from __future__ import annotations

from time import perf_counter
from typing import Any

from utils.logging import get_logger
from domain.req import GraphPreviewRequest, ImportRequest, TextImportRequest
from exceptions import BusinessException, NotFoundException, ServiceUnavailableException, ValidationException
from graph.kt_builder import GraphKTBuilder
from ingest.normalizer import GraphNormalizer
from ingest.parser import GraphParser
from ingest.text_extractor import TextGraphExtractor
from mapper.graph_repository import GraphRepository

logger = get_logger(__name__)


class GraphService:
    def __init__(self, repo: GraphRepository, cfg: Any | None = None) -> None:
        self.repo = repo
        self.cfg = cfg

    def preview_graph(self, payload: GraphPreviewRequest) -> dict:
        try:
            return self._preview_graph(payload.graph_json)
        except Exception as exc:
            raise ValidationException(f"invalid graph_json: {exc}") from exc

    def import_graph(self, payload: ImportRequest) -> dict:
        parser = GraphParser()
        normalizer = GraphNormalizer()

        try:
            graph = parser.parse(payload.graph_json)
            normalized = normalizer.normalize(graph)
        except Exception as exc:
            raise ValidationException(f"invalid graph_json: {exc}") from exc

        self.repo.save_graph_input(payload.graph_id, normalized)
        try:
            build_result = self._materialize_graph(payload.graph_id)
        except BusinessException:
            raise
        except Exception as exc:
            logger.exception("graph materialization failed: graph_id=%s", payload.graph_id)
            raise ValidationException(f"graph materialization failed: {exc}") from exc
        return {
            **build_result,
            "entities": len(normalized.entities),
            "transitions": len(normalized.transitions),
            "has_relations": len(normalized.has_relations),
            "focus_node_id": self._focus_node_id(normalized),
            "auto_built": True,
        }

    def import_graph_text(self, payload: TextImportRequest) -> dict:
        request_started = perf_counter()
        logger.info(
            "text import requested: graph_id=%s, text_length=%s, schema_hint=%s",
            payload.graph_id,
            len(payload.text),
            bool(payload.schema_hint and payload.schema_hint.strip()),
        )
        if payload.prefer_fallback_graph_json and payload.fallback_graph_json:
            logger.info("using preferred fallback graph_json for text import: graph_id=%s", payload.graph_id)
            graph_json = payload.fallback_graph_json
            extraction_source = "fallback_graph_json"
            extraction_error = "preferred fallback graph_json supplied"
        else:
            graph_json, extraction_source, extraction_error = self._extract_text_graph(payload)

        parser = GraphParser()
        normalizer = GraphNormalizer()
        try:
            parse_started = perf_counter()
            graph = parser.parse(graph_json)
            normalized = normalizer.normalize(graph)
            logger.info(
                "text import parse stage completed: graph_id=%s, elapsed_seconds=%.2f",
                payload.graph_id,
                perf_counter() - parse_started,
            )
        except Exception as exc:
            logger.exception("extracted graph_json is invalid: graph_id=%s", payload.graph_id)
            raise ValidationException(f"extracted graph_json is invalid: {exc}") from exc

        self.repo.save_graph_input(payload.graph_id, normalized)
        try:
            build_result = self._materialize_graph(payload.graph_id)
        except BusinessException:
            raise
        except Exception as exc:
            logger.exception("text import materialization failed: graph_id=%s", payload.graph_id)
            raise ValidationException(f"text import materialization failed: {exc}") from exc
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
            "focus_node_id": self._focus_node_id(normalized),
            "auto_built": True,
            "graph_json": graph_json,
            "extraction": {
                "source": extraction_source,
                "text_length": len(payload.text),
                "fallback_reason": extraction_error,
                "elapsed_seconds": round(perf_counter() - request_started, 2),
            },
        }

    def _extract_text_graph(self, payload: TextImportRequest) -> tuple[dict, str, str | None]:
        try:
            extractor = TextGraphExtractor.from_config(self.cfg)
            extraction_started = perf_counter()
            graph_json = extractor.extract(payload.text, payload.schema_hint)
            logger.info(
                "text extraction stage completed: graph_id=%s, elapsed_seconds=%.2f",
                payload.graph_id,
                perf_counter() - extraction_started,
            )
            return graph_json, "text", None
        except RuntimeError as exc:
            if payload.fallback_graph_json:
                logger.warning(
                    "text extraction unavailable, using fallback graph_json: graph_id=%s error=%s",
                    payload.graph_id,
                    exc,
                )
                return payload.fallback_graph_json, "fallback_graph_json", str(exc)
            logger.warning("text extraction unavailable: graph_id=%s error=%s", payload.graph_id, exc)
            raise ServiceUnavailableException(str(exc)) from exc
        except ValueError as exc:
            if payload.fallback_graph_json:
                logger.warning(
                    "text extraction invalid, using fallback graph_json: graph_id=%s error=%s",
                    payload.graph_id,
                    exc,
                )
                return payload.fallback_graph_json, "fallback_graph_json", str(exc)
            logger.exception("text extraction failed: graph_id=%s", payload.graph_id)
            raise ValidationException(f"text extraction failed: {exc}") from exc
        except Exception as exc:
            if payload.fallback_graph_json:
                logger.exception("text extraction failed, using fallback graph_json: graph_id=%s", payload.graph_id)
                return payload.fallback_graph_json, "fallback_graph_json", str(exc)
            logger.exception("text extraction failed: graph_id=%s", payload.graph_id)
            raise ValidationException(f"text extraction failed: {exc}") from exc

    def _preview_graph(self, graph_json: dict) -> dict:
        parser = GraphParser()
        normalizer = GraphNormalizer()
        graph = parser.parse(graph_json)
        normalized = normalizer.normalize(graph)
        result = GraphKTBuilder().build(normalized)
        relation_counts: dict[str, int] = {}
        for transition in normalized.transitions:
            relation_counts[transition.relation] = relation_counts.get(transition.relation, 0) + 1
        checklist = [
            {"label": "graph JSON parseable", "ok": True},
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
            "focus_node_id": self._focus_node_id(normalized),
            "relation_counts": relation_counts,
            "relation_types": sorted(relation_counts),
            "checklist": checklist,
        }

    def _materialize_graph(self, graph_id: str) -> dict:
        normalized = self.repo.get_graph_input(graph_id)
        if normalized is None:
            raise NotFoundException(f"graph_id '{graph_id}' not imported")

        started = perf_counter()
        builder = GraphKTBuilder()
        result = builder.build(normalized)
        build_elapsed = perf_counter() - started

        started = perf_counter()
        falkor_status = self.repo.save_graph(graph_id, result.graph, result.evidence_chunks, result.metadata)
        save_graph_elapsed = perf_counter() - started
        if falkor_status.get("enabled") and not falkor_status.get("written"):
            raise ServiceUnavailableException(
                f"FalkorDB write failed for graph_id '{graph_id}': "
                f"{falkor_status.get('error') or 'database unavailable'}"
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

    @staticmethod
    def _focus_node_id(normalized) -> str | None:
        if not normalized.entities:
            return None
        high_signal = {"person", "user", "account", "wallet", "merchant", "business", "entity"}
        for entity in normalized.entities:
            entity_type = str(entity.properties.get("type", "")).lower()
            if entity_type in high_signal:
                return entity.id
        return normalized.entities[0].id
