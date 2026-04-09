from __future__ import annotations


def build_answer_prompt(question: str, triples: list[str], chunks: list[str], impact_summary: str | None = None) -> str:
    prompt = [
        "你是一个血缘分析助手，请基于证据回答问题。",
        f"问题: {question}",
        "Triples:",
        *triples[:8],
        "Chunks:",
        *chunks[:4],
    ]
    if impact_summary:
        prompt.append(f"Impact: {impact_summary}")
    return "\n".join(prompt)

