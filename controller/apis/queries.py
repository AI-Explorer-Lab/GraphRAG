from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from controller.dependencies import get_query_service
from domain.req import AskRequest
from domain.res import AskResponse
from service.query_service import QueryService

router = APIRouter(tags=["query"])


@router.get("/v1/graphs")
def list_graphs(service: QueryService = Depends(get_query_service)):
    return service.list_graphs()


@router.post("/v1/graphs/sync")
def sync_graphs(service: QueryService = Depends(get_query_service)):
    return service.sync_graphs()


@router.post("/v1/queries/ask", response_model=AskResponse)
def ask_question(payload: AskRequest, service: QueryService = Depends(get_query_service)) -> AskResponse:
    return service.ask_question(payload)


@router.get("/v1/graphs/{graph_id}/subgraph")
def get_subgraph(
    graph_id: str,
    node_id: Optional[str] = Query(None, description="optional center node id"),
    hops: int = Query(1, ge=1, le=3),
    view: str = Query("full", description="business, entity_attribute, semantic, or full"),
    service: QueryService = Depends(get_query_service),
):
    return service.get_subgraph(graph_id=graph_id, node_id=node_id, hops=hops, view=view)
