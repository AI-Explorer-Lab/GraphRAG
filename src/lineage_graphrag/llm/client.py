from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lineage_graphrag.common.logging import get_logger

logger = get_logger(__name__)

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency in some environments
    OpenAI = None  # type: ignore[assignment]


@dataclass(slots=True)
class LLMSettings:
    provider: str = "stub"
    model: str = "gpt-4o-mini"
    api_key: str | None = None
    base_url: str | None = None
    timeout_seconds: float = 30.0
    temperature: float = 0.2


class LLMClient:
    def __init__(self, settings: LLMSettings | None = None) -> None:
        self.settings = settings or LLMSettings()
        self.provider = self.settings.provider.strip().lower()
        self.client: Any = None
        if self.provider == "openai":
            self._init_openai_client()

    def _init_openai_client(self) -> None:
        if OpenAI is None:
            logger.warning("OpenAI SDK not installed. Install 'openai' to enable real LLM calls.")
            return
        if not self.settings.api_key:
            logger.warning("OPENAI_API_KEY is missing. Falling back to local answer mode.")
            return

        kwargs: dict[str, Any] = {
            "api_key": self.settings.api_key,
            "timeout": self.settings.timeout_seconds,
        }
        if self.settings.base_url:
            kwargs["base_url"] = self.settings.base_url

        try:
            self.client = OpenAI(**kwargs)
        except Exception as exc:  # pragma: no cover - external system path
            logger.warning("OpenAI client init failed: %s", exc)
            self.client = None

    def is_available(self) -> bool:
        return self.provider == "openai" and self.client is not None

    def generate(self, prompt: str, system_prompt: str | None = None) -> str | None:
        if not self.is_available():
            return None
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            resp = self.client.chat.completions.create(
                model=self.settings.model,
                messages=messages,
                temperature=self.settings.temperature,
            )
            content = resp.choices[0].message.content if resp.choices else None
            return _normalize_content(content)
        except Exception as exc:  # pragma: no cover - external system path
            logger.warning("OpenAI generation failed: %s", exc)
            return None


def _normalize_content(content: Any) -> str | None:
    if content is None:
        return None
    if isinstance(content, str):
        stripped = content.strip()
        return stripped if stripped else None
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        merged = "\n".join(p for p in parts if p.strip()).strip()
        return merged if merged else None
    return str(content).strip() or None
