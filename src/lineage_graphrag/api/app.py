from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from lineage_graphrag.api.routes_impact import router as impact_router
from lineage_graphrag.api.routes_ingest import router as ingest_router
from lineage_graphrag.api.routes_query import router as query_router
from lineage_graphrag.common.config import AppConfig
from lineage_graphrag.storage.graph_repository import GraphRepository
from lineage_graphrag.storage.snapshot_store import SnapshotStore


def create_app(config_path: str | Path = "configs/base.yaml") -> FastAPI:
    cfg = AppConfig.from_yaml(config_path)
    app = FastAPI(title="lineage-graphrag", version="0.1.0")
    app.include_router(ingest_router)
    app.include_router(query_router)
    app.include_router(impact_router)

    app.state.config = cfg
    app.state.repo = GraphRepository(use_falkordb=cfg.use_falkordb, falkordb_url=cfg.falkordb_url)
    app.state.snapshot_store = SnapshotStore(cfg.snapshot_dir)
    return app


app = create_app()

