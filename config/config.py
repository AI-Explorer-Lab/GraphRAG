from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

import yaml

try:  # pragma: no cover - exercised when dynaconf is installed in runtime envs
    from dynaconf import Dynaconf
except ImportError:  # pragma: no cover - local tests can run before dependency install
    Dynaconf = None  # type: ignore[assignment]


DEFAULT_CONFIG_CANDIDATES = (
    "configs/local.yaml",
    "config/app.yaml",
    "configs/base.yaml",
)


def default_config_path() -> str:
    configured = os.getenv("GRAPH_CONFIG")
    if configured:
        return configured
    for candidate in DEFAULT_CONFIG_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return DEFAULT_CONFIG_CANDIDATES[-1]


def resolve_config_path(path: str | Path | None = None) -> Path:
    return Path(path) if path else Path(default_config_path())


def _load_payload(path: Path) -> dict[str, Any]:
    if Dynaconf is not None:
        settings = Dynaconf(settings_files=[str(path)], environments=False, merge_enabled=True)
        payload = settings.as_dict()
        return _lower_keys(payload)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _lower_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k).lower(): _lower_keys(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_lower_keys(v) for v in value]
    return value


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


def _env_first(names: list[str]) -> str | None:
    for name in names:
        value = _env_optional(name)
        if value is not None:
            return value
    return None


def _llm_env_names(active_provider: str, generic_name: str, provider_name: str) -> list[str]:
    if active_provider.lower() in {"openai", "default"}:
        return [generic_name, provider_name]
    return [provider_name]


def _as_dict(raw: Any) -> dict[str, Any]:
    return raw if isinstance(raw, dict) else {}


def _as_str(raw: Any, default: str) -> str:
    if raw is None:
        return default
    value = str(raw).strip()
    return value or default


def _normalize_provider_base_url(active_provider: str, base_url: str | None) -> str | None:
    if base_url is None:
        return None
    normalized = base_url.strip()
    if not normalized:
        return None
    if active_provider.lower() == "anyrouter" and not normalized.rstrip("/").endswith("/v1"):
        normalized = normalized.rstrip("/") + "/v1"
    return normalized


@dataclass
class AppConfig:
    environment: str = "local"
    use_falkordb: bool = False
    falkordb_url: str = "redis://localhost:6379/0"
    default_top_k: int = 8
    default_ask_mode: str = "agent"
    agent_max_steps: int = 4
    decomposer_max_sub_questions: int = 3
    retrieval_embedding_model: str = "all-MiniLM-L6-v2"
    enable_faiss: bool = True
    retrieval_path_depth: int = 3

    llm_active_provider: str = "default"
    llm_provider: str = "stub"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_timeout_seconds: float = 30.0

    @classmethod
    def from_yaml(cls, path: str | Path | None = None) -> "AppConfig":
        config_path = resolve_config_path(path)
        payload = _load_payload(config_path)

        legacy_app_cfg = _as_dict(payload.get("app"))
        db_cfg = _as_dict(payload.get("db")) or legacy_app_cfg
        agent_cfg = _as_dict(payload.get("agent")) or legacy_app_cfg
        environment_cfg = _as_dict(payload.get("environment"))

        use_falkordb_default = bool(db_cfg.get("use_falkordb", False))
        falkordb_url_default = _as_str(db_cfg.get("falkordb_url"), "redis://localhost:6379/0")
        default_top_k_default = int(agent_cfg.get("default_top_k", 8))
        default_ask_mode_default = _as_str(agent_cfg.get("default_ask_mode"), "agent")
        agent_max_steps_default = int(agent_cfg.get("agent_max_steps", agent_cfg.get("max_steps", 4)))
        decomposer_max_sub_questions_default = int(agent_cfg.get("decomposer_max_sub_questions", 3))
        retrieval_embedding_model_default = _as_str(
            agent_cfg.get("retrieval_embedding_model"),
            "all-MiniLM-L6-v2",
        )
        enable_faiss_default = bool(agent_cfg.get("enable_faiss", True))
        retrieval_path_depth_default = int(agent_cfg.get("retrieval_path_depth", 3))

        legacy_provider = _as_str(agent_cfg.get("llm_provider"), "stub")
        legacy_model = _as_str(agent_cfg.get("llm_model"), "gpt-4o-mini")
        legacy_api_key = agent_cfg.get("openai_api_key")
        legacy_base_url = agent_cfg.get("openai_base_url")
        legacy_timeout = float(agent_cfg.get("openai_timeout_seconds", 30.0))

        llm_cfg = _as_dict(agent_cfg.get("llm"))
        providers_cfg = _as_dict(llm_cfg.get("providers"))
        active_provider_default = _as_str(llm_cfg.get("active_provider"), "default")
        active_provider = os.getenv("GRAPH_LLM_ACTIVE_PROVIDER", active_provider_default).strip() or "default"

        selected_provider_cfg = _as_dict(providers_cfg.get(active_provider))

        provider_default = _as_str(selected_provider_cfg.get("provider"), legacy_provider)
        model_default = _as_str(selected_provider_cfg.get("model"), legacy_model)
        api_key_default = selected_provider_cfg.get("api_key", legacy_api_key)
        base_url_default = selected_provider_cfg.get("base_url", legacy_base_url)
        timeout_default = float(selected_provider_cfg.get("timeout_seconds", legacy_timeout))

        provider_upper = active_provider.upper().replace("-", "_")
        provider_api_env = f"{provider_upper}_API_KEY"
        provider_base_env = f"{provider_upper}_BASE_URL"
        provider_model_env = f"{provider_upper}_MODEL"
        provider_timeout_env = f"{provider_upper}_TIMEOUT_SECONDS"

        api_key = (
            _env_first(_llm_env_names(active_provider, "OPENAI_API_KEY", provider_api_env))
            or (str(api_key_default).strip() if api_key_default else None)
        )

        base_url_env_candidates = _llm_env_names(active_provider, "OPENAI_BASE_URL", provider_base_env)
        if active_provider.lower() == "anyrouter":
            base_url_env_candidates = ["ANTHROPIC_BASE_URL", *base_url_env_candidates]
        base_url = _env_first(base_url_env_candidates) or (str(base_url_default).strip() if base_url_default else None)
        base_url = _normalize_provider_base_url(active_provider, base_url)

        timeout_raw = _env_first(
            _llm_env_names(active_provider, "OPENAI_TIMEOUT_SECONDS", provider_timeout_env)
        )
        timeout_seconds = float(timeout_raw) if timeout_raw is not None else timeout_default
        model = (
            _env_first(_llm_env_names(active_provider, "GRAPH_LLM_MODEL", provider_model_env))
            or model_default
        )

        environment_default = _as_str(environment_cfg.get("name"), "local")
        return cls(
            environment=os.getenv("GRAPH_ENV", environment_default),
            use_falkordb=_env_bool("GRAPH_USE_FALKORDB", use_falkordb_default),
            falkordb_url=os.getenv("GRAPH_FALKORDB_URL", falkordb_url_default),
            default_top_k=int(os.getenv("GRAPH_DEFAULT_TOP_K", str(default_top_k_default))),
            default_ask_mode=os.getenv("GRAPH_DEFAULT_ASK_MODE", default_ask_mode_default),
            agent_max_steps=int(os.getenv("GRAPH_AGENT_MAX_STEPS", str(agent_max_steps_default))),
            decomposer_max_sub_questions=int(
                os.getenv(
                    "GRAPH_DECOMPOSER_MAX_SUB_QUESTIONS",
                    str(decomposer_max_sub_questions_default),
                )
            ),
            retrieval_embedding_model=os.getenv(
                "GRAPH_RETRIEVAL_EMBEDDING_MODEL",
                retrieval_embedding_model_default,
            ),
            enable_faiss=_env_bool("GRAPH_ENABLE_FAISS", enable_faiss_default),
            retrieval_path_depth=int(os.getenv("GRAPH_RETRIEVAL_PATH_DEPTH", str(retrieval_path_depth_default))),
            llm_active_provider=active_provider,
            llm_provider=os.getenv("GRAPH_LLM_PROVIDER", provider_default),
            llm_model=model,
            openai_api_key=api_key,
            openai_base_url=base_url,
            openai_timeout_seconds=timeout_seconds,
        )
