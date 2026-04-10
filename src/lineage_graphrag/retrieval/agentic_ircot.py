from __future__ import annotations

import re
from typing import Any

import networkx as nx

from lineage_graphrag.common.config import AppConfig
from lineage_graphrag.llm.answer_generator import AnswerGenerator
from lineage_graphrag.llm.prompts import build_ircot_prompt
from lineage_graphrag.retrieval.decomposer import LineageQuestionDecomposer
from lineage_graphrag.retrieval.orchestrator import LineageRetriever


class AgenticIRCoT:
    def __init__(
        self,
        decomposer: LineageQuestionDecomposer,
        retriever: LineageRetriever,
        answer_gen: AnswerGenerator,
        default_max_steps: int = 4,
    ) -> None:
        self.decomposer = decomposer
        self.retriever = retriever
        self.answer_gen = answer_gen
        self.default_max_steps = max(1, default_max_steps)

    @classmethod
    def from_config(cls, cfg: AppConfig) -> "AgenticIRCoT":
        return cls(
            decomposer=LineageQuestionDecomposer.from_config(cfg),
            retriever=LineageRetriever.from_config(cfg),
            answer_gen=AnswerGenerator.from_config(cfg),
            default_max_steps=cfg.agent_max_steps,
        )

    def run(
        self,
        graph: nx.MultiDiGraph,
        chunks: dict[str, str],
        question: str,
        top_k: int = 8,
        mode: str = "agent",
        max_steps: int | None = None,
    ) -> dict[str, Any]:
        decomposition = self.decomposer.decompose(question)
        sub_questions = decomposition["sub_questions"]
        involved_types = decomposition["involved_types"]

        merged_triples: list[str] = []
        merged_chunk_ids: list[str] = []
        merged_chunk_contents: list[str] = []
        merged_paths: list[Any] = []
        step_logs: list[dict[str, Any]] = []

        for sub_q in sub_questions:
            sub_text = str(sub_q.get("sub-question", question))
            result = self.retriever.retrieve(
                graph=graph,
                chunks=chunks,
                question=sub_text,
                top_k=top_k,
                involved_types=involved_types,  # type: ignore[arg-type]
            )
            merged_triples.extend(result.get("triples", []))
            merged_chunk_ids.extend(result.get("chunk_ids", []))
            merged_chunk_contents.extend(result.get("chunk_contents", []))
            merged_paths.extend(result.get("paths", []))
            step_logs.append(
                {
                    "step": 0,
                    "sub_question": sub_text,
                    "triples": len(result.get("triples", [])),
                    "chunks": len(result.get("chunk_contents", [])),
                    "mode": "decomposition_retrieval",
                }
            )

        retrieval_result = _build_retrieval_result(
            merged_triples,
            merged_chunk_ids,
            merged_chunk_contents,
            merged_paths,
            top_k=top_k,
        )

        normalized_mode = mode.lower().strip() if isinstance(mode, str) else "agent"
        if normalized_mode not in {"agent", "noagent"}:
            normalized_mode = "agent"

        final_answer = self.answer_gen.generate(question, retrieval_result)
        if normalized_mode == "noagent" or not self.answer_gen.llm_client.is_available():
            retrieval_result["reasoning_steps"] = step_logs
            retrieval_result["mode"] = normalized_mode
            return {
                "answer": final_answer,
                "sub_questions": sub_questions,
                "involved_types": involved_types,
                "retrieval": retrieval_result,
            }

        loop_steps = max_steps if isinstance(max_steps, int) and max_steps > 0 else self.default_max_steps
        current_query = question
        thoughts: list[str] = []

        for step in range(1, loop_steps + 1):
            context = _build_context(retrieval_result)
            ircot_prompt = build_ircot_prompt(
                original_question=question,
                current_query=current_query,
                context=context,
                thoughts=thoughts,
                step=step,
                max_steps=loop_steps,
            )
            reasoning = self.answer_gen.llm_client.generate(
                prompt=ircot_prompt,
                system_prompt="Return concise iterative reasoning.",
            )
            if not reasoning:
                break
            thoughts.append(reasoning)

            final = _extract_final_answer(reasoning)
            new_query = _extract_new_query(reasoning)
            step_logs.append(
                {
                    "step": step,
                    "query": current_query,
                    "reasoning": reasoning,
                    "new_query": new_query,
                    "found_final": bool(final),
                }
            )
            if final:
                final_answer = final
                break
            if not new_query or new_query == current_query:
                break

            current_query = new_query
            iter_result = self.retriever.retrieve(
                graph=graph,
                chunks=chunks,
                question=current_query,
                top_k=top_k,
                involved_types=involved_types,  # type: ignore[arg-type]
            )
            retrieval_result = _merge_retrieval_results(retrieval_result, iter_result, top_k=top_k)
            final_answer = self.answer_gen.generate(question, retrieval_result)

        retrieval_result["reasoning_steps"] = step_logs
        retrieval_result["mode"] = normalized_mode
        return {
            "answer": final_answer,
            "sub_questions": sub_questions,
            "involved_types": involved_types,
            "retrieval": retrieval_result,
        }


def _build_retrieval_result(
    triples: list[str],
    chunk_ids: list[str],
    chunk_contents: list[str],
    paths: list[Any],
    top_k: int,
) -> dict[str, Any]:
    limit = max(top_k * 2, top_k)
    return {
        "triples": list(dict.fromkeys(triples))[:limit],
        "chunk_ids": list(dict.fromkeys(chunk_ids))[:limit],
        "chunk_contents": list(dict.fromkeys(chunk_contents))[:limit],
        "paths": paths[:limit],
    }


def _merge_retrieval_results(base: dict[str, Any], inc: dict[str, Any], top_k: int) -> dict[str, Any]:
    limit = max(top_k * 2, top_k)
    merged = {
        "triples": list(dict.fromkeys(list(base.get("triples", [])) + list(inc.get("triples", []))))[:limit],
        "chunk_ids": list(dict.fromkeys(list(base.get("chunk_ids", [])) + list(inc.get("chunk_ids", []))))[:limit],
        "chunk_contents": list(
            dict.fromkeys(list(base.get("chunk_contents", [])) + list(inc.get("chunk_contents", [])))
        )[:limit],
        "paths": list(base.get("paths", []))[:limit] + list(inc.get("paths", []))[:limit],
    }
    merged["paths"] = merged["paths"][:limit]
    return merged


def _build_context(retrieval_result: dict[str, Any]) -> str:
    triples = retrieval_result.get("triples", [])
    chunks = retrieval_result.get("chunk_contents", [])
    lines = ["=== Triples ===", *[str(x) for x in triples[:12]], "=== Chunks ===", *[str(x) for x in chunks[:8]]]
    return "\n".join(lines)


def _extract_final_answer(reasoning: str) -> str | None:
    match = re.search(r"so the answer is:\s*(.+)$", reasoning, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    candidate = match.group(1).strip()
    return candidate or None


def _extract_new_query(reasoning: str) -> str | None:
    match = re.search(r"the new query is:\s*(.+)$", reasoning, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    query = match.group(1).strip().splitlines()[0].strip()
    return query or None

