from __future__ import annotations

from typing import Any

import networkx as nx

from config import AppConfig
from retrieval.dual_faiss_retriever import DualPathFAISSRetriever
from retrieval.evidence_ranker import rank_chunk_ids


class GraphRetriever:
    def __init__(
        self,
        embedding_model: str = "all-MiniLM-L6-v2",
        enable_faiss: bool = True,
    ) -> None:
        self.dual = DualPathFAISSRetriever(
            embedding_model=embedding_model,
            enable_faiss=enable_faiss,
        )

    @classmethod
    def from_config(cls, cfg: AppConfig) -> "GraphRetriever":
        return cls(
            embedding_model=cfg.retrieval_embedding_model,
            enable_faiss=cfg.enable_faiss,
        )

    def retrieve(
        self,
        graph: nx.MultiDiGraph,
        chunks: dict[str, str],
        question: str,
        top_k: int = 8,
        involved_types: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        _ = involved_types  # kept for compatibility; not required in graph has/transitions scope
        dual_result = self.dual.retrieve(graph=graph, chunks=chunks, question=question, top_k=top_k)
        path1_results = dual_result["path1_results"]
        path2_results = dual_result["path2_results"]

        triples: list[str] = []
        all_chunk_ids: list[str] = list(dual_result.get("chunk_ids", []))
        seed_nodes: set[str] = _seed_nodes_from_chunk_ids(graph, all_chunk_ids)

        for u, r, v, _ in path1_results.get("one_hop_triples", []):
            triples.append(f"({u}, {r}, {v})")
            seed_nodes.update(_entity_nodes(graph, [u, v]))

        for u, r, v, _ in path2_results.get("scored_triples", []):
            triples.append(f"({u}, {r}, {v})")
            seed_nodes.update(_entity_nodes(graph, [u, v]))

        expanded_triples, expanded_chunk_ids = _expand_semantic_one_hop(graph, seed_nodes)
        triples.extend(expanded_triples)
        all_chunk_ids.extend(expanded_chunk_ids)

        dedup_triples = _prioritize_triples(list(dict.fromkeys(triples)))[: max(top_k * 2, top_k)]
        ranked_chunk_ids = rank_chunk_ids(question, chunks, all_chunk_ids, top_k=max(top_k * 2, top_k))
        chunk_contents = [chunks[cid] for cid in ranked_chunk_ids if cid in chunks]

        return {
            "triples": dedup_triples,
            "chunk_ids": ranked_chunk_ids,
            "chunk_contents": chunk_contents,
            "paths": path2_results.get("scored_triples", []),
            "path1_results": path1_results,
            "path2_results": path2_results,
            "node_names": _node_names_for_evidence(graph, dedup_triples, ranked_chunk_ids),
            "edge_ids": _edge_ids_for_triples(graph, dedup_triples),
        }


_NOISE_RELATIONS = {
    "has_attribute",
    "member_of",
    "represented_by",
    "represents_entity",
    "represents_community",
    "has_keyword",
}

_RELATION_PRIORITY = {
    "triggers": 0,
    "scores": 1,
    "owns": 2,
    "uses": 3,
    "transfers_to": 4,
    "provides_to": 5,
    "has": 8,
}


def _seed_nodes_from_chunk_ids(graph: nx.MultiDiGraph, chunk_ids: list[str]) -> set[str]:
    seed_nodes: set[str] = set()
    for chunk_id in chunk_ids:
        if not chunk_id.startswith("entity::"):
            continue
        node_id = chunk_id.removeprefix("entity::")
        if graph.nodes.get(node_id, {}).get("label") == "entity":
            seed_nodes.add(node_id)
    return seed_nodes


def _entity_nodes(graph: nx.MultiDiGraph, node_ids: list[str]) -> set[str]:
    return {node_id for node_id in node_ids if graph.nodes.get(node_id, {}).get("label") == "entity"}


def _expand_semantic_one_hop(graph: nx.MultiDiGraph, seed_nodes: set[str]) -> tuple[list[str], list[str]]:
    triples: list[str] = []
    chunk_ids: list[str] = []
    for node_id in sorted(seed_nodes):
        for u, v, edge_data in list(graph.in_edges(node_id, data=True)) + list(graph.out_edges(node_id, data=True)):
            relation = str(edge_data.get("relation", "related_to"))
            if relation in _NOISE_RELATIONS:
                continue
            triples.append(f"({u}, {relation}, {v})")
            chunk_ids.extend(str(ref) for ref in edge_data.get("evidence_refs", []))
            chunk_ids.extend(f"entity::{endpoint}" for endpoint in (u, v) if graph.nodes.get(endpoint, {}).get("label") == "entity")
    return list(dict.fromkeys(triples)), list(dict.fromkeys(chunk_ids))


def _prioritize_triples(triples: list[str]) -> list[str]:
    semantic = [triple for triple in triples if not any(f", {relation}, " in triple for relation in _NOISE_RELATIONS)]
    semantic.sort(key=lambda triple: (_relation_priority(triple), triples.index(triple)))
    noise = [triple for triple in triples if triple not in semantic]
    return semantic + noise


def _relation_priority(triple: str) -> int:
    parts = [part.strip() for part in triple.strip("()").split(",")]
    if len(parts) < 3:
        return 99
    relation = parts[1]
    if relation == "transfers_to" and any("wallet" in endpoint.lower() for endpoint in (parts[0], parts[2])):
        return 3
    return _RELATION_PRIORITY.get(relation, 6)


def _node_names_for_evidence(graph: nx.MultiDiGraph, triples: list[str], chunk_ids: list[str]) -> dict[str, str]:
    node_ids: set[str] = set()
    for triple in triples:
        parts = [part.strip() for part in triple.strip("()").split(",")]
        if len(parts) == 3:
            node_ids.add(parts[0])
            node_ids.add(parts[2])
    for chunk_id in chunk_ids:
        if chunk_id.startswith("entity::"):
            node_ids.add(chunk_id.removeprefix("entity::"))
        elif chunk_id.startswith("subgraph::"):
            node_ids.add(chunk_id.removeprefix("subgraph::"))

    names: dict[str, str] = {}
    for node_id in node_ids:
        data = graph.nodes.get(node_id, {})
        props = data.get("properties", {})
        name = props.get("name") if isinstance(props, dict) else None
        if isinstance(name, str) and name.strip():
            names[node_id] = name.strip()
    return names


def _edge_ids_for_triples(graph: nx.MultiDiGraph, triples: list[str]) -> dict[str, str]:
    edge_ids: dict[str, str] = {}
    for triple in triples:
        parts = [part.strip() for part in triple.strip("()").split(",")]
        if len(parts) != 3:
            continue
        source, relation, target = parts
        edge_data_by_key = graph.get_edge_data(source, target, default={})
        if not isinstance(edge_data_by_key, dict):
            continue
        for edge_data in edge_data_by_key.values():
            if not isinstance(edge_data, dict) or str(edge_data.get("relation")) != relation:
                continue
            rel_props = edge_data.get("relation_properties", {})
            if isinstance(rel_props, dict):
                transition_id = str(rel_props.get("transition_id", "")).strip()
                if transition_id:
                    edge_ids[triple] = transition_id
                    break
            refs = edge_data.get("evidence_refs", [])
            for ref in refs if isinstance(refs, list) else []:
                ref_text = str(ref)
                if ref_text.startswith("transition::"):
                    edge_ids[triple] = ref_text.removeprefix("transition::")
                    break
            if triple in edge_ids:
                break
    return edge_ids
