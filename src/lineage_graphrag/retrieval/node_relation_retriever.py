from __future__ import annotations

from collections import defaultdict
from typing import Any

import networkx as nx


def _tokenize(text: str) -> set[str]:
    return {t for t in text.lower().replace("_", " ").split() if t}


class NodeRelationRetriever:
    def retrieve(
        self,
        graph: nx.MultiDiGraph,
        chunks: dict[str, str],
        question: str,
        top_k: int = 8,
        involved_types: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        q_tokens = _tokenize(question)
        scores: dict[str, float] = {}

        for node_id, data in graph.nodes(data=True):
            if data.get("label") != "entity":
                continue
            props = data.get("properties", {})
            raw_text = " ".join(
                [
                    str(props.get("name", "")),
                    str(props.get("description", "")),
                    str(props.get("schema_type", "")),
                ]
            )
            node_tokens = _tokenize(raw_text)
            if not node_tokens:
                continue
            overlap = len(q_tokens & node_tokens)
            score = overlap / max(len(node_tokens), 1)
            if score > 0:
                scores[node_id] = score

        # Fallback: if no overlap, use first entities
        if not scores:
            for node_id, data in graph.nodes(data=True):
                if data.get("label") == "entity":
                    scores[node_id] = 0.01
                    if len(scores) >= top_k:
                        break

        if involved_types and involved_types.get("nodes"):
            allowed = set(involved_types["nodes"])
            filtered = {}
            for node_id, score in scores.items():
                schema_type = str(graph.nodes[node_id].get("properties", {}).get("schema_type", ""))
                if schema_type in allowed:
                    filtered[node_id] = score
            if filtered:
                scores = filtered

        top_nodes = [n for n, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]]

        triples: list[tuple[str, str, str, float]] = []
        chunk_ids: set[str] = set()

        for node in top_nodes:
            for u, v, edge_data in graph.out_edges(node, data=True):
                relation = edge_data.get("relation", "")
                triples.append((u, relation, v, scores.get(node, 0.0)))
                chunk_ids.update(edge_data.get("evidence_refs", []))
            for u, v, edge_data in graph.in_edges(node, data=True):
                relation = edge_data.get("relation", "")
                triples.append((u, relation, v, scores.get(node, 0.0)))
                chunk_ids.update(edge_data.get("evidence_refs", []))
            chunk_ids.add(f"entity::{node}")

        return {
            "top_nodes": top_nodes,
            "one_hop_triples": triples,
            "chunk_ids": list(chunk_ids),
            "chunk_results": {cid: chunks[cid] for cid in chunk_ids if cid in chunks},
        }

