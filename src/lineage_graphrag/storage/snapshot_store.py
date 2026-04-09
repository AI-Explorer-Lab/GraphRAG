from __future__ import annotations

import json
from pathlib import Path

from lineage_graphrag.graph.serializer import save_graph_to_json


class SnapshotStore:
    def __init__(self, base_dir: str = "data/normalized") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, graph_id: str, graph, chunks: dict[str, str]) -> None:
        graph_path = self.base_dir / f"{graph_id}_graph.json"
        chunk_path = self.base_dir / f"{graph_id}_chunks.json"
        save_graph_to_json(graph, graph_path)
        with open(chunk_path, "w", encoding="utf-8") as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)

