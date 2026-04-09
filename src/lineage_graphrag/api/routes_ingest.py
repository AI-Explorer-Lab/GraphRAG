from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from lineage_graphrag.api.dependencies import get_repo
from lineage_graphrag.domain.query_models import BuildRequest, ImportRequest
from lineage_graphrag.graph.kt_builder import LineageKTBuilder
from lineage_graphrag.ingest.normalizer import LineageNormalizer
from lineage_graphrag.ingest.parser import LineageParser
from lineage_graphrag.storage.graph_repository import GraphRepository
from lineage_graphrag.storage.snapshot_store import SnapshotStore

router = APIRouter(prefix="/v1/graphs", tags=["graphs"])


@router.post("/import")
def import_lineage(payload: ImportRequest, repo: GraphRepository = Depends(get_repo)):
    parser = LineageParser()
    normalizer = LineageNormalizer()
    lineage = parser.parse(payload.lineage_json)
    normalized = normalizer.normalize(lineage)
    repo.save_lineage(payload.graph_id, normalized)
    return {
        "graph_id": payload.graph_id,
        "entities": len(normalized.entities),
        "transitions": len(normalized.transitions),
        "has_relations": len(normalized.has_relations),
        "next_step": "call POST /v1/graphs/build to materialize graph",
    }


@router.post("/build")
def build_graph(
    payload: BuildRequest,
    request: Request,
    repo: GraphRepository = Depends(get_repo),
):
    normalized = repo.get_lineage(payload.graph_id)
    if normalized is None:
        raise HTTPException(status_code=404, detail=f"graph_id '{payload.graph_id}' not imported")

    builder = LineageKTBuilder()
    result = builder.build(normalized)
    mirror_status = repo.save_graph(payload.graph_id, result.graph, result.evidence_chunks, result.metadata)

    snapshot_store: SnapshotStore = request.app.state.snapshot_store
    snapshot_store.save(payload.graph_id, result.graph, result.evidence_chunks)
    return {
        "graph_id": payload.graph_id,
        "metadata": result.metadata,
        "chunks": len(result.evidence_chunks),
        "falkordb": mirror_status,
    }
