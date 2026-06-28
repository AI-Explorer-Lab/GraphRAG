from __future__ import annotations

import json
import re
from typing import Any

from config import AppConfig
from llm.client import LLMClient, LLMSettings
from llm.prompts import build_decomposition_prompt


class GraphQuestionDecomposer:
    """LLM-first decomposition with deterministic fallback."""

    def __init__(self, llm_client: LLMClient | None = None, max_sub_questions: int = 3) -> None:
        self.llm_client = llm_client or LLMClient()
        self.max_sub_questions = max(1, min(max_sub_questions, 6))

    @classmethod
    def from_config(cls, cfg: AppConfig) -> "GraphQuestionDecomposer":
        settings = LLMSettings(
            provider=cfg.llm_provider,
            model=cfg.llm_model,
            api_key=cfg.openai_api_key,
            base_url=cfg.openai_base_url,
            timeout_seconds=cfg.openai_timeout_seconds,
        )
        return cls(
            llm_client=LLMClient(settings),
            max_sub_questions=cfg.decomposer_max_sub_questions,
        )

    def decompose(self, question: str) -> dict[str, object]:
        llm_sub_questions = self._decompose_with_llm(question)
        if llm_sub_questions:
            return {
                "sub_questions": [{"sub-question": q} for q in llm_sub_questions],
                # Graph schema is fixed (has/transitions), so this hint is optional.
                "involved_types": {},
            }

        fallback = self._fallback(question)
        return {
            "sub_questions": [{"sub-question": q} for q in fallback],
            "involved_types": {},
        }

    def _decompose_with_llm(self, question: str) -> list[str]:
        prompt = build_decomposition_prompt(question, max_sub_questions=self.max_sub_questions)
        raw = self.llm_client.generate(
            prompt=prompt,
            system_prompt="Return strict JSON only.",
        )
        if not raw:
            return []

        parsed = _safe_parse_json(raw)
        if not isinstance(parsed, dict):
            return []

        sub_questions = parsed.get("sub_questions")
        if not isinstance(sub_questions, list):
            return []

        normalized: list[str] = []
        for item in sub_questions:
            value: str | None = None
            if isinstance(item, dict):
                raw_value = item.get("sub-question")
                if isinstance(raw_value, str):
                    value = raw_value
            elif isinstance(item, str):
                value = item

            if value is None:
                continue

            cleaned = value.strip()
            if not cleaned:
                continue
            normalized.append(cleaned)
            if len(normalized) >= self.max_sub_questions:
                break
        return normalized

    def _fallback(self, question: str) -> list[str]:
        text = question.strip()
        if not text:
            return ["Explain the graph and key upstream/downstream dependencies."]

        lower = text.lower()
        if any(token in lower for token in ["what-if", "impact", "change"]):
            impact_parts = [
                f"What relationship is being changed in: {text}",
                f"Which downstream nodes are directly impacted by: {text}",
                f"What control, quality, or audit impact can be inferred for: {text}",
            ]
            return impact_parts[: self.max_sub_questions]

        clauses = re.split(r"[?.;]+\s*", text)
        normalized = [c.strip() for c in clauses if c.strip()]
        if not normalized:
            normalized = [text]
        return normalized[: self.max_sub_questions]


def _safe_parse_json(raw: str) -> Any:
    candidate = raw.strip()
    try:
        return json.loads(candidate)
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", candidate)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None
