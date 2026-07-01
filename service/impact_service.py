from __future__ import annotations

from typing import Any

import networkx as nx

from config import AppConfig
from domain.req import ImpactRequest
from exceptions import NotFoundException
from impact.propagation import ImpactAnalyzer
from llm.client import LLMClient, LLMSettings
from llm.prompts import build_impact_prompt
from mapper.graph_repository import GraphRepository


class ImpactService:
    def __init__(self, repo: GraphRepository, cfg: AppConfig, llm_client: LLMClient | None = None) -> None:
        self.repo = repo
        self.cfg = cfg
        self.llm_client = llm_client or LLMClient(
            LLMSettings(
                provider=cfg.llm_provider,
                model=cfg.llm_model,
                api_key=cfg.openai_api_key,
                base_url=cfg.openai_base_url,
                timeout_seconds=cfg.openai_timeout_seconds,
            )
        )

    def what_if_impact(self, payload: ImpactRequest) -> dict:
        graph = self.repo.get_graph(payload.graph_id)
        if graph is None:
            raise NotFoundException(f"graph_id '{payload.graph_id}' not built")

        analyzer = ImpactAnalyzer()
        report = analyzer.analyze(
            graph=graph,
            change_spec=payload.change_spec,
            target_node_id=payload.target_node_id,
        )
        report.answer, report.answer_source, report.llm_called = self._summarize_impact(graph, payload, report)
        return report.model_dump()

    def _summarize_impact(self, graph: nx.MultiDiGraph, payload: ImpactRequest, report: Any) -> tuple[str, str, bool]:
        scenario = _impact_question(payload)
        evidence_facts = _impact_evidence_facts(graph, report.evidence_paths)
        prompt = build_impact_prompt(
            scenario=scenario,
            change_target=_node_ref(graph, payload.change_spec.target),
            change_relation=payload.change_spec.relation,
            direct_impacts=[_node_ref(graph, node) for node in report.direct_impacts],
            indirect_impacts=[_node_ref(graph, node) for node in report.indirect_impacts],
            scoped_impact=[_node_ref(graph, node) for node in report.scoped_impact],
            target_impact=report.target_impact,
            evidence_facts=evidence_facts,
            language=payload.language,
        )
        llm_called = self.llm_client.is_available()
        llm_answer = self.llm_client.generate(
            prompt=prompt,
            system_prompt=_impact_system_prompt(scenario, payload.language),
            max_output_tokens=700,
        )
        if llm_answer:
            return llm_answer.strip(), "llm", llm_called
        return _local_impact_summary(scenario, report, graph), "local_fallback", llm_called


def _impact_question(payload: ImpactRequest) -> str:
    for value in (payload.scenario, payload.question):
        if value and value.strip():
            return value.strip()
    target = payload.change_spec.target
    relation = payload.change_spec.relation
    if _contains_cjk(target + relation):
        return f"如果 {target} 发生 {relation} 变化，会影响什么？"
    return f"What downstream impacts occur if {target} changes via {relation}?"


def _impact_system_prompt(scenario: str, language: str | None = None) -> str:
    if _wants_chinese(language, scenario):
        return (
            "你是严格的图谱影响分析助手。"
            "只能根据提供的影响路径解释。"
            "必须全程使用中文。"
            "保留括号中的节点 ID 和关系 ID，但不要写 id: 这类标签。"
        )
    return (
        "You are a strict graph impact analysis assistant. "
        "Explain only from provided impact paths. "
        "Preserve parenthesized node ids and edge ids, but never write labels like id:."
    )


def _wants_chinese(language: str | None, text: str) -> bool:
    if language and language.strip().lower() in {"zh", "zh-cn", "cn", "chinese", "中文"}:
        return True
    return _contains_cjk(text)


def _impact_evidence_facts(graph: nx.MultiDiGraph, paths: list[Any]) -> list[str]:
    facts: list[str] = []
    seen: set[str] = set()
    for path in paths:
        nodes = list(path.path)
        relations = list(path.relations)
        if len(nodes) < 2:
            continue
        hops: list[str] = []
        for index, relation in enumerate(relations):
            if index + 1 >= len(nodes):
                continue
            source = nodes[index]
            target = nodes[index + 1]
            edge_id = _edge_id(graph, source, target, relation)
            edge_suffix = f" ({edge_id})" if edge_id else ""
            hops.append(f"{_node_ref(graph, source)} --{relation}{edge_suffix}--> {_node_ref(graph, target)}")
        if not hops:
            continue
        fact = f"depth {path.depth}: " + " ; ".join(hops)
        if fact in seen:
            continue
        seen.add(fact)
        facts.append(fact)
    return facts


def _edge_id(graph: nx.MultiDiGraph, source: str, target: str, relation: str) -> str:
    edge_bundle = graph.get_edge_data(source, target, default={})
    for edge_data in edge_bundle.values():
        if str(edge_data.get("relation", "")).lower() != str(relation).lower():
            continue
        rel_props = edge_data.get("relation_properties", {})
        if isinstance(rel_props, dict):
            transition_id = str(rel_props.get("transition_id", "")).strip()
            if transition_id:
                return transition_id
        for ref in edge_data.get("evidence_refs", []) or []:
            ref_text = str(ref)
            if ref_text.startswith("transition::"):
                return ref_text.removeprefix("transition::")
    return ""


def _node_ref(graph: nx.MultiDiGraph, node_id: str) -> str:
    props = graph.nodes.get(node_id, {}).get("properties", {})
    name = str(props.get("name", "")).strip()
    if not name or _looks_mojibake(name):
        name = _prettify_identifier(node_id)
    if name == node_id:
        return node_id
    return f"{name} ({node_id})"


def _local_impact_summary(scenario: str, report: Any, graph: nx.MultiDiGraph) -> str:
    direct = ", ".join(_node_ref(graph, node) for node in report.direct_impacts) or "none"
    indirect = ", ".join(_node_ref(graph, node) for node in report.indirect_impacts) or "none"
    if _contains_cjk(scenario):
        return f"该场景会直接影响 {direct}，并进一步影响 {indirect}。这些结果来自图中的下游影响路径。"
    return f"This scenario directly affects {direct}, and further affects {indirect}. The result is based on downstream graph impact paths."


def _prettify_identifier(value: str) -> str:
    return value.strip().strip("`").replace("_", " ")


def _looks_mojibake(value: str) -> bool:
    return any(token in value for token in ("�", "锟", "���"))


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)
