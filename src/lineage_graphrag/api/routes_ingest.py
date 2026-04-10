from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from lineage_graphrag.api.dependencies import get_repo
from lineage_graphrag.domain.query_models import ImportRequest
from lineage_graphrag.graph.kt_builder import LineageKTBuilder
from lineage_graphrag.ingest.normalizer import LineageNormalizer
from lineage_graphrag.ingest.parser import LineageParser
from lineage_graphrag.storage.graph_repository import GraphRepository
from lineage_graphrag.storage.snapshot_store import SnapshotStore

router = APIRouter(prefix="/v1/graphs", tags=["graphs"])


def _materialize_graph(
    graph_id: str,
    request: Request,
    repo: GraphRepository,
) -> dict:
    normalized = repo.get_lineage(graph_id)
    if normalized is None:
        raise HTTPException(status_code=404, detail=f"graph_id '{graph_id}' not imported")

    builder = LineageKTBuilder()
    result = builder.build(normalized)
    mirror_status = repo.save_graph(graph_id, result.graph, result.evidence_chunks, result.metadata)

    snapshot_store: SnapshotStore = request.app.state.snapshot_store
    snapshot_store.save(graph_id, result.graph, result.evidence_chunks)
    return {
        "graph_id": graph_id,
        "metadata": result.metadata,
        "chunks": len(result.evidence_chunks),
        "falkordb": mirror_status,
    }


@router.post("/import")
def import_lineage(
    payload: ImportRequest,
    request: Request,
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
    build_result = _materialize_graph(payload.graph_id, request, repo)
    return {
        **build_result,
        "entities": len(normalized.entities),
        "transitions": len(normalized.transitions),
        "has_relations": len(normalized.has_relations),
        "auto_built": True,
    }
