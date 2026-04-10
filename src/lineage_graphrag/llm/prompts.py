from __future__ import annotations


def build_answer_prompt(question: str, triples: list[str], chunks: list[str], impact_summary: str | None = None) -> str:
    prompt = [
        "You are a lineage analysis assistant. Answer only from the provided evidence.",
        f"Question: {question}",
        "Triples:",
        *triples[:8],
        "Chunks:",
        *chunks[:4],
    ]
    if impact_summary:
        prompt.append(f"Impact: {impact_summary}")
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
