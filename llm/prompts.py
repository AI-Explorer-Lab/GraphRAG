from __future__ import annotations


def build_answer_prompt(question: str, triples: list[str], chunks: list[str], impact_summary: str | None = None) -> str:
    triple_limit = _evidence_fact_limit(question)
    chunk_limit = 10 if _needs_path_or_dependency_detail(question) else 8
    prompt = [
        "You are a business-facing graph risk analyst.",
        "Answer only from the provided evidence, but do not expose the evidence table itself.",
        "Use the same language as the question.",
        "",
        "Writing rules:",
        "- Give a synthesized business explanation, not a graph trace dump.",
        "- When mentioning a graph node, write the readable name followed by its node id in parentheses, for example `Felix Gao（usr_felix）`.",
        "- When mentioning a graph relationship and an edge id is available, include it in parentheses, for example `shared phone rule scores Felix（rule_scores_felix）`.",
        "- Preserve parenthesized identifiers from the evidence. If a bullet mentions a relationship, rule hit, model score, fund flow, ownership, or usage relation, include at least one related edge id in parentheses.",
        "- Never write labels such as `id:`, `node id:`, `edge id:`, or `ids:`.",
        "- Do not output arrow chains such as `A -> relation -> B`.",
        "- Parentheses are only for node ids or edge ids; never output empty parentheses.",
        "- Do not include a separate `Key evidence` or `关键证据` section unless the user explicitly asks for evidence IDs.",
        "- Adapt the answer structure to the user's question type; do not assume every question is about high-risk attribution.",
        "- Prefer 2-3 compact bullets when the question asks for causes, risks, impacts, or comparisons.",
        "- Mention only facts that directly explain the asked subject.",
        "- Do not use strong crime labels such as money laundering or fraud unless the evidence explicitly says so; prefer cautious wording such as suspicious fund flow, mule-account risk, shared-KYC risk, or abnormal transaction pattern.",
        "- For path questions, output the ordered path hop by hop. Do not summarize away intermediate nodes or relationship ids.",
        "- For model/feature dependency questions, separate inputs/features from affected targets. Affected targets include direct `scores` targets and direct `triggers` targets from the model/rule, but not second-hop downstream actions unless explicitly asked.",
        "- If the evidence is incomplete, say what is missing instead of guessing.",
        "",
        f"Question: {question}",
        "",
        "Evidence facts for grounding only. Read them, synthesize them, and do not copy them mechanically:",
        *(triples[:triple_limit] or ["None"]),
        "",
        "Supporting evidence notes for grounding only:",
        *(chunks[:chunk_limit] or ["None"]),
    ]
    if impact_summary:
        prompt.append(f"Impact summary: {impact_summary}")
    prompt.extend(_answer_shape_rules(question))
    prompt.append("Return the final answer only.")
    return "\n".join(prompt)


def _answer_shape_rules(question: str) -> list[str]:
    if not _contains_cjk(question):
        return [
            "",
            "Output shape:",
            "- Start with a direct answer to the specific question.",
            "- If the question asks why/risk/cause, group 2-3 bullets by business reason.",
            "- If the question asks path/impact/listing, use the structure that best answers that task.",
        ]
    return [
        "",
        "中文输出要求：",
        "- 第一句必须直接回答当前问题，不要套用固定主体或固定结论。",
        "- 提到节点时，用 `可读名称（node_id）`；提到关系且有边 ID 时，用 `关系描述（edge_id）`。",
        "- 保留证据中的括号标识；如果 bullet 提到了关系、规则命中、模型评分、资金流、持有或使用关系，至少保留一个对应的边 ID 括号。",
        "- 禁止写 `id:`、`node id:`、`edge id:`、`ids:` 这类标签。",
        "- 如果问题是在问“为什么高风险 / 风险原因 / 判定依据”，第一句概括该主体的主要原因；后面用 2 到 3 个短横线 bullet，每个 bullet 解释一类业务原因。",
        "- 如果问题是在问资金路径、影响范围、上下游依赖、子图结构或对比关系，就按对应任务组织答案，不要强行写成高风险归因。",
        "- 路径题必须按顺序逐跳写清楚，每一跳都保留节点括号 ID 和关系/边括号 ID；不要把中间节点或边省略成一句概括。",
        "- 模型/特征依赖题要分清“使用了哪些输入特征”和“影响了哪些对象”；影响对象包括模型/规则直接 `scores` 的对象，也包括直接 `triggers` 的对象，但除非问题明确问下游处置或影响链路，否则不要继续写冻结、SAR 等第二跳动作。",
        "- 风险归因类 bullet 名称可使用：`资金路径`、`共享身份信号`、`规则命中与处置`；其他问题请使用更贴合问题的名称。",
        "- 除非证据明确写出，否则不要直接定性为“洗钱”或“欺诈”；优先使用“异常资金流转风险”“共享 KYC 风险”“mule account 风险”“可疑交易模式”等审慎表达。",
        "- 不要写 `关键证据：` 这种附录式列表。",
        "- 不要逐条复述所有关系；只保留能回答问题的主线。",
    ]


def _evidence_fact_limit(question: str) -> int:
    if _needs_path_or_dependency_detail(question):
        return 28
    return 16


def _needs_path_or_dependency_detail(question: str) -> bool:
    lowered = question.lower()
    return any(
        token in lowered
        for token in (
            "路径",
            "资金路径",
            "链路",
            "上游",
            "下游",
            "影响哪些",
            "使用了哪些",
            "依赖",
            "path",
            "impact",
            "downstream",
            "upstream",
            "feature",
            "model",
        )
    )


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def build_decomposition_prompt(question: str, max_sub_questions: int = 3) -> str:
    return "\n".join(
        [
            "You are a graph QA retrieval planner.",
            "Decompose the user question into retrievable sub-questions that help answer the original task.",
            "Use business-readable names only.",
            "Do not output internal ids, id labels, node ids, chunk ids, or text like `id: xxx`.",
            "Do not expose graph implementation fields.",
            "For risk-cause questions, focus on direct signals, paths, rules/models, and relevant related-party risk.",
            "For path/impact/listing questions, focus on the entities and relationships needed for that task.",
            f"Question: {question}",
            "Return only JSON in this format:",
            '{"sub_questions":[{"sub-question":"..."},{"sub-question":"..."}]}',
            f"Rules: return 1 to {max_sub_questions} sub-questions; keep each sub-question concrete, natural, and retrieval-friendly.",
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
