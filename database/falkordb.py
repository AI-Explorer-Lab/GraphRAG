from __future__ import annotations

from config import AppConfig
from mapper.graph_repository import GraphRepository


def create_graph_repository(cfg: AppConfig) -> GraphRepository:
    return GraphRepository(use_falkordb=cfg.use_falkordb, falkordb_url=cfg.falkordb_url)
