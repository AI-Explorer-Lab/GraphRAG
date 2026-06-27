from __future__ import annotations


def build_answer_prompt(question: str, triples: list[str], chunks: list[str], impact_summary: str | None = None) -> str:
    prompt = [
        "You are a lineage analysis assistant. Answer only from the provided evidence.",
        "Use the same language as the question.",
        "Grounding rules:",
        "- Use only the triples and evidence chunks below; do not invent facts or node ids.",
        "- Cover all direct evidence categories that support the answer.",
        "- For why/risk questions, check ownership/path evidence, shared behavior or signal evidence, and rule/model/decision evidence before answering.",
        "- Mention important node ids and transition ids with backticks.",
        "- If the question is Chinese and named nodes are important, end with `关键证据节点：` followed by a short bullet list.",
        "- If the provided evidence is incomplete, say exactly what is missing instead of guessing.",
        f"Question: {question}",
        "Triples:",
        *(triples[:16] or ["None"]),
        "Evidence chunks:",
        *(chunks[:12] or ["None"]),
    ]
    if impact_summary:
        prompt.append(f"Impact: {impact_summary}")
    prompt.append("Write a concise, evidence-complete answer.")
    return "\n".join(prompt)


def build_decomposition_prompt(question: str, max_sub_questions: int = 3) -> str:
    return "\n".join(
        [
            "You are an expert at decomposing lineage questions into retrievable sub-questions.",
            f"Question: {question}",
            "Return only JSON in this format:",
            '{"sub_questions":[{"sub-question":"..."},{"sub-question":"..."}]}',
            f"Rules: return 1 to {max_sub_questions} sub-questions; keep each sub-question concrete and retrieval-friendly.",
        ]
    )


def build_ircot_prompt(
    original_question: str,
    current_query: str,
    context: str,
    thoughts: list[str],
    step: int,
    max_steps: int,
) -> str:
    joined_thoughts = " | ".join(thoughts[-4:]) if thoughts else "None"
    return "\n".join(
        [
            "You are running iterative retrieval chain-of-thought for lineage QA.",
            f"Original question: {original_question}",
            f"Current query: {current_query}",
            f"Step: {step}/{max_steps}",
            f"Previous thoughts: {joined_thoughts}",
            "Context:",
            context,
            "If enough evidence, end with: So the answer is: <answer>",
            "If evidence is insufficient, end with: The new query is: <better query>",
            "Keep reasoning short and evidence-driven.",
        ]
    )
