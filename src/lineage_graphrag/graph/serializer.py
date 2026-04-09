from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx


def save_graph_to_json(graph: nx.MultiDiGraph, output_path: str | Path) -> None:
    payload: list[dict[str, Any]] = []
    for u, v, data in graph.edges(data=True):
        payload.append(
            {
                "start_node": {
                    "id": u,
                    "label": graph.nodes[u].get("label", "entity"),
                    "properties": graph.nodes[u].get("properties", {}),
                },
                "relation": data.get("relation", ""),
                "relation_properties": data.get("relation_properties", {}),
                "evidence_refs": data.get("evidence_refs", []),
                "end_node": {
                    "id": v,
                    "label": graph.nodes[v].get("label", "entity"),
                    "properties": graph.nodes[v].get("properties", {}),
                },
            }
        )
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_graph_from_json(input_path: str | Path) -> nx.MultiDiGraph:
    with open(input_path, "r", encoding="utf-8") as f:
        relationships = json.load(f)

    graph = nx.MultiDiGraph()
    for rel in relationships:
        start_node = rel["start_node"]
        end_node = rel["end_node"]
        u = str(start_node.get("id", start_node.get("properties", {}).get("id", "")))
        v = str(end_node.get("id", end_node.get("properties", {}).get("id", "")))

        graph.add_node(
            u,
            label=start_node.get("label", "entity"),
            properties=start_node.get("properties", {}),
            level=_label_to_level(start_node.get("label", "entity")),
        )
        graph.add_node(
            v,
            label=end_node.get("label", "entity"),
            properties=end_node.get("properties", {}),
            level=_label_to_level(end_node.get("label", "entity")),
        )
        graph.add_edge(
            u,
            v,
            relation=rel.get("relation", ""),
            relation_properties=rel.get("relation_properties", {}),
            source_id=u,
            target_id=v,
            evidence_refs=rel.get("evidence_refs", []),
        )
    return graph


def _label_to_level(label: str) -> int:
    mapping = {"attribute": 1, "entity": 2, "keyword": 3, "community": 4}
    return mapping.get(label, 2)

