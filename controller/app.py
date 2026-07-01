from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from config import AppConfig, default_config_path
from utils.logging import get_logger
from controller.apis import graphs_router, impact_router, queries_router
from database import build_lifespan, initialize_runtime
from exceptions import register_exception_handlers
from middlewares import RequestLoggingMiddleware

logger = get_logger(__name__)


def create_app(config_path: str | Path | None = None) -> FastAPI:
    cfg = AppConfig.from_yaml(config_path)
    app = FastAPI(title="graphrag", version="0.1.0", lifespan=build_lifespan(cfg))
    register_exception_handlers(app)
    app.add_middleware(RequestLoggingMiddleware)

    app.include_router(graphs_router)
    app.include_router(queries_router)
    app.include_router(impact_router)

    logger.info(
        "runtime config selected: environment=%s, active_provider=%s, provider=%s, model=%s, base_url=%s",
        cfg.environment,
        cfg.llm_active_provider,
        cfg.llm_provider,
        cfg.llm_model,
        cfg.openai_base_url or "<default>",
    )
    initialize_runtime(app, cfg)
    return app


class LazyApp:
    def __init__(self) -> None:
        self._app: FastAPI | None = None

    async def __call__(self, scope, receive, send) -> None:
        if self._app is None:
            self._app = create_app(os.getenv("GRAPH_CONFIG") or default_config_path())
        await self._app(scope, receive, send)


app = LazyApp()


