from __future__ import annotations

import json

from lineage_graphrag.domain.lineage_models import NormalizedLineage


class EvidenceBuilder:
    """Build structured evidence chunks from normalized lineage."""

    def build(self, lineage: NormalizedLineage) -> dict[str, str]:
        chunks: dict[str, str] = {}

        for entity in lineage.entities:
            chunk_id = f"entity::{entity.id}"
            chunks[chunk_id] = json.dumps(entity.model_dump(), ensure_ascii=False)

        for transition in lineage.transitions:
            chunk_id = f"transition::{transition.id}"
            chunks[chunk_id] = json.dumps(transition.model_dump(), ensure_ascii=False)

        for entity in lineage.entities:
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
