from __future__ import annotations

from typing import Any

from lineage_graphrag.domain.lineage_models import LineageInput


class LineageParser:
    """Parse and validate lineage payloads."""

    def parse(self, raw_json: dict[str, Any]) -> LineageInput:
        canonical = dict(raw_json)
        canonical["entities"] = self._canonical_entities(raw_json.get("entities", {}))
        canonical["transitions"] = self._canonical_transitions(raw_json.get("transitions", []))

        lineage = LineageInput.model_validate(canonical)
        self._validate_cross_refs(lineage)
        return lineage

    def _canonical_entities(self, raw_entities: Any) -> dict[str, dict[str, Any]]:
        entities_map: dict[str, dict[str, Any]] = {}

        if isinstance(raw_entities, dict):
            for entity_id, payload in raw_entities.items():
                if not isinstance(payload, dict):
                    raise ValueError(f"Entity '{entity_id}' payload must be an object.")
                merged = dict(payload)
                merged.setdefault("id", str(entity_id))
                if str(merged.get("id", "")).strip() != str(entity_id):
                    raise ValueError(f"Entity key '{entity_id}' must match payload id '{merged.get('id')}'.")
                merged.setdefault("name", str(entity_id))
                merged.setdefault("children", [])
                entities_map[str(entity_id)] = merged
            return entities_map

        # Backward-compatible path for old list-based payloads.
        if isinstance(raw_entities, list):
            for idx, payload in enumerate(raw_entities):
                if not isinstance(payload, dict):
                    raise ValueError(f"Entity item at index {idx} must be an object.")
                entity_id = str(payload.get("id", "")).strip()
                if not entity_id:
                    raise ValueError(f"Entity item at index {idx} is missing 'id'.")
                merged = dict(payload)
                merged.setdefault("name", entity_id)
                merged.setdefault("children", [])
                entities_map[entity_id] = merged
            return entities_map

        raise ValueError("Field 'entities' must be an object map keyed by entity id.")

    def _canonical_transitions(self, raw_transitions: Any) -> list[dict[str, Any]]:
        transitions: list[dict[str, Any]] = []
        if isinstance(raw_transitions, list):
            for idx, payload in enumerate(raw_transitions):
                if not isinstance(payload, dict):
                    raise ValueError(f"Transition item at index {idx} must be an object.")
                merged = dict(payload)
                source = str(merged.get("source", "")).strip()
                target = str(merged.get("target", "")).strip()
                if not source or not target:
                    raise ValueError(f"Transition at index {idx} must contain source/target entity ids.")
                # Keep backward compatibility: auto-generate transition id for old payloads.
                merged.setdefault("id", f"tr::{source}->{target}::{idx}")
                transitions.append(merged)
            return transitions
        if isinstance(raw_transitions, dict):
            for transition_id, payload in raw_transitions.items():
                if not isinstance(payload, dict):
                    raise ValueError(f"Transition '{transition_id}' payload must be an object.")
                merged = dict(payload)
                merged.setdefault("id", str(transition_id))
                transitions.append(merged)
            return transitions
        raise ValueError("Field 'transitions' must be a list.")

    def _validate_cross_refs(self, lineage: LineageInput) -> None:
        entity_ids = set(lineage.entities.keys())
        if not entity_ids:
            raise ValueError("Field 'entities' cannot be empty.")

        for entity_id, entity in lineage.entities.items():
            if entity.id != entity_id:
                raise ValueError(f"Entity '{entity_id}' has inconsistent id '{entity.id}'.")
            for child_id in entity.children:
                if child_id not in entity_ids:
                    raise ValueError(
                        f"Entity '{entity_id}' has child '{child_id}' not present in entities."
                    )

        seen_transition_ids: set[str] = set()
        for transition in lineage.transitions:
            if transition.id in seen_transition_ids:
                raise ValueError(f"Duplicated transition id '{transition.id}'.")
            seen_transition_ids.add(transition.id)
            if transition.source not in entity_ids:
                raise ValueError(
                    f"Transition '{transition.id}' source '{transition.source}' is not an entity id."
                )
            if transition.target not in entity_ids:
                raise ValueError(
                    f"Transition '{transition.id}' target '{transition.target}' is not an entity id."
                )

        for relation in lineage.has_relations:
            if relation.source not in entity_ids or relation.target not in entity_ids:
                raise ValueError(
                    f"Has relation '{relation.source}->{relation.target}' must reference existing entity ids."
                )
