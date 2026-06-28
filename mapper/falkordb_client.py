from __future__ import annotations

import json
import re
from typing import Any

import networkx as nx

from utils.logging import get_logger
from domain.models import ALLOWED_ENTITY_RELATIONS

logger = get_logger(__name__)

try:
    import redis
except ImportError:  # pragma: no cover - dependency may be optional in some envs
    redis = None


RAW_SUFFIX = "__graph_raw"
COMM_SUFFIX = "__graph_comm"
REPRE_SUFFIX = "__graph_repre"
LEGACY_RAW_SUFFIX = "__raw"
LEGACY_COMM_SUFFIX = "__comm"
LEGACY_REPRE_SUFFIX = "__repre"
PARTITION_SUFFIXES = (
    RAW_SUFFIX,
    COMM_SUFFIX,
    REPRE_SUFFIX,
    LEGACY_RAW_SUFFIX,
    LEGACY_COMM_SUFFIX,
    LEGACY_REPRE_SUFFIX,
)


class FalkorDBClient:
    """Best-effort FalkorDB client for graph persistence and reload."""

    def __init__(self, url: str = "redis://localhost:6379/0") -> None:
        self.url = url
        self.client = None
        if redis is not None:
            try:
                self.client = redis.Redis.from_url(url)
            except Exception as exc:  # pragma: no cover
                logger.warning("FalkorDB client init failed: %s", exc)

    def is_available(self) -> bool:
        if self.client is None:
            return False
        try:
            self.client.ping()
            return True
        except Exception:
            return False

    def execute(self, graph_name: str, query: str) -> Any:
        if not self.is_available():
            return None
        return self.client.execute_command("GRAPH.QUERY", graph_name, query)

    def list_graphs(self) -> list[str]:
        physical = self._list_physical_graphs()
        logical: set[str] = set()
        for name in physical:
            matched_partition = False
            for suffix in PARTITION_SUFFIXES:
                if name.endswith(suffix):
                    base = name[: -len(suffix)]
                    if base:
                        logical.add(base)
                    matched_partition = True
                    break
            if matched_partition:
                continue
            logical.add(name)
        return sorted(logical)

    def _list_physical_graphs(self) -> list[str]:
        if not self.is_available():
            return []
        try:
            raw = self.client.execute_command("GRAPH.LIST")
        except Exception as exc:  # pragma: no cover - external system path
            logger.warning("FalkorDB GRAPH.LIST failed: %s", exc)
            return []
        values = _to_python(raw)
        if not isinstance(values, list):
            return []
        names = [str(x) for x in values if isinstance(x, (str, bytes))]
        return sorted({str(n) for n in names if n})

    def write_graph(
        self,
        graph: nx.MultiDiGraph,
        graph_name: str = "graph",
        chunks: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        partitions = _partition_graph_for_falkordb(graph)
        raw_name = _raw_graph_name(graph_name)
        comm_name = _comm_graph_name(graph_name)
        repre_name = _repre_graph_name(graph_name)
        raw_nodes = partitions["graph_raw"]["nodes"]
        raw_edges = partitions["graph_raw"]["edges"]
        comm_nodes = partitions["graph_comm"]["nodes"]
        comm_edges = partitions["graph_comm"]["edges"]
        repre_nodes = partitions["graph_repre"]["nodes"]
        repre_edges = partitions["graph_repre"]["edges"]

        status: dict[str, Any] = {
            "enabled": True,
            "available": self.is_available(),
            "graph_name": graph_name,
            "graph_raw": {
                "graph_name": raw_name,
                "nodes_attempted": len(raw_nodes),
                "edges_attempted": len(raw_edges),
                "written": False,
                "error": None,
            },
            "graph_comm": {
                "graph_name": comm_name,
                "nodes_attempted": len(comm_nodes),
                "edges_attempted": len(comm_edges),
                "written": False,
                "error": None,
            },
            "graph_repre": {
                "graph_name": repre_name,
                "nodes_attempted": len(repre_nodes),
                "edges_attempted": len(repre_edges),
                "written": False,
                "error": None,
            },
            "nodes_attempted": len(raw_nodes) + len(comm_nodes) + len(repre_nodes),
            "edges_attempted": len(raw_edges) + len(comm_edges) + len(repre_edges),
            "written": False,
            "chunks_written": False,
            "nodes_total": graph.number_of_nodes(),
            "edges_total": graph.number_of_edges(),
            "error": None,
        }
        if not self.is_available():
            logger.info("FalkorDB unavailable, skip remote write.")
            status["error"] = "falkordb unavailable"
            return status

        try:
            # Backward compatibility cleanup: remove old single-graph name and partition names.
            self._delete_graph_if_exists(graph_name)
            self._delete_graph_if_exists(raw_name)
            self._delete_graph_if_exists(comm_name)
            self._delete_graph_if_exists(repre_name)

            raw_status = self._write_sub_graph(
                graph=graph,
                graph_name=raw_name,
                node_ids=raw_nodes,
                edges=raw_edges,
            )
            comm_status = self._write_sub_graph(
                graph=graph,
                graph_name=comm_name,
                node_ids=comm_nodes,
                edges=comm_edges,
            )
            repre_status = self._write_sub_graph(
                graph=graph,
                graph_name=repre_name,
                node_ids=repre_nodes,
                edges=repre_edges,
            )
            status["graph_raw"].update(raw_status)
            status["graph_comm"].update(comm_status)
            status["graph_repre"].update(repre_status)
        except Exception as exc:
            status["error"] = str(exc)
            logger.warning("FalkorDB write failed: %s", exc)
            return status

        status["written"] = bool(
            status["graph_raw"]["written"] and status["graph_comm"]["written"] and status["graph_repre"]["written"]
        )
        if chunks is not None:
            status["chunks_written"] = self.write_chunks(graph_name, chunks)
        return status

    def _delete_graph_if_exists(self, graph_name: str) -> None:
        if not self.is_available():
            return
        try:
            existing = set(self._list_physical_graphs())
            if graph_name not in existing:
                return
            self.client.execute_command("GRAPH.DELETE", graph_name)
        except Exception as exc:  # pragma: no cover - external system path
            logger.warning("FalkorDB graph reset failed for '%s': %s", graph_name, exc)

    def _write_sub_graph(
        self,
        graph: nx.MultiDiGraph,
        graph_name: str,
        node_ids: list[str],
        edges: list[tuple[str, str, dict[str, Any]]],
    ) -> dict[str, Any]:
        sub_status = {
            "written": False,
            "error": None,
        }
        try:
            for node_id in node_ids:
                node_data = graph.nodes[node_id]
                label = _safe_symbol(str(node_data.get("label", "entity")).lower(), fallback="entity")
                safe_id = _cypher_escape(node_id)
                persist_props = _build_persist_props(node_id=node_id, node_data=node_data)
                assignments = ", ".join(
                    [
                        f"n.{_safe_symbol(k, fallback='prop')}='{_cypher_escape(v)}'"
                        for k, v in persist_props.items()
                    ]
                )
                if assignments:
                    q = f"MERGE (n:{label} {{id:'{safe_id}'}}) SET {assignments}"
                else:
                    q = f"MERGE (n:{label} {{id:'{safe_id}'}})"
                self.execute(graph_name, q)

            for u, v, edge_data in edges:
                relation = _safe_symbol(edge_data.get("relation", "RELATED_TO"), fallback="RELATED_TO").upper()
                safe_u = _cypher_escape(u)
                safe_v = _cypher_escape(v)
                rel_props = edge_data.get("relation_properties", {})
                if not isinstance(rel_props, dict):
                    rel_props = {}
                evidence_refs = edge_data.get("evidence_refs", [])
                if not isinstance(evidence_refs, list):
                    evidence_refs = []
                safe_rel_props_json = _cypher_escape(json.dumps(rel_props, ensure_ascii=False))
                safe_evidence_json = _cypher_escape(json.dumps(evidence_refs, ensure_ascii=False))
                q = (
                    f"MATCH (a {{id:'{safe_u}'}}), (b {{id:'{safe_v}'}}) "
                    f"MERGE (a)-[r:{relation}]->(b) "
                    f"SET r.relation_properties_json='{safe_rel_props_json}', "
                    f"r.evidence_refs_json='{safe_evidence_json}'"
                )
                self.execute(graph_name, q)
            sub_status["written"] = True
        except Exception as exc:
            sub_status["error"] = str(exc)
            logger.warning("FalkorDB sub graph write failed for '%s': %s", graph_name, exc)
        return sub_status

    def write_chunks(self, graph_name: str, chunks: dict[str, str]) -> bool:
        if not self.is_available():
            return False
        try:
            payload = json.dumps(chunks, ensure_ascii=False)
            self.client.set(_chunks_key(graph_name), payload)
            return True
        except Exception as exc:  # pragma: no cover - external system path
            logger.warning("FalkorDB chunk write failed for '%s': %s", graph_name, exc)
            return False

    def read_chunks(self, graph_name: str) -> dict[str, str]:
        if not self.is_available():
            return {}
        try:
            raw = self.client.get(_chunks_key(graph_name))
            if raw is None:
                return {}
            value = _to_python(raw)
            if not isinstance(value, str):
                value = str(value)
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return {str(k): str(v) for k, v in parsed.items()}
        except Exception as exc:  # pragma: no cover - external system path
            logger.warning("FalkorDB chunk read failed for '%s': %s", graph_name, exc)
        return {}

    def read_graph(self, graph_name: str) -> nx.MultiDiGraph | None:
        if not self.is_available():
            return None
        try:
            physical = set(self._list_physical_graphs())
        except Exception as exc:  # pragma: no cover - external system path
            logger.warning("FalkorDB physical graph list failed: %s", exc)
            return None

        for raw_name, comm_name, repre_name in _partition_name_candidates(graph_name):
            has_raw = raw_name in physical
            has_comm = comm_name in physical
            has_repre = repre_name in physical

            if has_raw or has_comm or has_repre:
                merged = nx.MultiDiGraph()
                if has_raw:
                    raw_graph = self._read_single_graph(raw_name)
                    if raw_graph is not None:
                        _merge_into(merged, raw_graph)
                if has_comm:
                    comm_graph = self._read_single_graph(comm_name)
                    if comm_graph is not None:
                        _merge_into(merged, comm_graph)
                if has_repre:
                    repre_graph = self._read_single_graph(repre_name)
                    if repre_graph is not None:
                        _merge_into(merged, repre_graph)
                return merged

        if graph_name in physical:
            return self._read_single_graph(graph_name)
        return None

    def _read_single_graph(self, graph_name: str) -> nx.MultiDiGraph | None:
        graph = nx.MultiDiGraph()
        try:
            node_rows = _extract_rows(self.execute(graph_name, "MATCH (n) RETURN n.id, labels(n), properties(n)"))
            for row in node_rows:
                values = _row_values(row)
                if len(values) < 3:
                    continue
                node_id = str(values[0])
                raw_props = _to_dict(values[2])
                label = _resolve_node_label(_ensure_list(values[1]), raw_props)
                props = _parse_node_properties(raw_props, node_id=node_id, label=label)
                graph.add_node(
                    node_id,
                    label=label,
                    properties=props,
                    level=_label_to_level(label),
                )

            edge_rows = _extract_rows(
                self.execute(graph_name, "MATCH (a)-[r]->(b) RETURN a.id, b.id, type(r), properties(r)")
            )
            for row in edge_rows:
                values = _row_values(row)
                if len(values) < 4:
                    continue
                u = str(values[0])
                v = str(values[1])
                relation = str(values[2]).lower()
                raw_rel_props = _to_dict(values[3])

                relation_properties = _parse_json_field(raw_rel_props.get("relation_properties_json"), default={})
                evidence_refs = _parse_json_field(raw_rel_props.get("evidence_refs_json"), default=[])
                if not isinstance(evidence_refs, list):
                    evidence_refs = []
                evidence_refs = [str(x) for x in evidence_refs]

                if u not in graph:
                    graph.add_node(u, label="entity", properties={"name": u}, level=2)
                if v not in graph:
                    graph.add_node(v, label="entity", properties={"name": v}, level=2)

                graph.add_edge(
                    u,
                    v,
                    relation=relation,
                    relation_properties=relation_properties if isinstance(relation_properties, dict) else {},
                    source_id=u,
                    target_id=v,
                    evidence_refs=evidence_refs,
                )
        except Exception as exc:  # pragma: no cover - external system path
            logger.warning("FalkorDB read graph failed for '%s': %s", graph_name, exc)
            return None
        return graph


def _chunks_key(graph_name: str) -> str:
    return f"graph:chunks:{graph_name}"


def _cypher_escape(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def _safe_symbol(value: Any, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", str(value))
    if not cleaned:
        return fallback
    if cleaned[0].isdigit():
        return f"{fallback}_{cleaned}"
    return cleaned


def _to_python(value: Any) -> Any:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except Exception:
            return value.decode(errors="ignore")
    if isinstance(value, list):
        return [_to_python(v) for v in value]
    if isinstance(value, tuple):
        return [_to_python(v) for v in value]
    if isinstance(value, dict):
        return {_to_python(k): _to_python(v) for k, v in value.items()}
    return value


def _extract_rows(response: Any) -> list[Any]:
    payload = _to_python(response)
    if not isinstance(payload, list):
        return []
    if len(payload) >= 2 and isinstance(payload[1], list):
        return payload[1]
    if payload and all(isinstance(x, list) for x in payload):
        return payload
    return []


def _row_values(row: Any) -> list[Any]:
    raw = _to_python(row)
    if isinstance(raw, list):
        return raw
    return [raw]


def _ensure_list(value: Any) -> list[Any]:
    raw = _to_python(value)
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("[") and text.endswith("]"):
            inner = text[1:-1].strip()
            if not inner:
                return []
            return [_strip_outer_quotes(item.strip()) for item in _split_top_level(inner)]
    return []


def _to_dict(value: Any) -> dict[str, Any]:
    raw = _to_python(value)
    if isinstance(raw, dict):
        return {str(k): v for k, v in raw.items()}
    if isinstance(raw, list):
        if all(isinstance(item, list) and len(item) == 2 for item in raw):
            return {str(k): v for k, v in raw}
        if len(raw) % 2 == 0:
            out: dict[str, Any] = {}
            for i in range(0, len(raw), 2):
                out[str(raw[i])] = raw[i + 1]
            return out
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("{") and text.endswith("}"):
            inner = text[1:-1].strip()
            if not inner:
                return {}
            out: dict[str, Any] = {}
            for item in _split_top_level(inner):
                if ":" not in item:
                    continue
                key, raw_value = item.split(":", 1)
                out[str(_strip_outer_quotes(key.strip()))] = raw_value.strip()
            return out
    return {}


def _parse_json_field(raw: Any, default: Any) -> Any:
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    text = str(raw).strip()
    if not text:
        return default
    try:
        parsed = json.loads(text)
        if isinstance(parsed, str):
            nested = parsed.strip()
            if nested and nested[0] in "[{":
                try:
                    return json.loads(nested)
                except Exception:
                    return parsed
        return parsed
    except Exception:
        return default


def _split_top_level(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    quote: str | None = None
    escaped = False
    depth = 0
    for index, char in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char in "[{(":
            depth += 1
            continue
        if char in "]})" and depth > 0:
            depth -= 1
            continue
        if char == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    parts.append(text[start:].strip())
    return [part for part in parts if part]


def _strip_outer_quotes(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _resolve_node_label(raw_labels: list[Any], raw_props: dict[str, Any]) -> str:
    persisted = _strip_outer_quotes(str(raw_props.get("label", "")).strip()).lower()
    if persisted:
        return persisted
    for label in raw_labels:
        text = _strip_outer_quotes(str(label).strip()).lower()
        if text:
            return text
    return "entity"


def _build_persist_props(node_id: str, node_data: dict[str, Any]) -> dict[str, str]:
    label = str(node_data.get("label", "entity")).lower()
    props = node_data.get("properties", {})

    out: dict[str, str] = {
        "name": str(props.get("name", node_id)),
        "label": str(node_data.get("label", "entity")),
    }
    if label == "entity":
        out["description"] = str(props.get("description", ""))
        out["schema_type"] = str(props.get("schema_type", "entity"))
        out["raw_properties_json"] = json.dumps(props.get("raw_properties", {}), ensure_ascii=False)
    elif label == "attribute":
        out["description"] = str(props.get("name", ""))
        out["attr_key"] = str(props.get("attr_key", ""))
        out["attr_value_json"] = json.dumps(props.get("attr_value"), ensure_ascii=False)
    elif label == "community":
        out["description"] = str(props.get("description", ""))
        out["members_json"] = json.dumps(props.get("members", []), ensure_ascii=False)
        representative = props.get("representative")
        if representative is not None:
            out["representative"] = str(representative)
        out["keyword_entities_json"] = json.dumps(props.get("keyword_entities", []), ensure_ascii=False)
    elif label == "keyword":
        out["kind"] = str(props.get("kind", "lexical"))
        entity_id = props.get("entity_id")
        if entity_id is not None:
            out["entity_id"] = str(entity_id)
    return out


def _parse_node_properties(raw_props: dict[str, Any], node_id: str, label: str) -> dict[str, Any]:
    props_json = raw_props.get("props_json")
    parsed = _parse_json_field(props_json, default=None)
    if isinstance(parsed, dict):
        return {str(k): v for k, v in parsed.items()}

    label_l = label.lower()
    if label_l == "entity":
        raw_properties = _parse_json_field(raw_props.get("raw_properties_json"), default={})
        if not isinstance(raw_properties, dict):
            raw_properties = {}
        return {
            "id": node_id,
            "name": str(raw_props.get("name", node_id)),
            "description": str(raw_props.get("description", "")),
            "schema_type": str(raw_props.get("schema_type", "entity")),
            "raw_properties": {str(k): v for k, v in raw_properties.items()},
        }
    if label_l == "attribute":
        attr_value = _parse_json_field(raw_props.get("attr_value_json"), default=raw_props.get("attr_value"))
        return {
            "name": str(raw_props.get("description", raw_props.get("name", node_id))),
            "attr_key": str(raw_props.get("attr_key", "")),
            "attr_value": attr_value,
        }
    if label_l == "community":
        members = _parse_json_field(raw_props.get("members_json"), default=[])
        if not isinstance(members, list):
            members = []
        keyword_entities = _parse_json_field(raw_props.get("keyword_entities_json"), default=[])
        if not isinstance(keyword_entities, list):
            keyword_entities = []
        out = {
            "name": str(raw_props.get("name", node_id)),
            "description": str(raw_props.get("description", "")),
            "members": [str(x) for x in members],
            "keyword_entities": [str(x) for x in keyword_entities],
        }
        representative = raw_props.get("representative")
        if representative is not None:
            out["representative"] = str(representative)
        return out
    if label_l == "keyword":
        out = {
            "name": str(raw_props.get("name", node_id)),
            "kind": str(raw_props.get("kind", "lexical")),
        }
        entity_id = raw_props.get("entity_id")
        if entity_id is not None:
            out["entity_id"] = str(entity_id)
        return out

    fallback: dict[str, Any] = {}
    for key, value in raw_props.items():
        if key in {"id", "label", "props_json", "raw_properties_json", "members_json", "keyword_entities_json"}:
            continue
        fallback[str(key)] = value
    if "name" not in fallback:
        fallback["name"] = str(raw_props.get("name", node_id))
    return fallback


def _label_to_level(label: str) -> int:
    mapping = {"attribute": 1, "entity": 2, "keyword": 3, "community": 4}
    return mapping.get(label, 2)


def _raw_graph_name(graph_id: str) -> str:
    return f"{graph_id}{RAW_SUFFIX}"


def _comm_graph_name(graph_id: str) -> str:
    return f"{graph_id}{COMM_SUFFIX}"


def _repre_graph_name(graph_id: str) -> str:
    return f"{graph_id}{REPRE_SUFFIX}"


def _partition_name_candidates(graph_id: str) -> list[tuple[str, str, str]]:
    return [
        (_raw_graph_name(graph_id), _comm_graph_name(graph_id), _repre_graph_name(graph_id)),
        (
            f"{graph_id}{LEGACY_RAW_SUFFIX}",
            f"{graph_id}{LEGACY_COMM_SUFFIX}",
            f"{graph_id}{LEGACY_REPRE_SUFFIX}",
        ),
    ]


def _partition_graph_for_falkordb(graph: nx.MultiDiGraph) -> dict[str, dict[str, Any]]:
    raw_labels = {"entity", "attribute"}
    raw_relations = {"has_attribute", "has", *ALLOWED_ENTITY_RELATIONS}
    comm_relations = {"member_of", "has_keyword"}
    repre_relations = {"represents_community", "represented_by", "represents_entity"}
    comm_primary_labels = {"community", "keyword"}
    comm_allowed_labels = {"entity", "community", "keyword"}
    repre_allowed_labels = {"entity", "community", "keyword"}

    node_labels = {
        node_id: str(node_data.get("label", "entity")).lower()
        for node_id, node_data in graph.nodes(data=True)
    }

    raw_nodes = [node_id for node_id, label in node_labels.items() if label in raw_labels]
    raw_node_set = set(raw_nodes)
    raw_edges = [
        (u, v, edge_data)
        for u, v, edge_data in graph.edges(data=True)
        if str(edge_data.get("relation", "")).lower() in raw_relations and u in raw_node_set and v in raw_node_set
    ]

    comm_nodes_set = {
        node_id
        for node_id, label in node_labels.items()
        if label in comm_primary_labels
    }
    comm_edges: list[tuple[str, str, dict[str, Any]]] = []
    for u, v, edge_data in graph.edges(data=True):
        relation = str(edge_data.get("relation", "")).lower()
        if relation not in comm_relations:
            continue
        if node_labels.get(u) not in comm_allowed_labels or node_labels.get(v) not in comm_allowed_labels:
            continue
        comm_nodes_set.add(u)
        comm_nodes_set.add(v)
        comm_edges.append((u, v, edge_data))

    comm_nodes = [node_id for node_id in comm_nodes_set if node_labels.get(node_id) in comm_allowed_labels]
    comm_node_set = set(comm_nodes)
    comm_edges = [(u, v, edge_data) for u, v, edge_data in comm_edges if u in comm_node_set and v in comm_node_set]

    repre_nodes_set: set[str] = set()
    repre_edges: list[tuple[str, str, dict[str, Any]]] = []
    for u, v, edge_data in graph.edges(data=True):
        relation = str(edge_data.get("relation", "")).lower()
        if relation not in repre_relations:
            continue
        if node_labels.get(u) not in repre_allowed_labels or node_labels.get(v) not in repre_allowed_labels:
            continue
        repre_nodes_set.add(u)
        repre_nodes_set.add(v)
        repre_edges.append((u, v, edge_data))

    repre_nodes = [node_id for node_id in repre_nodes_set if node_labels.get(node_id) in repre_allowed_labels]
    repre_node_set = set(repre_nodes)
    repre_edges = [
        (u, v, edge_data)
        for u, v, edge_data in repre_edges
        if u in repre_node_set and v in repre_node_set
    ]

    return {
        "graph_raw": {
            "nodes": sorted(raw_nodes),
            "edges": raw_edges,
        },
        "graph_comm": {
            "nodes": sorted(comm_nodes),
            "edges": comm_edges,
        },
        "graph_repre": {
            "nodes": sorted(repre_nodes),
            "edges": repre_edges,
        },
    }


def _merge_into(target: nx.MultiDiGraph, source: nx.MultiDiGraph) -> None:
    for node_id, node_data in source.nodes(data=True):
        if node_id not in target:
            target.add_node(node_id, **node_data)
            continue
        existing = target.nodes[node_id]
        existing_props = existing.get("properties", {})
        incoming_props = node_data.get("properties", {})
        if isinstance(existing_props, dict) and isinstance(incoming_props, dict):
            merged_props = dict(existing_props)
            merged_props.update(incoming_props)
            existing["properties"] = merged_props
        for key, value in node_data.items():
            if key == "properties":
                continue
            if key == "label" and existing.get("label") != "entity" and value == "entity":
                continue
            existing[key] = value

    for u, v, edge_data in source.edges(data=True):
        target.add_edge(u, v, **edge_data)
