from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from utils.logging import get_logger

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
        self.last_error: str | None = None
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

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        json_mode: bool = False,
        max_output_tokens: int | None = None,
    ) -> str | None:
        self.last_error = None
        if not self.is_available():
            return None

        if _prefer_responses_first(self.settings):
            responses_text, responses_error = self._generate_responses(
                prompt,
                system_prompt,
                json_mode=json_mode,
                max_output_tokens=max_output_tokens,
            )
            if responses_text:
                return responses_text
            chat_text, chat_error = self._generate_chat(
                prompt,
                system_prompt,
                json_mode=json_mode,
                max_output_tokens=max_output_tokens,
            )
            if chat_text:
                return chat_text
            _log_generation_failure(chat_error=chat_error, responses_error=responses_error)
            self.last_error = _merge_errors(chat_error=chat_error, responses_error=responses_error)
            return None

        chat_text, chat_error = self._generate_chat(
            prompt,
            system_prompt,
            json_mode=json_mode,
            max_output_tokens=max_output_tokens,
        )
        if chat_text:
            return chat_text
        responses_text, responses_error = self._generate_responses(
            prompt,
            system_prompt,
            json_mode=json_mode,
            max_output_tokens=max_output_tokens,
        )
        if responses_text:
            return responses_text
        _log_generation_failure(chat_error=chat_error, responses_error=responses_error)
        self.last_error = _merge_errors(chat_error=chat_error, responses_error=responses_error)
        return None

    def _generate_chat(
        self,
        prompt: str,
        system_prompt: str | None,
        json_mode: bool = False,
        max_output_tokens: int | None = None,
    ) -> tuple[str | None, Exception | None]:
        chat_error: Exception | None = None
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            kwargs: dict[str, Any] = {
                "model": self.settings.model,
                "messages": messages,
                "temperature": self.settings.temperature,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            if max_output_tokens is not None:
                kwargs["max_completion_tokens"] = max_output_tokens
            resp = self.client.chat.completions.create(
                **kwargs,
            )
            content = resp.choices[0].message.content if resp.choices else None
            normalized = _normalize_content(content)
            if normalized:
                return normalized, None
        except Exception as exc:  # pragma: no cover - external system path
            chat_error = exc
        return None, chat_error

    def _generate_responses(
        self,
        prompt: str,
        system_prompt: str | None,
        json_mode: bool = False,
        max_output_tokens: int | None = None,
    ) -> tuple[str | None, Exception | None]:
        try:
            response_input = _build_responses_input(prompt=prompt, system_prompt=system_prompt)
            kwargs: dict[str, Any] = {
                "model": self.settings.model,
                "input": response_input,
                "temperature": self.settings.temperature,
            }
            if json_mode:
                kwargs["text"] = {"format": {"type": "json_object"}, "verbosity": "low"}
            if max_output_tokens is not None:
                kwargs["max_output_tokens"] = max_output_tokens
            if _prefer_low_reasoning(self.settings):
                kwargs["reasoning"] = {"effort": "minimal"}
            try:
                resp2 = self.client.responses.create(**kwargs)
            except Exception:
                if "reasoning" not in kwargs:
                    raise
                kwargs.pop("reasoning", None)
                resp2 = self.client.responses.create(**kwargs)
            normalized2 = _normalize_responses_output(resp2)
            if normalized2:
                return normalized2, None
        except Exception as exc2:  # pragma: no cover - external system path
            return None, exc2
        return None, None


def _prefer_responses_first(settings: LLMSettings) -> bool:
    base_url = (settings.base_url or "").lower()
    model = settings.model.lower()
    return "right.codes" in base_url or model.startswith("gpt-5")


def _prefer_low_reasoning(settings: LLMSettings) -> bool:
    model = settings.model.lower()
    return model.startswith("gpt-5")


def _merge_errors(chat_error: Exception | None, responses_error: Exception | None) -> str | None:
    if chat_error is not None and responses_error is not None:
        return f"chat={chat_error}; responses={responses_error}"
    if responses_error is not None:
        return str(responses_error)
    if chat_error is not None:
        return str(chat_error)
    return None


def _log_generation_failure(chat_error: Exception | None, responses_error: Exception | None) -> None:
    if chat_error is not None and responses_error is not None:
        logger.warning("OpenAI generation failed: chat=%s ; responses=%s", chat_error, responses_error)
    elif responses_error is not None:
        logger.warning("OpenAI generation failed: responses=%s", responses_error)
    elif chat_error is not None:
        logger.warning("OpenAI generation failed: chat=%s", chat_error)


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
