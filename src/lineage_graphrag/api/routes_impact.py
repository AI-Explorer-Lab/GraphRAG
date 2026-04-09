from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from lineage_graphrag.api.dependencies import get_repo
from lineage_graphrag.domain.query_models import ImpactRequest
from lineage_graphrag.impact.propagation import ImpactAnalyzer
from lineage_graphrag.storage.graph_repository import GraphRepository

router = APIRouter(tags=["impact"])


@router.post("/v1/impact/what-if")
def what_if_impact(payload: ImpactRequest, repo: GraphRepository = Depends(get_repo)):
    graph = repo.get_graph(payload.graph_id)
    if graph is None:
        raise HTTPException(status_code=404, detail=f"graph_id '{payload.graph_id}' not built")

    analyzer = ImpactAnalyzer()
    report = analyzer.analyze(
        graph=graph,
        change_spec=payload.change_spec,
        target_node_id=payload.target_node_id,
    )
    return report.model_dump()

