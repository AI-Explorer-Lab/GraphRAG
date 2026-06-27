from __future__ import annotations

from typing import Any

import networkx as nx


def extract_graph(graph: nx.MultiDiGraph) -> dict[str, Any]:
    return _serialize_graph(graph)


def extract_subgraph(graph: nx.MultiDiGraph, node_id: str, hops: int = 1) -> dict[str, Any]:
    if node_id not in graph:
        return {"nodes": [], "edges": []}

    distances = nx.single_source_shortest_path_length(graph.to_undirected(), node_id, cutoff=hops)
    nodes = list(distances.keys())
    sub = graph.subgraph(nodes).copy()
    return _serialize_graph(sub)


def _serialize_graph(graph: nx.MultiDiGraph) -> dict[str, Any]:
    node_payload = [
        {
            "id": n,
            "display_id": _display_id(n, d),
            "label": d.get("label", "entity"),
            "level": d.get("level", 2),
            "properties": d.get("properties", {}),
        }
        for n, d in graph.nodes(data=True)
    ]
    edge_payload = [
        {
            "source": u,
            "target": v,
            "relation": d.get("relation", ""),
            "relation_properties": d.get("relation_properties", {}),
            "evidence_refs": d.get("evidence_refs", []),
        }
        for u, v, d in graph.edges(data=True)
    ]
    return {"nodes": node_payload, "edges": edge_payload}


def _display_id(node_id: str, node_data: dict[str, Any]) -> str:
    if node_id.startswith("attr::"):
        parts = node_id.split("::", 2)
        if len(parts) == 3 and parts[2]:
            return parts[2]
    return node_id
