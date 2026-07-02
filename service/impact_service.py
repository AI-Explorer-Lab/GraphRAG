from __future__ import annotations

import re
from typing import Any

import networkx as nx

from config import AppConfig
from domain.models import ChangeSpecModel
from domain.req import ImpactRequest
from exceptions import NotFoundException
from impact.propagation import ImpactAnalyzer
from indexing.embedding_index import EmbeddingIndex
from indexing.faiss_index import FaissIndex
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
        resolved_spec, resolution = _resolve_change_spec(graph, payload, self.cfg, analyzer)
        report = analyzer.analyze(
            graph=graph,
            change_spec=resolved_spec,
            target_node_id=payload.target_node_id,
        )
        report.resolved_change_spec = resolved_spec.model_dump()
        report.resolution = resolution
        report.impact_subgraph = _build_impact_subgraph(graph, report.evidence_paths)
        report.answer, report.answer_source, report.llm_called = self._summarize_impact(
            graph,
            payload,
            report,
            resolved_spec,
        )
        return report.model_dump()

    def _summarize_impact(
        self,
        graph: nx.MultiDiGraph,
        payload: ImpactRequest,
        report: Any,
        change_spec: ChangeSpecModel,
    ) -> tuple[str, str, bool]:
        scenario = _impact_question(payload)
        evidence_facts = _impact_evidence_facts(graph, report.evidence_paths)
        prompt = build_impact_prompt(
            scenario=scenario,
            change_target=_node_ref(graph, change_spec.target),
            change_relation=change_spec.relation,
            direct_impacts=[_node_ref(graph, node) for node in report.direct_impacts],
            indirect_impacts=_prompt_indirect_refs(graph, report.evidence_paths),
            scoped_impact=[_node_ref(graph, node) for node in report.scoped_impact],
            target_impact=[_readable_path(graph, path) for path in report.target_impact],
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


def _resolve_change_spec(
    graph: nx.MultiDiGraph,
    payload: ImpactRequest,
    cfg: AppConfig,
    analyzer: ImpactAnalyzer,
) -> tuple[ChangeSpecModel, dict[str, Any]]:
    original = payload.change_spec
    scenario = _impact_question(payload)
    query = " ".join(
        value
        for value in (
            scenario,
            original.target,
            original.source,
            original.relation,
        )
        if value
    )

    exact_paths = []
    if original.target in graph:
        exact_paths = analyzer.analyze(graph, original, target_node_id=payload.target_node_id).evidence_paths
        if exact_paths:
            return original, {
                "status": "exact",
                "input_target": original.target,
                "resolved_target": original.target,
                "method": "exact_node_id",
                "score": 1.0,
            }

    candidates = _impact_start_candidates(graph, query, original, payload.target_node_id, cfg)
    if not candidates:
        return original, {
            "status": "unresolved",
            "input_target": original.target,
            "resolved_target": original.target,
            "method": "none",
            "reason": "no strong entity match in graph",
        }

    best: tuple[str, float, str, int] | None = None
    for node_id, score, method in candidates:
        candidate_spec = original.model_copy(update={"target": node_id})
        paths = analyzer.analyze(graph, candidate_spec, target_node_id=payload.target_node_id).evidence_paths
        path_count = len(paths)
        if not paths and original.target in graph:
            continue
        weighted_score = score + min(path_count, 12) * 0.75
        if best is None or weighted_score > best[1]:
            best = (node_id, weighted_score, method, path_count)

    if best is None:
        if original.target in graph:
            return original, {
                "status": "exact_empty",
                "input_target": original.target,
                "resolved_target": original.target,
                "method": "exact_node_id",
                "path_count": len(exact_paths),
            }
        top_node, score, method = candidates[0]
        return original, {
            "status": "unresolved",
            "input_target": original.target,
            "resolved_target": original.target,
            "candidate": top_node,
            "candidate_score": round(score, 4),
            "method": method,
            "reason": "candidate has no downstream impact path",
        }

    node_id, score, method, path_count = best
    if node_id == original.target:
        return original, {
            "status": "exact_empty",
            "input_target": original.target,
            "resolved_target": original.target,
            "method": method,
            "score": round(score, 4),
            "path_count": path_count,
        }

    resolved = original.model_copy(update={"target": node_id})
    return resolved, {
        "status": "resolved",
        "input_target": original.target,
        "resolved_target": node_id,
        "resolved_target_ref": _node_ref(graph, node_id),
        "method": method,
        "score": round(score, 4),
        "path_count": path_count,
    }


def _impact_start_candidates(
    graph: nx.MultiDiGraph,
    query: str,
    spec: ChangeSpecModel,
    target_node_id: str | None,
    cfg: AppConfig,
) -> list[tuple[str, float, str]]:
    semantic_scores = _semantic_node_scores(graph, query, cfg, top_k=10)
    query_l = query.lower()
    query_tokens = _text_tokens(query)
    target_tokens = _text_tokens(spec.target)
    excluded = {target_node_id} if target_node_id else set()
    candidates: dict[str, tuple[float, str]] = {}

    for node_id, data in graph.nodes(data=True):
        if data.get("label") != "entity" or node_id in excluded:
            continue
        props = data.get("properties", {})
        name = str(props.get("name", "")).strip()
        description = str(props.get("description", "")).strip()
        schema_type = str(props.get("schema_type", props.get("type", ""))).strip()
        node_tokens = _text_tokens(" ".join([node_id, name, description, schema_type]))
        score = 0.0
        reasons: list[str] = []

        if node_id == spec.target:
            score += 120.0
            reasons.append("exact_node_id")
        elif _normalized_identifier(node_id) == _normalized_identifier(spec.target):
            score += 90.0
            reasons.append("normalized_node_id")

        if name and name.lower() in query_l:
            score += 80.0
            reasons.append("name_in_scenario")
        if description and description.lower() in query_l and description.lower() != name.lower():
            score += 20.0
            reasons.append("description_in_scenario")

        token_overlap = len(query_tokens & node_tokens)
        target_overlap = len(target_tokens & node_tokens)
        if token_overlap:
            score += token_overlap * 3.0
            reasons.append("token_overlap")
        if target_overlap:
            score += target_overlap * 6.0
            reasons.append("target_token_overlap")

        semantic = semantic_scores.get(node_id, 0.0)
        if semantic >= 0.35:
            score += semantic * 12.0
            reasons.append("semantic")

        if _has_downstream_business_edge(graph, node_id):
            score += 1.0

        if score < 12.0:
            continue
        method = "+".join(dict.fromkeys(reasons)) or "scored"
        existing = candidates.get(node_id)
        if existing is None or score > existing[0]:
            candidates[node_id] = (score, method)

    return [
        (node_id, score, method)
        for node_id, (score, method) in sorted(candidates.items(), key=lambda item: item[1][0], reverse=True)
    ]


def _semantic_node_scores(
    graph: nx.MultiDiGraph,
    query: str,
    cfg: AppConfig,
    top_k: int,
) -> dict[str, float]:
    node_ids: list[str] = []
    node_texts: list[str] = []
    for node_id, data in graph.nodes(data=True):
        if data.get("label") != "entity":
            continue
        props = data.get("properties", {})
        node_ids.append(node_id)
        node_texts.append(
            " ".join(
                [
                    node_id,
                    str(props.get("name", "")),
                    str(props.get("description", "")),
                    str(props.get("schema_type", props.get("type", ""))),
                    str(props.get("raw_properties", "")),
                ]
            )
        )
    if not node_ids:
        return {}
    try:
        embedder = EmbeddingIndex(model_name=cfg.retrieval_embedding_model)
        vectors = embedder.encode(node_texts)
        query_vec = embedder.encode([query])[0]
        index = FaissIndex(use_faiss=cfg.enable_faiss)
        index.build(vectors)
        scores, indices = index.search(query_vec, min(top_k, len(node_ids)))
    except Exception:
        return {}
    output: dict[str, float] = {}
    if indices.size == 0:
        return output
    for idx, score in zip(indices[0], scores[0]):
        if idx < 0 or idx >= len(node_ids):
            continue
        output[node_ids[int(idx)]] = float(score)
    return output


def _has_downstream_business_edge(graph: nx.MultiDiGraph, node_id: str) -> bool:
    for _, _, edge_data in graph.out_edges(node_id, data=True):
        relation = str(edge_data.get("relation", "")).lower()
        if relation in {"owns", "uses", "transfers_to", "provides_to", "scores", "triggers", "transitions"}:
            return True
    return False


def _text_tokens(text: str) -> set[str]:
    tokens = set(re.findall(r"[a-zA-Z0-9]+", text.lower().replace("_", " ")))
    tokens.update(re.findall(r"[\u4e00-\u9fff]{2,}", text))
    return {token for token in tokens if token}


def _normalized_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _impact_system_prompt(scenario: str, language: str | None = None) -> str:
    if _wants_chinese(language, scenario):
        return (
            "你是严格的图谱影响分析助手。"
            "只能根据提供的影响路径解释。"
            "必须全程使用中文。"
            "节点可以保留括号中的 node id。"
            "不要输出 edge id、transition id、trace id 或内部追踪标识。"
        )
    return (
        "You are a strict graph impact analysis assistant. "
        "Explain only from provided impact paths. "
        "You may preserve parenthesized node ids. "
        "Do not output edge ids, transition ids, trace ids, or internal tracing tokens."
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
            hops.append(f"{_node_ref(graph, source)} --{relation}--> {_node_ref(graph, target)}")
        if not hops:
            continue
        fact = f"depth {path.depth}: " + " ; ".join(hops)
        if fact in seen:
            continue
        seen.add(fact)
        facts.append(fact)
    return facts


def _readable_path(graph: nx.MultiDiGraph, path: str) -> str:
    node_ids = [node.strip() for node in path.split(" -> ") if node.strip()]
    if not node_ids:
        return path
    return " -> ".join(_node_ref(graph, node_id) for node_id in node_ids)


def _prompt_indirect_refs(graph: nx.MultiDiGraph, paths: list[Any]) -> list[str]:
    node_ids: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if path.depth <= 1 or not path.path or not path.relations:
            continue
        node_id = path.path[-1]
        if node_id in seen:
            continue
        relation = str(path.relations[-1]).lower()
        if path.depth <= 2 or relation in {"scores", "triggers", "transitions"}:
            seen.add(node_id)
            node_ids.append(node_id)
    return [_node_ref(graph, node_id) for node_id in sorted(node_ids)]


def _build_impact_subgraph(graph: nx.MultiDiGraph, paths: list[Any]) -> dict[str, Any]:
    node_ids: list[str] = []
    seen_nodes: set[str] = set()
    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str]] = set()

    for path in paths:
        path_nodes = list(path.path)
        for node_id in path_nodes:
            if node_id in seen_nodes:
                continue
            seen_nodes.add(node_id)
            node_ids.append(node_id)

        for index, relation in enumerate(path.relations):
            if index + 1 >= len(path_nodes):
                continue
            source = path_nodes[index]
            target = path_nodes[index + 1]
            relation_text = str(relation)
            edge_key = (source, target, relation_text)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            edge_data = _matching_edge_data(graph, source, target, relation_text)
            edges.append(
                {
                    "source": source,
                    "target": target,
                    "relation": edge_data.get("relation", relation_text),
                    "relation_properties": edge_data.get("relation_properties", {}),
                    "evidence_refs": edge_data.get("evidence_refs", []),
                }
            )

    nodes = []
    for node_id in node_ids:
        node_data = graph.nodes.get(node_id, {})
        nodes.append(
            {
                "id": node_id,
                "display_id": _display_id(node_id, node_data),
                "label": node_data.get("label", "entity"),
                "level": node_data.get("level", 2),
                "properties": node_data.get("properties", {}),
            }
        )
    return {"nodes": nodes, "edges": edges, "view": "impact"}


def _matching_edge_data(graph: nx.MultiDiGraph, source: str, target: str, relation: str) -> dict[str, Any]:
    edge_bundle = graph.get_edge_data(source, target, default={})
    for edge_data in edge_bundle.values():
        if str(edge_data.get("relation", "")).lower() == str(relation).lower():
            return edge_data
    return {}


def _display_id(node_id: str, node_data: dict[str, Any]) -> str:
    if node_id.startswith("attr::"):
        parts = node_id.split("::", 2)
        if len(parts) == 3 and parts[2]:
            return parts[2]
    return node_id


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
