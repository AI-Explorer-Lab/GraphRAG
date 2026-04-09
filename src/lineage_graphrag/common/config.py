from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

import yaml


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_optional(name: str) -> str | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    return value


@dataclass(slots=True)
class AppConfig:
    use_falkordb: bool = False
    falkordb_url: str = "redis://localhost:6379/0"
    snapshot_dir: str = "data/normalized"
    default_top_k: int = 8
    llm_provider: str = "stub"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_timeout_seconds: float = 30.0

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AppConfig":
        with open(path, "r", encoding="utf-8") as f:
            payload: dict[str, Any] = yaml.safe_load(f) or {}
        app_cfg = payload.get("app", {})

        use_falkordb_default = bool(app_cfg.get("use_falkordb", False))
        falkordb_url_default = str(app_cfg.get("falkordb_url", "redis://localhost:6379/0"))
        snapshot_dir_default = str(app_cfg.get("snapshot_dir", "data/normalized"))
        default_top_k_default = int(app_cfg.get("default_top_k", 8))

        llm_provider_default = str(app_cfg.get("llm_provider", "stub"))
        llm_model_default = str(app_cfg.get("llm_model", "gpt-4o-mini"))
        openai_api_key_default = app_cfg.get("openai_api_key")
        openai_base_url_default = app_cfg.get("openai_base_url")
        openai_timeout_default = float(app_cfg.get("openai_timeout_seconds", 30.0))

        env_timeout = _env_optional("OPENAI_TIMEOUT_SECONDS")
        timeout_seconds = float(env_timeout) if env_timeout is not None else openai_timeout_default

        return cls(
            use_falkordb=_env_bool("LINEAGE_USE_FALKORDB", use_falkordb_default),
            falkordb_url=os.getenv("LINEAGE_FALKORDB_URL", falkordb_url_default),
            snapshot_dir=os.getenv("LINEAGE_SNAPSHOT_DIR", snapshot_dir_default),
            default_top_k=int(os.getenv("LINEAGE_DEFAULT_TOP_K", str(default_top_k_default))),
            llm_provider=os.getenv("LINEAGE_LLM_PROVIDER", llm_provider_default),
            llm_model=os.getenv("LINEAGE_LLM_MODEL", llm_model_default),
            openai_api_key=_env_optional("OPENAI_API_KEY")
            or (str(openai_api_key_default) if openai_api_key_default else None),
            openai_base_url=_env_optional("OPENAI_BASE_URL")
            or (str(openai_base_url_default) if openai_base_url_default else None),
            openai_timeout_seconds=timeout_seconds,
        )
