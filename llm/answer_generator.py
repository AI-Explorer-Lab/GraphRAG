from __future__ import annotations

import json
import re
from typing import Any

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
        id_to_name = {
            **_normalize_name_map(retrieval_result.get("node_names", {})),
            **_collect_entity_names(retrieval_result.get("chunk_contents", [])),
        }
        edge_ids = {
            **_collect_edge_ids(retrieval_result.get("chunk_contents", [])),
            **_normalize_edge_id_map(retrieval_result.get("edge_ids", {})),
        }
        readable_triples = _format_readable_triples(triples, id_to_name, edge_ids)
        chunks = _format_evidence_chunks(chunk_ids, retrieval_result.get("chunk_contents", []), id_to_name)
        impact_summary = None
        if impact_report:
            impact_summary = (
                f"direct={len(impact_report.direct_impacts)}, "
                f"indirect={len(impact_report.indirect_impacts)}, "
                f"scoped={len(impact_report.scoped_impact)}"
            )
        prompt = build_answer_prompt(question, readable_triples, chunks, impact_summary)
        llm_answer = self.llm_client.generate(
            prompt=prompt,
            system_prompt=(
                "You are a strict graph analysis assistant. Answer only from provided evidence. "
                "Preserve node ids and edge ids in parentheses, but never write labels like id:."
            ),
        )
        if llm_answer and not _looks_like_prompt_echo(llm_answer):
            return _clean_answer(_normalize_answer_markdown(llm_answer), id_to_name)

        return _build_local_answer(question, readable_triples, chunks, impact_report)


def _format_evidence_chunks(chunk_ids: list[str], chunk_contents: list[str], id_to_name: dict[str, str]) -> list[str]:
    formatted: list[str] = []
    for index, content in enumerate(chunk_contents):
        chunk_id = chunk_ids[index] if index < len(chunk_ids) else ""
        formatted.append(_format_readable_chunk(content, chunk_id, id_to_name))
    return formatted


def _collect_entity_names(chunk_contents: list[str]) -> dict[str, str]:
    names: dict[str, str] = {}
    for content in chunk_contents:
        payload = _parse_json_dict(content)
        if not payload:
            continue
        entity_id = _clean_str(payload.get("id") or payload.get("entity_id"))
        name = _clean_str(payload.get("name"))
        if entity_id and name:
            names[entity_id] = name
    return names


def _normalize_name_map(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {
        str(key).strip(): str(value).strip()
        for key, value in raw.items()
        if str(key).strip() and str(value).strip()
    }


def _collect_edge_ids(chunk_contents: list[str]) -> dict[tuple[str, str, str], str]:
    edge_ids: dict[tuple[str, str, str], str] = {}
    for content in chunk_contents:
        payload = _parse_json_dict(content)
        if not payload:
            continue
        edge_id = _clean_str(payload.get("id"))
        source = _clean_str(payload.get("source"))
        relation = _clean_str(payload.get("relation"))
        target = _clean_str(payload.get("target"))
        if edge_id and source and relation and target:
            edge_ids[(source, relation, target)] = edge_id
    return edge_ids


def _normalize_edge_id_map(raw: Any) -> dict[tuple[str, str, str], str]:
    if not isinstance(raw, dict):
        return {}
    edge_ids: dict[tuple[str, str, str], str] = {}
    for triple, edge_id in raw.items():
        parsed = _parse_triple(triple)
        value = _clean_str(edge_id)
        if parsed is not None and value:
            edge_ids[parsed] = value
    return edge_ids


def _format_readable_triples(
    triples: list[str],
    id_to_name: dict[str, str],
    edge_ids: dict[tuple[str, str, str], str],
) -> list[str]:
    readable: list[str] = []
    for triple in triples:
        parsed = _parse_triple(triple)
        if parsed is None:
            readable.append(_replace_known_ids(str(triple), id_to_name, include_ids=True))
            continue
        source, relation, target = parsed
        readable.append(
            _relationship_sentence(
                _node_ref(source, id_to_name),
                relation,
                _node_ref(target, id_to_name),
                edge_ids.get((source, relation, target), ""),
            )
        )
    return readable


def _format_readable_chunk(content: str, chunk_id: str, id_to_name: dict[str, str]) -> str:
    payload = _parse_json_dict(content)
    if not payload:
        return _replace_known_ids(str(content), id_to_name, include_ids=True)

    if chunk_id.startswith("transition::") or {"source", "target", "relation"}.issubset(payload.keys()):
        source_id = _clean_str(payload.get("source"))
        target_id = _clean_str(payload.get("target"))
        source = _node_ref(source_id, id_to_name)
        target = _node_ref(target_id, id_to_name)
        relation = _clean_str(payload.get("relation"))
        edge_id = _clean_str(payload.get("id")) or chunk_id.removeprefix("transition::")
        props = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}
        reason = _clean_str(props.get("reason") or props.get("description") or payload.get("description"))
        return _join_parts([_relationship_sentence(source, relation, target, edge_id), reason])

    if chunk_id.startswith("subgraph::") or "children" in payload:
        name = _node_ref(_clean_str(payload.get("entity_id") or payload.get("id")), id_to_name)
        children = payload.get("children") if isinstance(payload.get("children"), list) else []
        child_names = [_node_ref(str(child), id_to_name) for child in children[:6]]
        description = _clean_str(payload.get("description"))
        return _join_parts([f"{name} 包含：{', '.join(child_names)}" if child_names else name, description])

    name = _node_ref(_clean_str(payload.get("id")), id_to_name) if payload.get("id") else _clean_str(payload.get("name"))
    description = _clean_str(payload.get("description"))
    props = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}
    entity_type = _clean_str(props.get("type") or props.get("schema_type"))
    return _join_parts([name, f"类型：{entity_type}" if entity_type else "", description])


def _build_local_answer(
    question: str,
    readable_triples: list[str],
    chunks: list[str],
    impact_report: ImpactReport | None = None,
) -> str:
    chinese = _contains_cjk(question)
    if not readable_triples and not chunks:
        return "没有检索到足够证据，请补充问题中的主体或关系。" if chinese else "No evidence was retrieved. Please refine the query."

    if chinese:
        lines = [_conclusion_sentence(question)]
        category_lines = _categorize_evidence(readable_triples)
        if category_lines:
            lines.extend(category_lines)
        else:
            for item in readable_triples[:4]:
                lines.append(f"- {item}")
        for chunk in chunks[:3]:
            if chunk and chunk not in "\n".join(lines):
                lines.append(f"- 补充信息：{chunk}")
        if impact_report:
            lines.append(
                "- 影响范围："
                f"直接影响 {len(impact_report.direct_impacts)} 项，"
                f"间接影响 {len(impact_report.indirect_impacts)} 项，"
                f"范围内影响 {len(impact_report.scoped_impact)} 项。"
            )
        return "\n".join(lines)

    lines = ["Based on the retrieved graph evidence:"]
    for item in readable_triples[:5]:
        lines.append(f"- {item}")
    for chunk in chunks[:3]:
        lines.append(f"- {chunk}")
    return "\n".join(lines)


def _categorize_evidence(readable_triples: list[str]) -> list[str]:
    buckets: dict[str, list[str]] = {
        "资金路径": [],
        "共享身份信号": [],
        "规则命中与处置": [],
    }
    for triple in readable_triples:
        lowered = triple.lower()
        if any(token in lowered for token in ("钱包", "账户", "交易", "转账", "资金", "wallet", "account", "transfer")):
            buckets["资金路径"].append(triple)
        elif any(token in lowered for token in ("设备", "手机", "手机号", "device", "phone")):
            buckets["共享身份信号"].append(triple)
        elif any(token in lowered for token in ("规则", "审核", "处置", "冻结", "rule", "review", "freeze", "scores", "triggers")):
            buckets["规则命中与处置"].append(triple)

    lines: list[str] = []
    for label, items in buckets.items():
        if items:
            lines.append(f"- {label}：{_merge_fact_fragments(items[:2])}。")
    return lines


def _looks_like_prompt_echo(text: str) -> bool:
    lowered = text.lower()
    markers = [
        "回答格式要求",
        "grounding rules",
        "internal evidence map",
        "output shape",
        "中文输出格式",
        "中文输出要求",
        "matched relations",
        "evidence chunks",
        "evidence facts for grounding",
    ]
    return any(marker in lowered for marker in markers) or text.strip().startswith("Question:")


def _clean_answer(text: str, id_to_name: dict[str, str]) -> str:
    cleaned = _replace_known_ids(text, id_to_name, include_ids=True)
    cleaned = re.sub(r"\s*\((?:id|ids)\s*:\s*[^)]*\)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:id|ids)\s*:\s*[\w:.-]+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:node\s+id|edge\s+id)\s*:\s*[\w:.-]+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"`([A-Za-z]+_[A-Za-z0-9_]+)`", r"\1", cleaned)
    cleaned = _remove_trace_section(cleaned)
    cleaned = _remove_empty_parentheses(cleaned)
    cleaned = cleaned.replace("转入/流向", "流向").replace("评分/命中", "评分命中")
    cleaned = cleaned.replace("洗钱行为", "异常资金流转风险")
    cleaned = cleaned.replace("洗钱或欺诈风险模式", "异常资金流转或 mule account 风险模式")
    cleaned = cleaned.replace("合成风险", "共享 KYC 风险")
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def _replace_known_ids(text: str, id_to_name: dict[str, str], include_ids: bool = False) -> str:
    replaced = str(text)
    for entity_id, name in sorted(id_to_name.items(), key=lambda item: len(item[0]), reverse=True):
        if not entity_id or not name:
            continue
        replacement = f"{name}（{entity_id}）" if include_ids else name
        pattern = rf"(?<![（(])`?{re.escape(entity_id)}`?(?![)）])"
        replaced = re.sub(pattern, replacement, replaced)
    return replaced


def _parse_json_dict(content: Any) -> dict[str, Any]:
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        return {}
    try:
        payload = json.loads(content)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_triple(triple: Any) -> tuple[str, str, str] | None:
    parts = [part.strip() for part in str(triple).strip().strip("()").split(",")]
    if len(parts) != 3 or not all(parts):
        return None
    return parts[0], parts[1], parts[2]


def _display_name(value: str, id_to_name: dict[str, str]) -> str:
    value = _clean_str(value)
    if not value:
        return "未知节点"
    return id_to_name.get(value, _prettify_identifier(value))


def _node_ref(value: str, id_to_name: dict[str, str]) -> str:
    node_id = _clean_str(value)
    if not node_id:
        return "未知节点"
    name = id_to_name.get(node_id, _prettify_identifier(node_id))
    if name == node_id or name.endswith(f"（{node_id}）"):
        return name
    return f"{name}（{node_id}）"


def _prettify_identifier(value: str) -> str:
    cleaned = value.strip().strip("`")
    prefixes = {
        "usr_": "",
        "acct_": "",
        "wallet_": "",
        "phone_": "",
        "dev_": "",
        "rule_": "",
        "dec_": "",
        "act_": "",
        "txn_": "",
        "biz_": "",
        "mch_": "",
        "feat_": "",
        "mdl_": "",
        "src_": "",
        "report_": "",
    }
    for prefix, replacement in prefixes.items():
        if cleaned.startswith(prefix):
            cleaned = replacement + cleaned[len(prefix) :]
            break
    return cleaned.replace("_", " ").strip() or value


def _relation_label(relation: str) -> str:
    labels = {
        "owns": "持有",
        "uses": "使用",
        "transfers_to": "流向",
        "provides_to": "提供给",
        "scores": "评分命中",
        "triggers": "触发",
        "has": "包含",
    }
    relation = _clean_str(relation)
    return labels.get(relation, relation.replace("_", " "))


def _relationship_sentence(source: str, relation: str, target: str, edge_id: str = "") -> str:
    relation = _clean_str(relation)
    if relation == "owns":
        text = f"{source}持有{target}"
    elif relation == "uses":
        text = f"{source}使用{target}"
    elif relation == "transfers_to":
        text = f"资金从{source}流向{target}"
    elif relation == "provides_to":
        text = f"{source}为{target}提供输入"
    elif relation == "scores":
        text = f"{source}对{target}评分命中"
    elif relation == "triggers":
        text = f"{source}触发{target}"
    elif relation == "has":
        text = f"{source}包含{target}"
    else:
        text = f"{source}{_relation_label(relation)}{target}"
    return f"{text}（{edge_id}）" if edge_id else text


def _merge_fact_fragments(items: list[str]) -> str:
    return "；".join(item.rstrip("。") for item in items)


def _conclusion_sentence(question: str) -> str:
    if any(token in question for token in ("为什么", "原因", "高风险", "判定依据", "风险")):
        subject = _subject_hint(question)
        if subject:
            return f"{subject} 的风险判断主要由检索到的身份信号、资金关系和规则/模型结果共同支撑。"
        return "该风险判断主要由检索到的身份信号、资金关系和规则/模型结果共同支撑。"
    return "根据检索到的图谱证据，可以归纳出以下业务原因。"


def _subject_hint(question: str) -> str:
    cleaned = re.sub(r"\s+", " ", question).strip()
    match = re.search(r"([A-Za-z][A-Za-z0-9]*(?:\s+[A-Za-z][A-Za-z0-9]*){0,3})", cleaned)
    if match:
        return match.group(1).strip()
    for splitter in ("为什么", "为何", "的", "会", "被"):
        if splitter in cleaned:
            candidate = cleaned.split(splitter, 1)[0].strip(" ，,。?？")
            if candidate:
                return candidate
    return ""


def _remove_trace_section(text: str) -> str:
    lines = text.splitlines()
    kept: list[str] = []
    skipping = False
    for line in lines:
        stripped = line.strip()
        if stripped in {"关键证据：", "关键证据:", "Key evidence:", "Key evidence："}:
            skipping = True
            continue
        if skipping:
            if not stripped:
                continue
            if stripped.startswith("-"):
                continue
            skipping = False
        kept.append(line)
    return "\n".join(kept)


def _remove_empty_parentheses(text: str) -> str:
    cleaned = re.sub(r"[（(]\s*[)）]", "", text)
    return cleaned


def _join_parts(parts: list[str]) -> str:
    return "；".join(part for part in parts if part)


def _clean_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


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
