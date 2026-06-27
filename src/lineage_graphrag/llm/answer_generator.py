from __future__ import annotations

from lineage_graphrag.common.config import AppConfig
from lineage_graphrag.domain.impact_models import ImpactReport
from lineage_graphrag.llm.client import LLMClient, LLMSettings
from lineage_graphrag.llm.prompts import build_answer_prompt


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
            system_prompt="You are a strict lineage analysis assistant. Answer only from provided evidence.",
        )
        if llm_answer:
            return llm_answer

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
