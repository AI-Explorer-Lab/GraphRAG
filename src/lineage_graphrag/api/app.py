from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from lineage_graphrag.api.routes_impact import router as impact_router
from lineage_graphrag.api.routes_ingest import router as ingest_router
from lineage_graphrag.api.routes_query import router as query_router
from lineage_graphrag.common.config import AppConfig
from lineage_graphrag.common.logging import get_logger
from lineage_graphrag.storage.graph_repository import GraphRepository
from lineage_graphrag.storage.snapshot_store import SnapshotStore

logger = get_logger(__name__)


def create_app(config_path: str | Path = "configs/base.yaml") -> FastAPI:
    cfg = AppConfig.from_yaml(config_path)
    app = FastAPI(title="lineage-graphrag", version="0.1.0")
    app.include_router(ingest_router)
    app.include_router(query_router)
    app.include_router(impact_router)

    app.state.config = cfg
    app.state.repo = GraphRepository(use_falkordb=cfg.use_falkordb, falkordb_url=cfg.falkordb_url)
    app.state.snapshot_store = SnapshotStore(cfg.snapshot_dir)
    hydrate_status = app.state.repo.hydrate_startup(app.state.snapshot_store)
    logger.info(
        "startup hydrate completed: snapshots_loaded=%s, falkordb_loaded=%s, total_graphs=%s",
        hydrate_status.get("snapshots_loaded"),
        hydrate_status.get("falkordb_loaded"),
        len(app.state.repo.list_graph_ids()),
    )
    errors = hydrate_status.get("errors", [])
    if isinstance(errors, list) and errors:
        logger.warning("startup hydrate errors: %s", errors)
    return app


app = create_app()
