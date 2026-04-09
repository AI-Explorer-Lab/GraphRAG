from __future__ import annotations

import networkx as nx


def filter_nodes_by_scope(graph: nx.MultiDiGraph, node_ids: list[str], scope: str) -> list[str]:
    scope_l = scope.lower()
    matched: list[str] = []
    for node_id in node_ids:
        props = graph.nodes[node_id].get("properties", {})
        raw = props.get("raw_properties", {})
        domain = str(raw.get("domain", raw.get("audit_domain", ""))).lower()
        if domain == scope_l:
            matched.append(node_id)
    return sorted(set(matched))

