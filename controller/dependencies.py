from __future__ import annotations

from fastapi import Request

from config import AppConfig
from mapper.graph_repository import GraphRepository
from service import GraphService, ImpactService, QueryService


def get_config(request: Request) -> AppConfig:
    return request.app.state.config


def get_repo(request: Request) -> GraphRepository:
    return request.app.state.repo


def get_graph_service(request: Request) -> GraphService:
    return GraphService(repo=get_repo(request), cfg=get_config(request))


def get_query_service(request: Request) -> QueryService:
    return QueryService(repo=get_repo(request), cfg=get_config(request))


def get_impact_service(request: Request) -> ImpactService:
    return ImpactService(repo=get_repo(request))
