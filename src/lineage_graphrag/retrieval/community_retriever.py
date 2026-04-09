from __future__ import annotations

from typing import Any

import networkx as nx


class CommunityRetriever:
    def retrieve(self, graph: nx.MultiDiGraph, question: str, top_k: int = 8) -> dict[str, Any]:
        question_l = question.lower()
        scored_triples: list[tuple[str, str, str, float]] = []

        for node_id, data in graph.nodes(data=True):
            if data.get("label") != "community":
                continue
            props = data.get("properties", {})
            text = f"{props.get('name', '')} {props.get('description', '')}".lower()
            score = 1.0 if any(tok in text for tok in question_l.split()) else 0.1
            for u, v, edge_data in graph.in_edges(node_id, data=True):
                if edge_data.get("relation") == "member_of":
                    scored_triples.append((u, "member_of", node_id, score))

        scored_triples = sorted(scored_triples, key=lambda x: x[3], reverse=True)[:top_k]
        return {"scored_triples": scored_triples}

