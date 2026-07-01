from __future__ import annotations

import json

from domain.models import NormalizedGraph


class EvidenceBuilder:
    """Build structured evidence chunks from normalized graph."""

    def build(self, graph: NormalizedGraph) -> dict[str, str]:
        chunks: dict[str, str] = {}

        for entity in graph.entities:
            chunk_id = f"entity::{entity.id}"
            chunks[chunk_id] = json.dumps(entity.model_dump(), ensure_ascii=False)

        for transition in graph.transitions:
            chunk_id = f"transition::{transition.id}"
            chunks[chunk_id] = json.dumps(transition.model_dump(), ensure_ascii=False)

        for entity in graph.entities:
            if not entity.children:
                continue
            chunk_id = f"subgraph::{entity.id}"
            payload = {
                "entity_id": entity.id,
                "children": entity.children,
                "description": entity.description,
            }
            chunks[chunk_id] = json.dumps(payload, ensure_ascii=False)

        return chunks
