from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from graph.serializer import save_graph_to_json


class SnapshotStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def save(self, graph_id: str, graph: nx.MultiDiGraph, chunks: dict[str, str]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        save_graph_to_json(graph, self.root / f"{graph_id}_graph.json")
        with open(self.root / f"{graph_id}_chunks.json", "w", encoding="utf-8") as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)
