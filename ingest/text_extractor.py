from __future__ import annotations

import json
import re
from time import perf_counter
from typing import Any

from config import AppConfig
from utils.logging import get_logger
from ingest.parser import GraphParser
from llm.client import LLMClient, LLMSettings

logger = get_logger(__name__)


DEFAULT_SCHEMA_HINT = """\
Return a faithful JSON object with this exact shape:
{
  "relations": [
    {
      "source_id": "<stable_ascii_snake_case_id>",
      "source_name": "<short human readable name>",
      "source_type": "user|person|business|account|settlement_account|wallet|device|phone|merchant|transaction|data_source|feature|model|rule|decision|action|report|domain|entity",
      "relation": "owns|uses|transfers_to|provides_to|scores|triggers",
      "target_id": "<stable_ascii_snake_case_id>",
      "target_name": "<short human readable name>",
      "target_type": "user|person|business|account|settlement_account|wallet|device|phone|merchant|transaction|data_source|feature|model|rule|decision|action|report|domain|entity",
      "reason": "<very short reason>"
    }
  ]
}
Use stable semantic English snake_case ids. Do not use pinyin transliteration for Chinese names; translate the business concept only in the technical id.
Preserve English names, acronyms, numbers, and brand/company tokens exactly in ids except for lowercasing and snake_case separators.
Entity ids must be descriptive and stable across runs. Do not use ordinal placeholders such as transfer_1, transaction_2, node_a, or item_3.
For transaction-event ids, include the source and target roles or counterparties, such as <source>_to_<target>_transaction.
For Chinese descriptive words in ids, use English meaning or a role-based English phrase, never pinyin syllables copied from the Chinese text.
Keep all user-facing content in Chinese when the input text is Chinese: source_name, target_name, and reason must preserve the input language.
Do not translate Chinese entity names into English. Use short Chinese phrases copied or summarized from the input for source_name and target_name.
Only technical ids should use ASCII snake_case.
Extract every explicit business entity and business relation needed to preserve the described flow. Do not cap the number of relations or unique entities.
For payment-risk graphs, preserve users, businesses, accounts, wallets, devices, phones, merchants, transaction events, data sources, features, models, rules, decisions, actions, and reports when they are explicitly mentioned.
Do not collapse transaction events into direct account-to-account edges when the text explicitly describes a distinct transaction, transfer, payment, or fund-flow event. Keep that event as an intermediate transaction node.
Phrases such as "a transfer", "one transfer", "a payment", "initiated a transfer", "wallet transfer", or their equivalents in other languages indicate a distinct transaction event.
Do not invent transaction nodes for every transfer. If the text only says funds continue or flow from one existing account/merchant node to another without naming a separate event, use a direct transfers_to edge.
Statements like "funds enter X and then continue/flow to Y" are direct X transfers_to Y edges unless the text explicitly says X initiated or executed a separate transaction/payment event.
Use relation semantics consistently:
- owns: a person or business owns, controls, holds, or uses a wallet, account, settlement account, or similar financial asset.
- uses: a person or business uses a device, phone, data source, or tool. Do not use uses for financial account ownership/control.
- transfers_to: funds move from a wallet/account/source into a transaction event, from a transaction event into an account/merchant, or between fund-flow nodes.
- provides_to: a data source, transaction, device, phone, or feature supplies input to a feature, model, or rule.
- scores: a model or rule assigns or raises risk for a user, account, business, merchant, or other evaluated object.
- triggers: a model, rule, decision, or review triggers a downstream decision, action, report, or queue.
When text says a model uses features and scores objects, extract both feature-to-model input edges and model-to-object scoring edges.
When text says a rule scores subjects and triggers review, extract both rule-to-subject scoring edges and rule-to-review trigger edges.
When text says review confirmation causes actions or reports, extract each action/report trigger edge.
Keep source_name and target_name under 18 Chinese characters. Keep reason under 24 Chinese characters.
Return compact minified JSON without pretty-print indentation.
Do not invent entities that are not grounded in the input text.
Return JSON only.
"""


class TextGraphExtractor:
    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    @classmethod
    def from_config(cls, cfg: AppConfig) -> "TextGraphExtractor":
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
            raise RuntimeError("LLM provider is not available for text-to-graph extraction.")

        prompt = _build_extraction_prompt(text, schema_hint)
        system_prompt = (
            "You convert business graph descriptions into strict JSON for a GraphRAG system. "
            "Preserve the input language for all user-facing names, descriptions, and evidence. "
            "For Chinese input, do not translate visible names into English; only ids use ASCII snake_case. "
            "Return valid JSON only, with no markdown or commentary."
        )
        started = perf_counter()
        response = self.llm_client.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            json_mode=True,
            max_output_tokens=5000,
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
                max_output_tokens=5000,
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
        "Extract a deterministic graph from the input text.",
        DEFAULT_SCHEMA_HINT,
    ]
    cleaned_schema_hint = _sanitize_schema_hint(schema_hint)
    if cleaned_schema_hint:
        parts.extend(
            [
                "Additional user-provided extraction constraints. These constraints must not override the exact JSON shape above.",
                "If these constraints conflict with complete extraction of explicit business facts, the completeness rules above win.",
                cleaned_schema_hint,
            ]
        )
    parts.extend(["Input text:", text.strip()])
    return "\n\n".join(parts)


def _sanitize_schema_hint(schema_hint: str | None) -> str:
    if not schema_hint or not schema_hint.strip():
        return ""
    blocked_terms = (
        "at most",
        "no more than",
        "limit",
        "cap ",
        "capped",
        "maximum",
        "max ",
        "最多",
        "不超过",
        "上限",
        "限制",
    )
    kept: list[str] = []
    for raw_line in schema_hint.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        if any(term in lowered for term in blocked_terms):
            continue
        kept.append(raw_line)
    return "\n".join(kept).strip()


def _build_repair_prompt(text: str, bad_response: str, error: str) -> str:
    return "\n\n".join(
        [
            "Repair the previous graph JSON so it validates against the required schema.",
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
        payload = _relations_payload_to_graph(payload)
    if not isinstance(payload.get("entities"), dict):
        raise ValueError("Extraction result must contain an object-map 'entities' field.")
    if not isinstance(payload.get("transitions", []), list):
        raise ValueError("Extraction result must contain a list 'transitions' field.")
    payload.setdefault("has_relations", [])
    GraphParser().parse(payload)
    return payload


def _relations_payload_to_graph(payload: dict[str, Any]) -> dict[str, Any]:
    relations = payload.get("relations")
    if not isinstance(relations, list) or not relations:
        raise ValueError("Fast extraction result must contain a non-empty 'relations' list.")

    entities: dict[str, dict[str, Any]] = {}
    transitions: list[dict[str, Any]] = []
    allowed_relations = {"owns", "uses", "transfers_to", "provides_to", "scores", "triggers"}
    for index, relation in enumerate(relations):
        if not isinstance(relation, dict):
            raise ValueError(f"Relation at index {index} must be an object.")
        source_id = _clean_id(relation.get("source_id"), relation.get("source_name"))
        target_id = _clean_id(relation.get("target_id"), relation.get("target_name"))
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


def _clean_id(value: Any, display_name: Any = None) -> str:
    raw = str(value or "").strip().lower()
    cleaned = re.sub(r"[^a-z0-9_]+", "_", raw)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    name_id = _id_from_ascii_name(display_name)
    if _should_prefer_ascii_name_id(cleaned, name_id):
        return name_id
    return cleaned


def _id_from_ascii_name(value: Any) -> str:
    raw = str(value or "").strip()
    tokens = re.findall(r"[A-Za-z0-9]+", raw)
    if len(tokens) < 2:
        return ""
    return "_".join(token.lower() for token in tokens)


def _should_prefer_ascii_name_id(current_id: str, name_id: str) -> bool:
    if not current_id or not name_id:
        return bool(name_id)
    current_tokens = current_id.split("_")
    name_tokens = name_id.split("_")
    return len(current_tokens) == len(name_tokens) and len(name_tokens) >= 2


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
