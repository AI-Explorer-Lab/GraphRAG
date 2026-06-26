from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from lineage_graphrag.api.routes_impact import router as impact_router
from lineage_graphrag.api.routes_ingest import router as ingest_router
from lineage_graphrag.api.routes_query import router as query_router
from lineage_graphrag.common.config import AppConfig, default_config_path
from lineage_graphrag.common.logging import get_logger
from lineage_graphrag.storage.graph_repository import GraphRepository

logger = get_logger(__name__)


def create_app(config_path: str | Path | None = None) -> FastAPI:
    cfg = AppConfig.from_yaml(config_path)
    app = FastAPI(title="lineage-graphrag", version="0.1.0")

    @app.exception_handler(Exception)
    async def log_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled request error: method=%s path=%s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

    app.include_router(ingest_router)
    app.include_router(query_router)
    app.include_router(impact_router)

    app.state.config = cfg
    logger.info(
        "llm config selected: active_provider=%s, provider=%s, model=%s, base_url=%s",
        cfg.llm_active_provider,
        cfg.llm_provider,
        cfg.llm_model,
        cfg.openai_base_url or "<default>",
    )
    app.state.repo = GraphRepository(use_falkordb=cfg.use_falkordb, falkordb_url=cfg.falkordb_url)
    hydrate_status = app.state.repo.hydrate_startup()
    logger.info(
        "startup hydrate completed: falkordb_enabled=%s, falkordb_loaded=%s, total_graphs=%s",
        hydrate_status.get("falkordb_enabled"),
        hydrate_status.get("falkordb_loaded"),
        len(app.state.repo.list_graph_ids()),
    )
    errors = hydrate_status.get("errors", [])
    if isinstance(errors, list) and errors:
        logger.warning("startup hydrate errors: %s", errors)
    return app


class LazyApp:
    def __init__(self) -> None:
        self._app: FastAPI | None = None

    async def __call__(self, scope, receive, send) -> None:
        if self._app is None:
            self._app = create_app(os.getenv("LINEAGE_CONFIG") or default_config_path())
        await self._app(scope, receive, send)


app = LazyApp()


