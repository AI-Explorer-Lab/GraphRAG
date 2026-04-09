from __future__ import annotations

from fastapi import HTTPException, Request

from lineage_graphrag.storage.graph_repository import GraphRepository


def get_repo(request: Request) -> GraphRepository:
    repo: GraphRepository = request.app.state.repo
    return repo


def require_graph(repo: GraphRepository, graph_id: str):
    graph = repo.get_graph(graph_id)
    if graph is None:
        raise HTTPException(status_code=404, detail=f"graph_id '{graph_id}' not built")
    return graph

