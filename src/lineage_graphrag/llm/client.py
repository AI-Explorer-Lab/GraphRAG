from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lineage_graphrag.common.logging import get_logger

logger = get_logger(__name__)

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency in some environments
    OpenAI = None  # type: ignore[assignment]


@dataclass
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
        chat_error: Exception | None = None
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
            normalized = _normalize_content(content)
            if normalized:
                return normalized
        except Exception as exc:  # pragma: no cover - external system path
            chat_error = exc

        # Some gateways/models (for example GPT-5 series on router providers) expose
        # only the Responses API route.
        try:
            response_input = _build_responses_input(prompt=prompt, system_prompt=system_prompt)
            resp2 = self.client.responses.create(
                model=self.settings.model,
                input=response_input,
            )
            normalized2 = _normalize_responses_output(resp2)
            if normalized2:
                return normalized2
        except Exception as exc2:  # pragma: no cover - external system path
            if chat_error is not None:
                logger.warning("OpenAI generation failed: chat=%s ; responses=%s", chat_error, exc2)
            else:
                logger.warning("OpenAI generation failed: responses=%s", exc2)
            return None

        if chat_error is not None:
            logger.warning("OpenAI generation failed: %s", chat_error)
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


def _build_responses_input(prompt: str, system_prompt: str | None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if system_prompt:
        items.append(
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            }
        )
    items.append(
        {
            "role": "user",
            "content": [{"type": "input_text", "text": prompt}],
        }
    )
    return items


def _normalize_responses_output(resp: Any) -> str | None:
    output_text = getattr(resp, "output_text", None)
    normalized = _normalize_content(output_text)
    if normalized:
        return normalized

    output = getattr(resp, "output", None)
    if not isinstance(output, list):
        return None

    parts: list[str] = []
    for item in output:
        content = getattr(item, "content", None)
        if not isinstance(content, list):
            continue
        for c in content:
            text = getattr(c, "text", None)
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    merged = "\n".join(parts).strip()
    return merged or None
