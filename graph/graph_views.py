from __future__ import annotations

from typing import Any

import networkx as nx

from constants.graph import ALLOWED_ENTITY_RELATIONS

BUSINESS_RELATIONS = set(ALLOWED_ENTITY_RELATIONS)
RAW_RELATIONS = {"has", "has_attribute", *ALLOWED_ENTITY_RELATIONS}
SEMANTIC_RELATIONS = {"member_of", "has_keyword", "represents_community", "represented_by", "represents_entity"}
GRAPH_VIEW_MODES = {"business", "entity_attribute", "semantic", "full"}


def extract_graph(graph: nx.MultiDiGraph, view: str = "full") -> dict[str, Any]:
    payload = _serialize_graph(_filter_graph_by_view(graph, view))
    payload["view"] = _normalize_view(view)
    return payload


def extract_subgraph(graph: nx.MultiDiGraph, node_id: str, hops: int = 1, view: str = "full") -> dict[str, Any]:
    scoped = _filter_graph_by_view(graph, view)
    if node_id not in scoped:
        return {"nodes": [], "edges": [], "view": _normalize_view(view)}

    distances = nx.single_source_shortest_path_length(scoped.to_undirected(), node_id, cutoff=hops)
    nodes = list(distances.keys())
    sub = scoped.subgraph(nodes).copy()
    payload = _serialize_graph(sub)
    payload["view"] = _normalize_view(view)
    return payload


def _filter_graph_by_view(graph: nx.MultiDiGraph, view: str) -> nx.MultiDiGraph:
    mode = _normalize_view(view)
    if mode == "full":
        return graph.copy()

    labels = {node_id: str(data.get("label", "entity")).lower() for node_id, data in graph.nodes(data=True)}
    selected_nodes: set[str] = set()
    selected_edges: list[tuple[str, str, dict[str, Any]]] = []

    if mode == "business":
        allowed_labels = {"entity"}
        allowed_relations = BUSINESS_RELATIONS
    elif mode == "entity_attribute":
        allowed_labels = {"entity", "attribute"}
        allowed_relations = RAW_RELATIONS
    else:
        allowed_labels = {"entity", "keyword", "community"}
        allowed_relations = SEMANTIC_RELATIONS

    for u, v, data in graph.edges(data=True):
        relation = str(data.get("relation", "")).lower()
        if relation not in allowed_relations:
            continue
        if labels.get(u) not in allowed_labels or labels.get(v) not in allowed_labels:
            continue
        selected_nodes.add(u)
        selected_nodes.add(v)
        selected_edges.append((u, v, data))

    if mode == "entity_attribute":
        selected_nodes.update(node_id for node_id, label in labels.items() if label in allowed_labels)
    elif mode == "semantic":
        selected_nodes.update(node_id for node_id, label in labels.items() if label in {"keyword", "community"})
    elif not selected_nodes:
        selected_nodes.update(node_id for node_id, label in labels.items() if label == "entity")

    scoped = nx.MultiDiGraph()
    for node_id in sorted(selected_nodes):
        if node_id in graph:
            scoped.add_node(node_id, **graph.nodes[node_id])
    for u, v, data in selected_edges:
        if u in scoped and v in scoped:
            scoped.add_edge(u, v, **data)
    return scoped


def _normalize_view(view: str) -> str:
    mode = (view or "full").strip().lower()
    if mode not in GRAPH_VIEW_MODES:
        return "full"
    return mode


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
