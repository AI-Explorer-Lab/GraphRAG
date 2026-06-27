from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from lineage_graphrag.api.dependencies import get_repo
from lineage_graphrag.domain.query_models import AskRequest, AskResponse
from lineage_graphrag.graph.graph_views import extract_graph, extract_subgraph
from lineage_graphrag.retrieval.agentic_ircot import AgenticIRCoT
from lineage_graphrag.storage.graph_repository import GraphRepository

router = APIRouter(tags=["query"])


@router.get("/v1/graphs")
def list_graphs(repo: GraphRepository = Depends(get_repo)):
    return {"graphs": repo.list_graph_ids()}


@router.post("/v1/graphs/sync")
def sync_graphs(repo: GraphRepository = Depends(get_repo)):
    status = repo.sync_from_falkordb(clear_existing=True)
    if status.get("enabled") is False:
        raise HTTPException(status_code=400, detail="FalkorDB is disabled for this API runtime.")
    if status.get("available") is False:
        raise HTTPException(status_code=503, detail="FalkorDB is unavailable; start the database and retry sync.")
    return status


@router.post("/v1/queries/ask", response_model=AskResponse)
def ask_question(
    payload: AskRequest,
    request: Request,
    repo: GraphRepository = Depends(get_repo),
) -> AskResponse:
    graph = repo.get_graph(payload.graph_id)
    if graph is None:
        raise HTTPException(status_code=404, detail=f"graph_id '{payload.graph_id}' not built")
    chunks = repo.get_chunks(payload.graph_id)

    cfg = request.app.state.config
    chain = AgenticIRCoT.from_config(cfg)
    mode = payload.mode or cfg.default_ask_mode
    result = chain.run(
        graph=graph,
        chunks=chunks,
        question=payload.question,
        top_k=payload.top_k,
        mode=mode,
        max_steps=payload.max_steps,
    )
    return AskResponse(
        answer=str(result.get("answer", "")),
        sub_questions=result.get("sub_questions", []),  # type: ignore[arg-type]
        involved_types=result.get("involved_types", {}),  # type: ignore[arg-type]
        retrieval=result.get("retrieval", {}),
    )


@router.get("/v1/graphs/{graph_id}/subgraph")
def get_subgraph(
    graph_id: str,
    node_id: Optional[str] = Query(None, description="optional center node id"),
    hops: int = Query(1, ge=1, le=3),
    repo: GraphRepository = Depends(get_repo),
):
    graph = repo.get_graph(graph_id)
    if graph is None:
        raise HTTPException(status_code=404, detail=f"graph_id '{graph_id}' not built")
    if not node_id:
        return extract_graph(graph)
    return extract_subgraph(graph, node_id=node_id, hops=hops)
