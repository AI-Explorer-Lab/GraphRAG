from __future__ import annotations

import re
from typing import Any

import networkx as nx

from lineage_graphrag.common.logging import get_logger

logger = get_logger(__name__)

try:
    import redis
except ImportError:  # pragma: no cover - dependency may be optional in some envs
    redis = None


class FalkorDBClient:
    """Best-effort FalkorDB client for graph persistence."""

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

    def write_graph(self, graph: nx.MultiDiGraph, graph_name: str = "lineage") -> dict[str, Any]:
        status: dict[str, Any] = {
            "enabled": True,
            "available": self.is_available(),
            "graph_name": graph_name,
            "nodes_attempted": graph.number_of_nodes(),
            "edges_attempted": graph.number_of_edges(),
            "written": False,
            "error": None,
        }
        if not self.is_available():
            logger.info("FalkorDB unavailable, skip remote write.")
            status["error"] = "falkordb unavailable"
            return status

        try:
            for node_id, node_data in graph.nodes(data=True):
                label = _safe_symbol(node_data.get("label", "entity"), fallback="entity")
                props = node_data.get("properties", {})
                safe_id = _cypher_escape(node_id)
                safe_name = _cypher_escape(props.get("name", node_id))
                q = f"MERGE (n:{label} {{id:'{safe_id}'}}) SET n.name='{safe_name}'"
                self.execute(graph_name, q)

            for u, v, edge_data in graph.edges(data=True):
                relation = _safe_symbol(edge_data.get("relation", "RELATED_TO"), fallback="RELATED_TO").upper()
                safe_u = _cypher_escape(u)
                safe_v = _cypher_escape(v)
                q = (
                    f"MATCH (a {{id:'{safe_u}'}}), (b {{id:'{safe_v}'}}) "
                    f"MERGE (a)-[:{relation}]->(b)"
                )
                self.execute(graph_name, q)
        except Exception as exc:
            status["error"] = str(exc)
            logger.warning("FalkorDB write failed: %s", exc)
            return status

        status["written"] = True
        return status


def _cypher_escape(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def _safe_symbol(value: Any, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", str(value))
    if not cleaned:
        return fallback
    if cleaned[0].isdigit():
        return f"{fallback}_{cleaned}"
    return cleaned
