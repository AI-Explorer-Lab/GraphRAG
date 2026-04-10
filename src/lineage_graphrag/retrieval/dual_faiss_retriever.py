from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import networkx as nx
import numpy as np

from lineage_graphrag.indexing.embedding_index import EmbeddingIndex
from lineage_graphrag.indexing.faiss_index import FaissIndex


@dataclass(slots=True)
class EdgeRecord:
    source: str
    relation: str
    target: str
    evidence_refs: list[str]


class DualPathFAISSRetriever:
    """
    Path 1: node + relation retrieval.
    Path 2: triple + community retrieval.
    """

    def __init__(self, embedding_model: str = "all-MiniLM-L6-v2", enable_faiss: bool = True) -> None:
        self.embedder = EmbeddingIndex(model_name=embedding_model)
        self.enable_faiss = enable_faiss

        self.node_index = FaissIndex(use_faiss=enable_faiss)
        self.relation_index = FaissIndex(use_faiss=enable_faiss)
        self.triple_index = FaissIndex(use_faiss=enable_faiss)
        self.community_index = FaissIndex(use_faiss=enable_faiss)
        self.chunk_index = FaissIndex(use_faiss=enable_faiss)

        self.node_ids: list[str] = []
        self.relation_records: list[EdgeRecord] = []
        self.triple_records: list[EdgeRecord] = []
        self.community_ids: list[str] = []
        self.chunk_ids: list[str] = []
        self.chunk_map: dict[str, str] = {}

        self._signature: tuple[int, int, int] | None = None

    def retrieve(
        self,
        graph: nx.MultiDiGraph,
        chunks: dict[str, str],
        question: str,
        top_k: int = 8,
    ) -> dict[str, Any]:
        self._build_if_needed(graph, chunks)
        if top_k <= 0:
            top_k = 1

        query_vec = self.embedder.encode([question])[0]

        path1 = self._path1_node_relation(graph, query_vec, top_k)
        path2 = self._path2_triple_community(graph, query_vec, top_k)
        chunk_hits = self._search_chunk_ids(query_vec, top_k)

        merged_chunk_ids: list[str] = []
        seen_chunk_ids: set[str] = set()
        for cid in path1.get("chunk_ids", []) + path2.get("chunk_ids", []) + chunk_hits:
            if cid not in seen_chunk_ids:
                seen_chunk_ids.add(cid)
                merged_chunk_ids.append(cid)

        return {
            "path1_results": path1,
            "path2_results": path2,
            "chunk_ids": merged_chunk_ids[: max(top_k * 2, top_k)],
        }

    def _build_if_needed(self, graph: nx.MultiDiGraph, chunks: dict[str, str]) -> None:
        signature = (graph.number_of_nodes(), graph.number_of_edges(), len(chunks))
        if signature == self._signature:
            return
        self._signature = signature

        self.node_ids = []
        self.relation_records = []
        self.triple_records = []
        self.community_ids = []
        self.chunk_ids = list(chunks.keys())
        self.chunk_map = dict(chunks)

        node_texts: list[str] = []
        relation_texts: list[str] = []
        triple_texts: list[str] = []
        community_texts: list[str] = []
        chunk_texts: list[str] = [chunks[cid] for cid in self.chunk_ids]

        for node_id, data in graph.nodes(data=True):
            label = str(data.get("label", ""))
            props = data.get("properties", {})
            if label == "entity":
                self.node_ids.append(node_id)
                node_texts.append(
                    " ".join(
                        [
                            str(props.get("name", "")),
                            str(props.get("description", "")),
                            str(props.get("schema_type", "")),
                        ]
                    )
                )
            elif label == "community":
                self.community_ids.append(node_id)
                community_texts.append(
                    " ".join(
                        [
                            str(props.get("name", "")),
                            str(props.get("description", "")),
                            " ".join(str(m) for m in props.get("members", [])),
                        ]
                    )
                )

        for u, v, edge_data in graph.edges(data=True):
            relation = str(edge_data.get("relation", "related_to"))
            ev_refs = [str(x) for x in edge_data.get("evidence_refs", [])]
            u_name = _node_name(graph, u)
            v_name = _node_name(graph, v)

            record = EdgeRecord(source=u, relation=relation, target=v, evidence_refs=ev_refs)
            self.relation_records.append(record)
            relation_texts.append(f"{u_name} {relation} {v_name}")

            self.triple_records.append(record)
            triple_texts.append(f"{u_name} {relation} {v_name}")

        self.node_index.build(self.embedder.encode(node_texts) if node_texts else np.zeros((0, 384), dtype=np.float32))
        self.relation_index.build(
            self.embedder.encode(relation_texts) if relation_texts else np.zeros((0, 384), dtype=np.float32)
        )
        self.triple_index.build(self.embedder.encode(triple_texts) if triple_texts else np.zeros((0, 384), dtype=np.float32))
        self.community_index.build(
            self.embedder.encode(community_texts) if community_texts else np.zeros((0, 384), dtype=np.float32)
        )
        self.chunk_index.build(self.embedder.encode(chunk_texts) if chunk_texts else np.zeros((0, 384), dtype=np.float32))

    def _path1_node_relation(self, graph: nx.MultiDiGraph, query_vec: np.ndarray, top_k: int) -> dict[str, Any]:
        node_scores, node_indices = self.node_index.search(query_vec, top_k)
        relation_scores, relation_indices = self.relation_index.search(query_vec, top_k)

        scored: dict[tuple[str, str, str], float] = {}
        chunk_ids: set[str] = set()
        top_nodes: list[str] = []

        if node_indices.size > 0:
            for idx, score in zip(node_indices[0], node_scores[0]):
                if idx < 0 or idx >= len(self.node_ids):
                    continue
                node_id = self.node_ids[int(idx)]
                top_nodes.append(node_id)
                chunk_ids.add(f"entity::{node_id}")
                for u, v, edge_data in graph.out_edges(node_id, data=True):
                    key = (u, str(edge_data.get("relation", "")), v)
                    scored[key] = max(scored.get(key, 0.0), float(score))
                    chunk_ids.update(str(x) for x in edge_data.get("evidence_refs", []))
                for u, v, edge_data in graph.in_edges(node_id, data=True):
                    key = (u, str(edge_data.get("relation", "")), v)
                    scored[key] = max(scored.get(key, 0.0), float(score))
                    chunk_ids.update(str(x) for x in edge_data.get("evidence_refs", []))

        if relation_indices.size > 0:
            for idx, score in zip(relation_indices[0], relation_scores[0]):
                if idx < 0 or idx >= len(self.relation_records):
                    continue
                rec = self.relation_records[int(idx)]
                key = (rec.source, rec.relation, rec.target)
                scored[key] = max(scored.get(key, 0.0), float(score))
                chunk_ids.update(rec.evidence_refs)

        one_hop_triples = sorted(
            [(u, r, v, s) for (u, r, v), s in scored.items()],
            key=lambda x: x[3],
            reverse=True,
        )[: max(top_k * 2, top_k)]

        return {
            "top_nodes": top_nodes[:top_k],
            "one_hop_triples": one_hop_triples,
            "chunk_ids": list(chunk_ids),
        }

    def _path2_triple_community(self, graph: nx.MultiDiGraph, query_vec: np.ndarray, top_k: int) -> dict[str, Any]:
        triple_scores, triple_indices = self.triple_index.search(query_vec, top_k)
        comm_scores, comm_indices = self.community_index.search(query_vec, max(1, top_k // 2))

        scored: dict[tuple[str, str, str], float] = {}
        chunk_ids: set[str] = set()

        if triple_indices.size > 0:
            for idx, score in zip(triple_indices[0], triple_scores[0]):
                if idx < 0 or idx >= len(self.triple_records):
                    continue
                rec = self.triple_records[int(idx)]
                key = (rec.source, rec.relation, rec.target)
                scored[key] = max(scored.get(key, 0.0), float(score))
                chunk_ids.update(rec.evidence_refs)

        if comm_indices.size > 0:
            for idx, score in zip(comm_indices[0], comm_scores[0]):
                if idx < 0 or idx >= len(self.community_ids):
                    continue
                comm_id = self.community_ids[int(idx)]
                comm_score = float(score)

                for u, v, edge_data in graph.in_edges(comm_id, data=True):
                    rel = str(edge_data.get("relation", "member_of"))
                    key = (u, rel, v)
                    scored[key] = max(scored.get(key, 0.0), comm_score)
                    chunk_ids.update(str(x) for x in edge_data.get("evidence_refs", []))
                    if rel == "member_of":
                        chunk_ids.add(f"entity::{u}")

                for u, v, edge_data in graph.out_edges(comm_id, data=True):
                    rel = str(edge_data.get("relation", "related_to"))
                    key = (u, rel, v)
                    scored[key] = max(scored.get(key, 0.0), comm_score)
                    chunk_ids.update(str(x) for x in edge_data.get("evidence_refs", []))

                props = graph.nodes[comm_id].get("properties", {})
                for member in props.get("members", []):
                    chunk_ids.add(f"entity::{member}")

        scored_triples = sorted(
            [(u, r, v, s) for (u, r, v), s in scored.items()],
            key=lambda x: x[3],
            reverse=True,
        )[: max(top_k * 2, top_k)]
        return {
            "scored_triples": scored_triples,
            "chunk_ids": list(chunk_ids),
        }

    def _search_chunk_ids(self, query_vec: np.ndarray, top_k: int) -> list[str]:
        scores, indices = self.chunk_index.search(query_vec, top_k)
        if indices.size == 0:
            return []
        ordered: list[str] = []
        seen: set[str] = set()
        for idx in indices[0]:
            if idx < 0 or idx >= len(self.chunk_ids):
                continue
            chunk_id = self.chunk_ids[int(idx)]
            if chunk_id not in seen:
                seen.add(chunk_id)
                ordered.append(chunk_id)
        return ordered


def _node_name(graph: nx.MultiDiGraph, node_id: str) -> str:
    data = graph.nodes.get(node_id, {})
    props = data.get("properties", {})
    name = props.get("name")
    if isinstance(name, str) and name.strip():
        return name
    return str(node_id)

