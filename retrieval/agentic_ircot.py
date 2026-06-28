from __future__ import annotations

import re
from typing import Any

import networkx as nx

from config import AppConfig
from llm.answer_generator import AnswerGenerator
from llm.prompts import build_ircot_prompt
from retrieval.decomposer import GraphQuestionDecomposer
from retrieval.orchestrator import GraphRetriever


class AgenticIRCoT:
    def __init__(
        self,
        decomposer: GraphQuestionDecomposer,
        retriever: GraphRetriever,
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
            decomposer=GraphQuestionDecomposer.from_config(cfg),
            retriever=GraphRetriever.from_config(cfg),
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
        subquery_results: list[dict[str, Any]] = []
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
            subquery_results.append(result)
            step_logs.append(
                {
                    "step": 0,
                    "sub_question": sub_text,
                    "triples": len(result.get("triples", [])),
                    "chunks": len(result.get("chunk_contents", [])),
                    "mode": "decomposition_retrieval",
                }
            )

        if subquery_results:
            retrieval_result = _build_retrieval_result_from_results(subquery_results, top_k=top_k)
        else:
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


def _build_retrieval_result_from_results(results: list[dict[str, Any]], top_k: int) -> dict[str, Any]:
    limit = _evidence_limit(top_k, result_count=len(results))
    chunk_pairs_by_result = [
        list(zip(result.get("chunk_ids", []), result.get("chunk_contents", []))) for result in results
    ]
    paths: list[Any] = []
    for result in results:
        paths.extend(result.get("paths", []))
    chunk_pairs = _round_robin_unique_pairs(chunk_pairs_by_result, limit=limit)

    return {
        "triples": _round_robin_unique([result.get("triples", []) for result in results], limit=limit),
        "chunk_ids": [cid for cid, _ in chunk_pairs],
        "chunk_contents": [content for _, content in chunk_pairs],
        "paths": paths[:limit],
    }


def _merge_retrieval_results(base: dict[str, Any], inc: dict[str, Any], top_k: int) -> dict[str, Any]:
    limit = _evidence_limit(top_k, result_count=2)
    chunk_pairs = [
        list(zip(base.get("chunk_ids", []), base.get("chunk_contents", []))),
        list(zip(inc.get("chunk_ids", []), inc.get("chunk_contents", []))),
    ]
    merged_chunk_pairs = _round_robin_unique_pairs(chunk_pairs, limit=limit)
    merged = {
        "triples": _round_robin_unique([base.get("triples", []), inc.get("triples", [])], limit=limit),
        "chunk_ids": [cid for cid, _ in merged_chunk_pairs],
        "chunk_contents": [content for _, content in merged_chunk_pairs],
        "paths": list(base.get("paths", []))[:limit] + list(inc.get("paths", []))[:limit],
    }
    merged["paths"] = merged["paths"][:limit]
    return merged


def _build_context(retrieval_result: dict[str, Any]) -> str:
    triples = retrieval_result.get("triples", [])
    chunks = retrieval_result.get("chunk_contents", [])
    chunk_ids = retrieval_result.get("chunk_ids", [])
    formatted_chunks = []
    for index, chunk in enumerate(chunks[:12]):
        if index < len(chunk_ids):
            formatted_chunks.append(f"[{chunk_ids[index]}] {chunk}")
        else:
            formatted_chunks.append(str(chunk))
    lines = ["=== Triples ===", *[str(x) for x in triples[:16]], "=== Chunks ===", *formatted_chunks]
    return "\n".join(lines)


def _evidence_limit(top_k: int, result_count: int = 1) -> int:
    return min(max(top_k * max(2, result_count), top_k), 50)


def _round_robin_unique(groups: list[list[Any]], limit: int) -> list[Any]:
    selected: list[Any] = []
    seen: set[str] = set()
    max_len = max((len(group) for group in groups), default=0)
    for index in range(max_len):
        for group in groups:
            if index >= len(group):
                continue
            item = group[index]
            key = str(item)
            if key in seen:
                continue
            seen.add(key)
            selected.append(item)
            if len(selected) >= limit:
                return selected
    return selected


def _round_robin_unique_pairs(groups: list[list[tuple[Any, Any]]], limit: int) -> list[tuple[Any, Any]]:
    selected: list[tuple[Any, Any]] = []
    seen: set[str] = set()
    max_len = max((len(group) for group in groups), default=0)
    for index in range(max_len):
        for group in groups:
            if index >= len(group):
                continue
            key_item, value_item = group[index]
            key = str(key_item)
            if key in seen:
                continue
            seen.add(key)
            selected.append((key_item, value_item))
            if len(selected) >= limit:
                return selected
    return selected


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
