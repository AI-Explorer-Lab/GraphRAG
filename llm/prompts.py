from __future__ import annotations


def build_answer_prompt(question: str, triples: list[str], chunks: list[str], impact_summary: str | None = None) -> str:
    triple_limit = _evidence_fact_limit(question)
    chunk_limit = 10 if _needs_path_or_dependency_detail(question) else 8
    trace_ids_requested = _wants_trace_ids(question)
    prompt = [
        "You are a business-facing graph risk analyst.",
        "Answer only from the provided evidence, but do not expose the evidence table itself.",
        "Use the same language as the question.",
        "",
        "Writing rules:",
        "- Give a synthesized business explanation, not a graph trace dump.",
        "- When mentioning a graph node, write the readable name followed by its node id in parentheses, for example `Felix Gao（usr_felix）`.",
        "- Do not include edge ids, transition ids, or raw trace ids in the answer unless the user explicitly asks for evidence ids.",
        "- Never output raw trace tokens such as `tr::...`, `transition::...`, `::transfers_to_2`, `::scores_17`, or arrow-form edge ids.",
        "- Never write labels such as `id:`, `node id:`, `edge id:`, or `ids:`.",
        "- Do not output arrow chains such as `A -> relation -> B`.",
        "- Parentheses are only for node ids in normal answers; never output empty parentheses.",
        "- Do not include a separate `Key evidence` or `关键证据` section unless the user explicitly asks for evidence IDs.",
        "- Adapt the answer structure to the user's question type; do not assume every question is about high-risk attribution.",
        "- Prefer 2-3 compact bullets when the question asks for causes, risks, impacts, or comparisons.",
        "- Mention only facts that directly explain the asked subject.",
        "- Do not use strong crime labels such as money laundering or fraud unless the evidence explicitly says so; prefer cautious wording such as suspicious fund flow, mule-account risk, shared-KYC risk, or abnormal transaction pattern.",
        "- For path questions, output the ordered path hop by hop. Do not summarize away intermediate nodes.",
        "- For model/feature dependency questions, separate inputs/features from affected targets. Affected targets include direct `scores` targets and direct `triggers` targets from the model/rule, but not second-hop downstream actions unless explicitly asked.",
        "- If the evidence is incomplete, say what is missing instead of guessing.",
        (
            "- The user asked for evidence ids, so you may add a short final evidence-id line. Keep the main explanation business-readable."
            if trace_ids_requested
            else "- The user did not ask for evidence ids, so keep trace ids internal and do not output them."
        ),
        "",
        f"Question: {question}",
        "",
        "Business facts for grounding only. Read them, synthesize them, and do not copy them mechanically:",
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
        "- 提到节点时，用 `可读名称（node_id）`。",
        "- 默认不要输出边 ID、transition ID 或底层 trace ID；除非用户明确要求证据 ID。",
        "- 禁止输出 `tr::...`、`transition::...`、`::transfers_to_2`、`::scores_17` 这类原始追踪标识。",
        "- 禁止写 `id:`、`node id:`、`edge id:`、`ids:` 这类标签。",
        "- 如果问题是在问“为什么高风险 / 风险原因 / 判定依据”，第一句概括该主体的主要原因；后面用 2 到 3 个短横线 bullet，每个 bullet 解释一类业务原因。",
        "- 如果问题是在问资金路径、影响范围、上下游依赖、子图结构或对比关系，就按对应任务组织答案，不要强行写成高风险归因。",
        "- 路径题必须按顺序逐跳写清楚，保留中间节点，但不要输出底层边 ID。",
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


def _wants_trace_ids(question: str) -> bool:
    lowered = question.lower()
    return any(
        token in lowered
        for token in (
            "edge id",
            "edge ids",
            "trace id",
            "trace ids",
            "transition id",
            "transition ids",
            "evidence id",
            "evidence ids",
            "证据id",
            "证据 id",
            "边id",
            "边 id",
            "关系id",
            "关系 id",
            "追踪id",
            "追踪 id",
        )
    )


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def build_impact_prompt(
    scenario: str,
    change_target: str,
    change_relation: str,
    direct_impacts: list[str],
    indirect_impacts: list[str],
    scoped_impact: list[str],
    target_impact: list[str],
    evidence_facts: list[str],
    language: str | None = None,
) -> str:
    if _wants_chinese(language, scenario):
        return _build_chinese_impact_prompt(
            scenario=scenario,
            change_target=change_target,
            change_relation=change_relation,
            direct_impacts=direct_impacts,
            indirect_impacts=indirect_impacts,
            scoped_impact=scoped_impact,
            target_impact=target_impact,
            evidence_facts=evidence_facts,
        )
    language_rule = (
        "The scenario is Chinese. Answer entirely in Chinese; do not use English sentences."
        if _contains_cjk(scenario)
        else "Answer in English."
    )
    return "\n".join(
        [
            "You are a business-facing graph impact analyst.",
            "Explain the what-if impact using only the provided graph impact result.",
            "Do not add facts that are not supported by the impact paths.",
            language_rule,
            "",
            "Writing rules:",
            "- Start with one direct conclusion about what is affected.",
            "- Then write 2 to 3 compact bullets.",
            "- Each bullet should explain: affected area, evidence meaning, and business consequence.",
            "- Mention node ids and edge ids in parentheses when they are present in the evidence.",
            "- Never write labels such as `id:`, `node id:`, `edge id:`, or `ids:`.",
            "- Do not output a separate evidence checklist.",
            "- Do not copy the raw direct/indirect lists mechanically.",
            "- Use cautious wording such as may affect, may reduce, may delay, or needs re-evaluation.",
            "- Do not claim missed true risk, fraud, or money laundering unless the evidence explicitly says so.",
            "",
            f"Scenario: {scenario}",
            f"Changed target: {change_target}",
            f"Change relation/type: {change_relation}",
            f"Direct impacts: {', '.join(direct_impacts) if direct_impacts else 'None'}",
            f"Indirect impacts: {', '.join(indirect_impacts) if indirect_impacts else 'None'}",
            f"Scoped impacts: {', '.join(scoped_impact) if scoped_impact else 'None'}",
            f"Target impact paths: {'; '.join(target_impact) if target_impact else 'None'}",
            "",
            "Evidence impact paths:",
            *(evidence_facts or ["None"]),
            "",
            "Return the final answer only.",
        ]
    )


def _wants_chinese(language: str | None, text: str) -> bool:
    if language and language.strip().lower() in {"zh", "zh-cn", "cn", "chinese", "中文"}:
        return True
    return _contains_cjk(text)


def _build_chinese_impact_prompt(
    scenario: str,
    change_target: str,
    change_relation: str,
    direct_impacts: list[str],
    indirect_impacts: list[str],
    scoped_impact: list[str],
    target_impact: list[str],
    evidence_facts: list[str],
) -> str:
    return "\n".join(
        [
            "你是面向业务人员的图谱影响分析助手。",
            "请只根据下面的图谱影响分析结果解释 what-if 场景，不要补充证据之外的事实。",
            "必须全程使用中文回答，不要输出英文句子。",
            "",
            "写作要求：",
            "- 第一句直接给结论，说明这个变化会影响哪些核心对象或流程。",
            "- 后面写 2 到 3 个简短 bullet。",
            "- 每个 bullet 按“影响对象/环节 + 证据含义 + 业务后果”的方式解释。",
            "- 提到节点时保留括号中的 node id；提到关系时保留括号中的 edge id。",
            "- 禁止写 `id:`、`node id:`、`edge id:`、`ids:` 这类标签。",
            "- 不要单独列证据清单，也不要机械复述 direct/indirect 列表。",
            "- 用“可能影响、可能减少、可能延迟、需要重新评估”等审慎表达。",
            "- 除非证据明确说明，否则不要说洗钱、欺诈、漏检真实风险。",
            "",
            f"场景：{scenario}",
            f"变化对象：{change_target}",
            f"变化类型：{change_relation}",
            f"直接影响：{', '.join(direct_impacts) if direct_impacts else '无'}",
            f"间接影响：{', '.join(indirect_impacts) if indirect_impacts else '无'}",
            f"范围内影响：{', '.join(scoped_impact) if scoped_impact else '无'}",
            f"目标影响路径：{'; '.join(target_impact) if target_impact else '无'}",
            "",
            "图谱影响路径：",
            *(evidence_facts or ["无"]),
            "",
            "只返回最终答案。",
        ]
    )


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
