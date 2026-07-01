from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from utils.logging import get_logger
from config import AppConfig
from database.falkordb import create_graph_repository

logger = get_logger(__name__)


def initialize_runtime(app: FastAPI, cfg: AppConfig) -> None:
    if getattr(app.state, "runtime_initialized", False):
        return

    app.state.config = cfg
    app.state.repo = create_graph_repository(cfg)
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
    app.state.runtime_initialized = True


def build_lifespan(cfg: AppConfig):
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        initialize_runtime(app, cfg)
        try:
            yield
        finally:
            app.state.runtime_initialized = False

    return lifespan
