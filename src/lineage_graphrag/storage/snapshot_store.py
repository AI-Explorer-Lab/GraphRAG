from __future__ import annotations

import json
from pathlib import Path

from lineage_graphrag.graph.serializer import load_graph_from_json, save_graph_to_json


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

    def list_graph_ids(self) -> list[str]:
        graph_ids: set[str] = set()
        for path in self.base_dir.glob("*_graph.json"):
            name = path.name
            if not name.endswith("_graph.json"):
                continue
            graph_ids.add(name[: -len("_graph.json")])
        return sorted(graph_ids)

    def load(self, graph_id: str):
        graph_path = self.base_dir / f"{graph_id}_graph.json"
        chunk_path = self.base_dir / f"{graph_id}_chunks.json"
        if not graph_path.exists():
            return None

        graph = load_graph_from_json(graph_path)
        chunks: dict[str, str] = {}
        if chunk_path.exists():
            with open(chunk_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
                if isinstance(raw, dict):
                    chunks = {str(k): str(v) for k, v in raw.items()}
        return graph, chunks
