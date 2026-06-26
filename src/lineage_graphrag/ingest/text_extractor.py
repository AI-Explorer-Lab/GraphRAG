from __future__ import annotations

import json
import re
from time import perf_counter
from typing import Any

from lineage_graphrag.common.config import AppConfig
from lineage_graphrag.common.logging import get_logger
from lineage_graphrag.ingest.parser import LineageParser
from lineage_graphrag.llm.client import LLMClient, LLMSettings

logger = get_logger(__name__)


DEFAULT_SCHEMA_HINT = """\
Return a compact JSON object with this exact shape:
{
  "relations": [
    {
      "source_id": "<stable_ascii_snake_case_id>",
      "source_name": "<short human readable name>",
      "source_type": "person|account|wallet|device|merchant|transaction|data_source|feature|model|rule|decision|action|domain|entity",
      "relation": "owns|uses|transfers_to|provides_to|scores|triggers",
      "target_id": "<stable_ascii_snake_case_id>",
      "target_name": "<short human readable name>",
      "target_type": "person|account|wallet|device|merchant|transaction|data_source|feature|model|rule|decision|action|domain|entity",
      "reason": "<very short reason>"
    }
  ]
}
Use stable snake_case ids. Only use entities and relations supported by the schema.
Keep all user-facing content in Chinese when the input text is Chinese: source_name, target_name, and reason must preserve the input language.
Only technical ids should use ASCII snake_case.
Keep output compact for interactive demos: at most 16 relations and at most 12 unique entities.
Prefer the most important people, accounts, devices, merchants, fund-flow events, features, models, rules, decisions, and actions.
Omit low-signal details instead of trying to cover every noun in the input.
Keep source_name and target_name under 18 Chinese characters. Keep reason under 24 Chinese characters.
Return compact minified JSON without pretty-print indentation.
Do not invent entities that are not grounded in the input text.
Return JSON only.
"""


class TextLineageExtractor:
    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    @classmethod
    def from_config(cls, cfg: AppConfig) -> "TextLineageExtractor":
        settings = LLMSettings(
            provider=cfg.llm_provider,
            model=cfg.llm_model,
            api_key=cfg.openai_api_key,
            base_url=cfg.openai_base_url,
            timeout_seconds=cfg.openai_timeout_seconds,
            temperature=0.0,
        )
        return cls(LLMClient(settings))

    def extract(self, text: str, schema_hint: str | None = None) -> dict[str, Any]:
        if not self.llm_client.is_available():
            raise RuntimeError("LLM provider is not available for text-to-lineage extraction.")

        prompt = _build_extraction_prompt(text, schema_hint)
        system_prompt = (
            "You convert business lineage descriptions into strict JSON for a GraphRAG system. "
            "Preserve the input language for all user-facing names, descriptions, and evidence. "
            "Return valid JSON only, with no markdown or commentary."
        )
        started = perf_counter()
        response = self.llm_client.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            json_mode=True,
            max_output_tokens=2500,
        )
        logger.info(
            "text extraction llm completed: elapsed_seconds=%.2f, response_chars=%s",
            perf_counter() - started,
            len(response) if response else 0,
        )
        if not response:
            provider_error = getattr(self.llm_client, "last_error", None)
            if provider_error:
                raise ValueError(f"LLM returned no extraction text. provider_error={provider_error}")
            raise ValueError("LLM returned no extraction text.")
        try:
            return _parse_and_validate_payload(response)
        except Exception as exc:
            logger.warning("text extraction validation failed, requesting repair: error=%s", exc)
            repair_prompt = _build_repair_prompt(text=text, bad_response=response, error=str(exc))
            repair_started = perf_counter()
            repaired = self.llm_client.generate(
                prompt=repair_prompt,
                system_prompt=system_prompt,
                json_mode=True,
                max_output_tokens=2500,
            )
            logger.info(
                "text extraction repair llm completed: elapsed_seconds=%.2f, response_chars=%s",
                perf_counter() - repair_started,
                len(repaired) if repaired else 0,
            )
            if not repaired:
                raise ValueError(f"LLM returned invalid extraction and repair was empty: {exc}") from exc
            try:
                return _parse_and_validate_payload(repaired)
            except Exception as repair_exc:
                raise ValueError(
                    f"LLM returned invalid extraction after repair. initial_error={exc}; repair_error={repair_exc}"
                ) from repair_exc


def _build_extraction_prompt(text: str, schema_hint: str | None = None) -> str:
    parts = [
        "Extract a deterministic lineage graph from the input text.",
        DEFAULT_SCHEMA_HINT,
    ]
    if schema_hint and schema_hint.strip():
        parts.extend(
            [
                "Additional user-provided extraction constraints. These constraints must not override the exact JSON shape above.",
                schema_hint.strip(),
            ]
        )
    parts.extend(["Input text:", text.strip()])
    return "\n\n".join(parts)


def _build_repair_prompt(text: str, bad_response: str, error: str) -> str:
    return "\n\n".join(
        [
            "Repair the previous lineage JSON so it validates against the required schema.",
            DEFAULT_SCHEMA_HINT,
            "Validation error:",
            error,
            "Original input text:",
            text.strip(),
            "Invalid JSON response:",
            bad_response.strip(),
            "Return corrected JSON only.",
        ]
    )


def _parse_and_validate_payload(text: str) -> dict[str, Any]:
    payload = _parse_json_object(text)
    if "relations" in payload and "entities" not in payload:
        payload = _relations_payload_to_lineage(payload)
    if not isinstance(payload.get("entities"), dict):
        raise ValueError("Extraction result must contain an object-map 'entities' field.")
    if not isinstance(payload.get("transitions", []), list):
        raise ValueError("Extraction result must contain a list 'transitions' field.")
    payload.setdefault("has_relations", [])
    LineageParser().parse(payload)
    return payload


def _relations_payload_to_lineage(payload: dict[str, Any]) -> dict[str, Any]:
    relations = payload.get("relations")
    if not isinstance(relations, list) or not relations:
        raise ValueError("Fast extraction result must contain a non-empty 'relations' list.")

    entities: dict[str, dict[str, Any]] = {}
    transitions: list[dict[str, Any]] = []
    allowed_relations = {"owns", "uses", "transfers_to", "provides_to", "scores", "triggers"}
    for index, relation in enumerate(relations[:16]):
        if not isinstance(relation, dict):
            raise ValueError(f"Relation at index {index} must be an object.")
        source_id = _clean_id(relation.get("source_id"))
        target_id = _clean_id(relation.get("target_id"))
        relation_name = str(relation.get("relation", "")).strip()
        if not source_id or not target_id:
            raise ValueError(f"Relation at index {index} must contain source_id and target_id.")
        if relation_name not in allowed_relations:
            raise ValueError(f"Relation at index {index} has unsupported relation '{relation_name}'.")
        _put_entity(
            entities,
            entity_id=source_id,
            name=relation.get("source_name"),
            entity_type=relation.get("source_type"),
        )
        _put_entity(
            entities,
            entity_id=target_id,
            name=relation.get("target_name"),
            entity_type=relation.get("target_type"),
        )
        transitions.append(
            {
                "id": f"tr::{source_id}->{target_id}::{relation_name}_{index + 1}",
                "source": source_id,
                "target": target_id,
                "relation": relation_name,
                "properties": {
                    "description": str(relation.get("reason") or relation_name).strip()[:80],
                },
            }
        )

    return {
        "entities": entities,
        "transitions": transitions,
        "has_relations": [],
    }


def _put_entity(entities: dict[str, dict[str, Any]], entity_id: str, name: Any, entity_type: Any) -> None:
    if entity_id in entities:
        return
    display_name = str(name or entity_id).strip() or entity_id
    normalized_type = str(entity_type or "entity").strip() or "entity"
    entities[entity_id] = {
        "id": entity_id,
        "name": display_name,
        "description": display_name,
        "children": [],
        "properties": {"type": normalized_type, "risk_level": "unknown"},
    }


def _clean_id(value: Any) -> str:
    raw = str(value or "").strip().lower()
    cleaned = re.sub(r"[^a-z0-9_]+", "_", raw)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(stripped[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("Extraction response must be a JSON object.")
    return value
