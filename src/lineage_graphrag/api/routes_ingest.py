from __future__ import annotations

from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Request

from lineage_graphrag.api.dependencies import get_repo
from lineage_graphrag.common.logging import get_logger
from lineage_graphrag.domain.query_models import ImportRequest, LineagePreviewRequest, TextImportRequest
from lineage_graphrag.graph.kt_builder import LineageKTBuilder
from lineage_graphrag.ingest.normalizer import LineageNormalizer
from lineage_graphrag.ingest.parser import LineageParser
from lineage_graphrag.ingest.text_extractor import TextLineageExtractor
from lineage_graphrag.storage.graph_repository import GraphRepository

router = APIRouter(prefix="/v1/graphs", tags=["graphs"])
logger = get_logger(__name__)


def _focus_node_id(normalized) -> str | None:
    if not normalized.entities:
        return None
    high_signal = {"person", "user", "account", "wallet", "merchant", "business", "entity"}
    for entity in normalized.entities:
        entity_type = str(entity.properties.get("type", "")).lower()
        if entity_type in high_signal:
            return entity.id
    return normalized.entities[0].id


def _preview_lineage(lineage_json: dict) -> dict:
    parser = LineageParser()
    normalizer = LineageNormalizer()
    lineage = parser.parse(lineage_json)
    normalized = normalizer.normalize(lineage)
    result = LineageKTBuilder().build(normalized)
    relation_counts: dict[str, int] = {}
    for transition in normalized.transitions:
        relation_counts[transition.relation] = relation_counts.get(transition.relation, 0) + 1
    checklist = [
        {"label": "lineage JSON 可解析", "ok": True},
        {"label": "entities", "ok": len(normalized.entities) > 0, "value": len(normalized.entities)},
        {"label": "transitions", "ok": len(normalized.transitions) > 0, "value": len(normalized.transitions)},
        {"label": "has_relations", "ok": len(normalized.has_relations) > 0, "value": len(normalized.has_relations)},
        {
            "label": "relations",
            "ok": bool(relation_counts),
            "value": " / ".join(sorted(relation_counts)) if relation_counts else "none",
        },
    ]
    return {
        "entities": len(normalized.entities),
        "transitions": len(normalized.transitions),
        "has_relations": len(normalized.has_relations),
        "metadata": result.metadata,
        "chunks": len(result.evidence_chunks),
        "focus_node_id": _focus_node_id(normalized),
        "relation_counts": relation_counts,
        "relation_types": sorted(relation_counts),
        "checklist": checklist,
    }


def _materialize_graph(
    graph_id: str,
    repo: GraphRepository,
) -> dict:
    normalized = repo.get_lineage(graph_id)
    if normalized is None:
        raise HTTPException(status_code=404, detail=f"graph_id '{graph_id}' not imported")

    started = perf_counter()
    builder = LineageKTBuilder()
    result = builder.build(normalized)
    build_elapsed = perf_counter() - started

    started = perf_counter()
    falkor_status = repo.save_graph(graph_id, result.graph, result.evidence_chunks, result.metadata)
    save_graph_elapsed = perf_counter() - started
    if falkor_status.get("enabled") and not falkor_status.get("written"):
        raise HTTPException(
            status_code=503,
            detail=f"FalkorDB write failed for graph_id '{graph_id}': {falkor_status.get('error') or 'database unavailable'}",
        )

    logger.info(
        "graph materialized: graph_id=%s, build_seconds=%.2f, save_graph_seconds=%.2f",
        graph_id,
        build_elapsed,
        save_graph_elapsed,
    )
    return {
        "graph_id": graph_id,
        "metadata": result.metadata,
        "chunks": len(result.evidence_chunks),
        "falkordb": falkor_status,
    }


@router.post("/preview")
def preview_lineage(payload: LineagePreviewRequest):
    try:
        return _preview_lineage(payload.lineage_json)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"invalid lineage_json: {exc}") from exc


@router.post("/import")
def import_lineage(
    payload: ImportRequest,
    repo: GraphRepository = Depends(get_repo),
):
    parser = LineageParser()
    normalizer = LineageNormalizer()

    try:
        lineage = parser.parse(payload.lineage_json)
        normalized = normalizer.normalize(lineage)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"invalid lineage_json: {exc}") from exc

    repo.save_lineage(payload.graph_id, normalized)
    try:
        build_result = _materialize_graph(payload.graph_id, repo)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("graph materialization failed: graph_id=%s", payload.graph_id)
        raise HTTPException(status_code=500, detail=f"graph materialization failed: {exc}") from exc
    return {
        **build_result,
        "entities": len(normalized.entities),
        "transitions": len(normalized.transitions),
        "has_relations": len(normalized.has_relations),
        "focus_node_id": _focus_node_id(normalized),
        "auto_built": True,
    }


@router.post("/import-text")
def import_lineage_text(
    payload: TextImportRequest,
    request: Request,
    repo: GraphRepository = Depends(get_repo),
):
    request_started = perf_counter()
    logger.info(
        "text import requested: graph_id=%s, text_length=%s, schema_hint=%s",
        payload.graph_id,
        len(payload.text),
        bool(payload.schema_hint and payload.schema_hint.strip()),
    )
    if payload.prefer_fallback_lineage_json and payload.fallback_lineage_json:
        logger.info("using preferred fallback lineage_json for text import: graph_id=%s", payload.graph_id)
        lineage_json = payload.fallback_lineage_json
        extraction_source = "fallback_lineage_json"
        extraction_error = "preferred fallback lineage_json supplied"
    else:
        try:
            extractor = TextLineageExtractor.from_config(request.app.state.config)
            extraction_started = perf_counter()
            lineage_json = extractor.extract(payload.text, payload.schema_hint)
            extraction_elapsed = perf_counter() - extraction_started
            logger.info(
                "text extraction stage completed: graph_id=%s, elapsed_seconds=%.2f",
                payload.graph_id,
                extraction_elapsed,
            )
            extraction_source = "text"
            extraction_error = None
        except RuntimeError as exc:
            if payload.fallback_lineage_json:
                logger.warning(
                    "text extraction unavailable, using fallback lineage_json: graph_id=%s error=%s",
                    payload.graph_id,
                    exc,
                )
                lineage_json = payload.fallback_lineage_json
                extraction_source = "fallback_lineage_json"
                extraction_error = str(exc)
            else:
                logger.warning("text extraction unavailable: graph_id=%s error=%s", payload.graph_id, exc)
                raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            if payload.fallback_lineage_json:
                logger.warning(
                    "text extraction invalid, using fallback lineage_json: graph_id=%s error=%s",
                    payload.graph_id,
                    exc,
                )
                lineage_json = payload.fallback_lineage_json
                extraction_source = "fallback_lineage_json"
                extraction_error = str(exc)
            else:
                logger.exception("text extraction failed: graph_id=%s", payload.graph_id)
                raise HTTPException(status_code=422, detail=f"text extraction failed: {exc}") from exc
        except Exception as exc:
            if payload.fallback_lineage_json:
                logger.exception("text extraction failed, using fallback lineage_json: graph_id=%s", payload.graph_id)
                lineage_json = payload.fallback_lineage_json
                extraction_source = "fallback_lineage_json"
                extraction_error = str(exc)
            else:
                logger.exception("text extraction failed: graph_id=%s", payload.graph_id)
                raise HTTPException(status_code=422, detail=f"text extraction failed: {exc}") from exc

    parser = LineageParser()
    normalizer = LineageNormalizer()
    try:
        parse_started = perf_counter()
        lineage = parser.parse(lineage_json)
        normalized = normalizer.normalize(lineage)
        logger.info(
            "text import parse stage completed: graph_id=%s, elapsed_seconds=%.2f",
            payload.graph_id,
            perf_counter() - parse_started,
        )
    except Exception as exc:
        logger.exception("extracted lineage_json is invalid: graph_id=%s", payload.graph_id)
        raise HTTPException(status_code=422, detail=f"extracted lineage_json is invalid: {exc}") from exc

    repo.save_lineage(payload.graph_id, normalized)
    try:
        build_result = _materialize_graph(payload.graph_id, repo)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("text import materialization failed: graph_id=%s", payload.graph_id)
        raise HTTPException(status_code=500, detail=f"text import materialization failed: {exc}") from exc
    logger.info(
        "text import completed: graph_id=%s, entities=%s, transitions=%s, has_relations=%s",
        payload.graph_id,
        len(normalized.entities),
        len(normalized.transitions),
        len(normalized.has_relations),
    )
    return {
        **build_result,
        "entities": len(normalized.entities),
        "transitions": len(normalized.transitions),
        "has_relations": len(normalized.has_relations),
        "focus_node_id": _focus_node_id(normalized),
        "auto_built": True,
        "lineage_json": lineage_json,
        "extraction": {
            "source": extraction_source,
            "text_length": len(payload.text),
            "fallback_reason": extraction_error,
            "elapsed_seconds": round(perf_counter() - request_started, 2),
        },
    }
