from __future__ import annotations

import re

from config import AppConfig
from domain.res import ImpactReport
from llm.client import LLMClient, LLMSettings
from llm.prompts import build_answer_prompt


class AnswerGenerator:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or LLMClient()

    @classmethod
    def from_config(cls, cfg: AppConfig) -> "AnswerGenerator":
        settings = LLMSettings(
            provider=cfg.llm_provider,
            model=cfg.llm_model,
            api_key=cfg.openai_api_key,
            base_url=cfg.openai_base_url,
            timeout_seconds=cfg.openai_timeout_seconds,
        )
        return cls(llm_client=LLMClient(settings))

    def generate(self, question: str, retrieval_result: dict, impact_report: ImpactReport | None = None) -> str:
        triples = retrieval_result.get("triples", [])
        chunk_ids = retrieval_result.get("chunk_ids", [])
        chunks = _format_evidence_chunks(chunk_ids, retrieval_result.get("chunk_contents", []))
        impact_summary = None
        if impact_report:
            impact_summary = (
                f"direct={len(impact_report.direct_impacts)}, "
                f"indirect={len(impact_report.indirect_impacts)}, "
                f"scoped={len(impact_report.scoped_impact)}"
            )
        prompt = build_answer_prompt(question, triples, chunks, impact_summary)
        llm_answer = self.llm_client.generate(
            prompt=prompt,
            system_prompt="You are a strict graph analysis assistant. Answer only from provided evidence.",
        )
        if llm_answer:
            return _normalize_answer_markdown(llm_answer)

        lines = []
        lines.append(f"Question: {question}")
        if triples:
            lines.append(f"Matched relations: {len(triples)}; sample: {triples[0]}")
        if chunks:
            lines.append(f"Evidence chunks: {len(chunks)}")
        if impact_report:
            lines.append(
                "Impact summary: "
                f"direct={len(impact_report.direct_impacts)}, "
                f"indirect={len(impact_report.indirect_impacts)}, "
                f"scoped={len(impact_report.scoped_impact)}."
            )
        if not triples and not chunks:
            lines.append("No evidence was retrieved. Please refine the query.")
        return "\n".join(lines)


def _format_evidence_chunks(chunk_ids: list[str], chunk_contents: list[str]) -> list[str]:
    formatted: list[str] = []
    for index, content in enumerate(chunk_contents):
        if index < len(chunk_ids) and chunk_ids[index]:
            formatted.append(f"[{chunk_ids[index]}] {content}")
        else:
            formatted.append(str(content))
    return formatted


_ORDERED_MARKER_RE = re.compile(r"^(\d+)([.)])(\s+.*)$")
_UNORDERED_MARKER_RE = re.compile(r"^[-+*]\s+")


def _normalize_answer_markdown(text: str) -> str:
    return _convert_top_level_ordered_markers_to_bullets(_normalize_top_level_ordered_markers(text))


def _convert_top_level_ordered_markers_to_bullets(text: str) -> str:
    lines = text.splitlines()
    normalized: list[str] = []
    for line in lines:
        ordered_match = _ORDERED_MARKER_RE.match(line)
        if ordered_match:
            normalized.append(f"-{ordered_match.group(3)}")
        else:
            normalized.append(line)
    trailing_newline = "\n" if text.endswith("\n") else ""
    return "\n".join(normalized) + trailing_newline


def _normalize_top_level_ordered_markers(text: str) -> str:
    lines = text.splitlines()
    normalized: list[str] = []
    active_sequence = False
    next_number = 1

    for line in lines:
        ordered_match = _ORDERED_MARKER_RE.match(line)
        if ordered_match:
            marker_number = int(ordered_match.group(1))
            punctuation = ordered_match.group(2)
            tail = ordered_match.group(3)
            if active_sequence:
                line = f"{next_number}{punctuation}{tail}"
                next_number += 1
            else:
                active_sequence = True
                next_number = marker_number + 1
            normalized.append(line)
            continue

        normalized.append(line)
        if not line.strip() or line.startswith((" ", "\t")) or _UNORDERED_MARKER_RE.match(line):
            continue
        active_sequence = False
        next_number = 1

    trailing_newline = "\n" if text.endswith("\n") else ""
    return "\n".join(normalized) + trailing_newline
