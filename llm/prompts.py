from __future__ import annotations


def build_answer_prompt(question: str, triples: list[str], chunks: list[str], impact_summary: str | None = None) -> str:
    checklist = _build_evidence_checklist(triples)
    prompt = [
        "You are a graph analysis assistant. Answer only from the provided evidence.",
        "Use the same language as the question.",
        "Grounding rules:",
        "- Use only the triples and evidence chunks below; do not invent facts or node ids.",
        "- Prefer direct evidence for the named subject; use related-subject evidence only when it explains a shared signal or direct path.",
        "- Do not cite every retrieved triple. Omit adjacent model/account evidence when it does not directly explain the named subject.",
        "- For why/risk questions, cover wallet/account ownership and path evidence, shared device/phone evidence, and rule/decision evidence when present.",
        "- If a named subject has an `owns` triple to a wallet or account in the evidence, include that triple in the answer.",
        "- Do not use Markdown numbered lists. Use short paragraphs or `-` bullets only.",
        "- Do not copy internal evidence-map labels such as Ownership/account/wallet evidence into the answer.",
        "- Mention important node ids and transition ids with backticks.",
        "- If the question is Chinese, write natural Chinese. Do not output English section names.",
        "- If the question is Chinese and named nodes are important, end with `关键证据节点：` followed by a short bullet list.",
        "- If the provided evidence is incomplete, say exactly what is missing instead of guessing.",
        f"Question: {question}",
        "Internal evidence map; use for grounding, but do not copy these labels into the answer:",
        *(checklist or ["None"]),
        "Triples:",
        *(triples[:16] or ["None"]),
        "Evidence chunks:",
        *(chunks[:12] or ["None"]),
    ]
    if impact_summary:
        prompt.append(f"Impact: {impact_summary}")
    prompt.extend(_answer_shape_rules(question))
    prompt.append("Write a concise, evidence-complete answer.")
    return "\n".join(prompt)


def _build_evidence_checklist(triples: list[str]) -> list[str]:
    ownership: list[str] = []
    shared_signals: list[str] = []
    controls: list[str] = []
    other_path: list[str] = []

    for triple in triples[:24]:
        parsed = _parse_triple(triple)
        if parsed is None:
            continue
        source, relation, target = parsed
        lowered = f"{source} {relation} {target}".lower()
        formatted = f"- {triple}"
        if relation in {"scores", "triggers"} or any(
            token in lowered for token in ("rule", "model", "decision", "dec_", "mdl_")
        ):
            controls.append(formatted)
        elif relation == "owns" or any(token in lowered for token in ("wallet", "account", "acct_")):
            ownership.append(formatted)
        elif relation == "uses" or any(token in lowered for token in ("phone", "device", "signal", "dev_")):
            shared_signals.append(formatted)
        elif relation in {"transfers_to", "provides_to"}:
            other_path.append(formatted)

    checklist: list[str] = []
    if ownership:
        checklist.append("Ownership/account/wallet evidence:")
        checklist.extend(_unique_limited(ownership, limit=4))
    if shared_signals:
        checklist.append("Shared behavior/signal evidence:")
        checklist.extend(_unique_limited(shared_signals, limit=4))
    if controls:
        checklist.append("Rule/model/decision evidence:")
        checklist.extend(_unique_limited(controls, limit=5))
    if other_path:
        checklist.append("Path/input evidence:")
        checklist.extend(_unique_limited(other_path, limit=4))
    return checklist


def _answer_shape_rules(question: str) -> list[str]:
    if not _contains_cjk(question):
        return [
            "Output shape:",
            "- Start with a one-sentence answer.",
            "- Then use 2-4 short `-` bullets for the main evidence categories.",
            "- End with `Key evidence nodes:` when node ids are important.",
        ]
    return [
        "中文输出格式：",
        "- 第一句直接回答结论，例如：`Felix Gao 被判定为高风险，主要由三类证据共同支持。`",
        "- 然后用 2 到 4 个短横线 bullet 说明原因；不要使用 `1.`、`2.`、`一、` 这类编号。",
        "- 对本类风险归因问题，优先使用这些中文 bullet 名称：`钱包与资金路径`、`共享设备和手机号`、`规则与处置`。",
        "- 每个 bullet 只写关键证据，不展开无关的下游模型或其他主体评分。",
        "- 最后输出 `关键证据节点：`，下面用短横线列出节点或 transition id。",
    ]


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _parse_triple(triple: str) -> tuple[str, str, str] | None:
    parts = [part.strip() for part in triple.strip().strip("()").split(",")]
    if len(parts) != 3 or not all(parts):
        return None
    return parts[0], parts[1], parts[2]


def _unique_limited(items: list[str], limit: int) -> list[str]:
    return list(dict.fromkeys(items))[:limit]


def build_decomposition_prompt(question: str, max_sub_questions: int = 3) -> str:
    return "\n".join(
        [
            "You are an expert at decomposing graph questions into retrievable sub-questions.",
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
            "You are running iterative retrieval chain-of-thought for graph QA.",
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
