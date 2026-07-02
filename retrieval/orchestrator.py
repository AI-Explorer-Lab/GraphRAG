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
        path_depth: int = 3,
    ) -> None:
        self.dual = DualPathFAISSRetriever(
            embedding_model=embedding_model,
            enable_faiss=enable_faiss,
        )
        self.path_depth = max(1, path_depth)

    @classmethod
    def from_config(cls, cfg: AppConfig) -> "GraphRetriever":
        return cls(
            embedding_model=cfg.retrieval_embedding_model,
            enable_faiss=cfg.enable_faiss,
            path_depth=cfg.retrieval_path_depth,
        )

    def retrieve(
        self,
        graph: nx.MultiDiGraph,
        chunks: dict[str, str],
        question: str,
        top_k: int = 8,
        involved_types: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        _ = involved_types  # kept for compatibility; schema constraints are encoded in graph relations.
        dual_result = self.dual.retrieve(graph=graph, chunks=chunks, question=question, top_k=top_k)
        path1_results = dual_result["path1_results"]
        path2_results = dual_result["path2_results"]

        triples: list[str] = []
        all_chunk_ids: list[str] = list(dual_result.get("chunk_ids", []))
        seed_nodes: set[str] = _seed_nodes_from_chunk_ids(graph, all_chunk_ids)
        seed_nodes.update(_entity_nodes(graph, path1_results.get("top_nodes", [])))

        for u, r, v, _ in path1_results.get("one_hop_triples", []):
            triples.append(f"({u}, {r}, {v})")
            seed_nodes.update(_entity_nodes(graph, [u, v]))

        for u, r, v, _ in path2_results.get("scored_triples", []):
            triples.append(f"({u}, {r}, {v})")
            seed_nodes.update(_entity_nodes(graph, [u, v]))

        path_triples, path_chunk_ids, traversal_paths = _traverse_semantic_paths(
            graph=graph,
            seed_nodes=seed_nodes,
            max_depth=self.path_depth,
            top_k=top_k,
        )
        triples.extend(path_triples)
        all_chunk_ids.extend(path_chunk_ids)

        dedup_triples = _prioritize_triples(list(dict.fromkeys(triples)))[: max(top_k * 2, top_k)]
        ranked_chunk_ids = rank_chunk_ids(question, chunks, all_chunk_ids, top_k=max(top_k * 2, top_k))
        chunk_contents = [chunks[cid] for cid in ranked_chunk_ids if cid in chunks]

        return {
            "triples": dedup_triples,
            "chunk_ids": ranked_chunk_ids,
            "chunk_contents": chunk_contents,
            "paths": traversal_paths[: max(top_k * 2, top_k)],
            "path_depth": self.path_depth,
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


def _traverse_semantic_paths(
    graph: nx.MultiDiGraph,
    seed_nodes: set[str],
    max_depth: int,
    top_k: int,
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    triples: list[str] = []
    chunk_ids: list[str] = []
    paths: list[dict[str, Any]] = []
    seen_path_keys: set[tuple[tuple[str, str, str], ...]] = set()
    path_limit = max(top_k * 4, top_k)

    def dfs(
        current: str,
        nodes: list[str],
        edges: list[tuple[str, str, str, dict[str, Any]]],
        visited: set[str],
    ) -> None:
        if len(edges) >= max_depth or len(paths) >= path_limit:
            return

        candidates = sorted(
            graph.out_edges(current, data=True),
            key=lambda item: (_relation_name_priority(str(item[2].get("relation", "related_to"))), str(item[1])),
        )
        for u, v, edge_data in candidates:
            relation = str(edge_data.get("relation", "related_to"))
            if relation in _NOISE_RELATIONS or v in visited:
                continue

            next_edges = [*edges, (u, relation, v, edge_data)]
            next_nodes = [*nodes, v]
            path_key = tuple((src, rel, dst) for src, rel, dst, _ in next_edges)
            if path_key not in seen_path_keys:
                seen_path_keys.add(path_key)
                path_triples = [f"({src}, {rel}, {dst})" for src, rel, dst, _ in next_edges]
                edge_refs = _edge_refs_for_path(next_edges)
                triples.extend(path_triples)
                chunk_ids.extend(edge_refs)
                for endpoint in next_nodes:
                    if graph.nodes.get(endpoint, {}).get("label") == "entity":
                        chunk_ids.append(f"entity::{endpoint}")
                paths.append(
                    {
                        "nodes": next_nodes,
                        "relations": [rel for _, rel, _, _ in next_edges],
                        "triples": path_triples,
                        "edge_ids": [_edge_id_from_data(edge_data) for _, _, _, edge_data in next_edges],
                        "evidence_refs": edge_refs,
                        "depth": len(next_edges),
                    }
                )
                if len(paths) >= path_limit:
                    return

            dfs(v, next_nodes, next_edges, {*visited, v})
            if len(paths) >= path_limit:
                return

    for seed in sorted(seed_nodes):
        if graph.nodes.get(seed, {}).get("label") != "entity":
            continue
        dfs(seed, [seed], [], {seed})
        if len(paths) >= path_limit:
            break

    return list(dict.fromkeys(triples)), list(dict.fromkeys(chunk_ids)), paths


def _edge_refs_for_path(edges: list[tuple[str, str, str, dict[str, Any]]]) -> list[str]:
    refs: list[str] = []
    for _, _, _, edge_data in edges:
        raw_refs = edge_data.get("evidence_refs", [])
        refs.extend(str(ref) for ref in raw_refs if str(ref).strip())
    return list(dict.fromkeys(refs))


def _edge_id_from_data(edge_data: dict[str, Any]) -> str:
    rel_props = edge_data.get("relation_properties", {})
    if isinstance(rel_props, dict):
        transition_id = str(rel_props.get("transition_id", "")).strip()
        if transition_id:
            return transition_id
    refs = edge_data.get("evidence_refs", [])
    for ref in refs if isinstance(refs, list) else []:
        ref_text = str(ref)
        if ref_text.startswith("transition::"):
            return ref_text.removeprefix("transition::")
    return ""


def _prioritize_triples(triples: list[str]) -> list[str]:
    semantic = [triple for triple in triples if not any(f", {relation}, " in triple for relation in _NOISE_RELATIONS)]
    semantic.sort(key=lambda triple: (_relation_priority(triple), triples.index(triple)))
    noise = [triple for triple in triples if triple not in semantic]
    return semantic + noise


def _relation_name_priority(relation: str) -> int:
    return _RELATION_PRIORITY.get(relation, 6)


def _relation_priority(triple: str) -> int:
    parts = [part.strip() for part in triple.strip("()").split(",")]
    if len(parts) < 3:
        return 99
    relation = parts[1]
    if relation == "transfers_to" and any("wallet" in endpoint.lower() for endpoint in (parts[0], parts[2])):
        return 3
    return _relation_name_priority(relation)


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
            edge_id = _edge_id_from_data(edge_data)
            if edge_id:
                edge_ids[triple] = edge_id
                break
    return edge_ids