from __future__ import annotations

from typing import Any

import networkx as nx

from lineage_graphrag.common.logging import get_logger
from lineage_graphrag.domain.lineage_models import NormalizedLineage
from lineage_graphrag.storage.falkordb_client import FalkorDBClient

logger = get_logger(__name__)


class GraphRepository:
    """In-memory source of truth with optional FalkorDB mirror."""

    def __init__(self, use_falkordb: bool = False, falkordb_url: str = "redis://localhost:6379/0") -> None:
        self._normalized_lineage: dict[str, NormalizedLineage] = {}
        self._graphs: dict[str, nx.MultiDiGraph] = {}
        self._chunks: dict[str, dict[str, str]] = {}
        self._metadata: dict[str, dict[str, Any]] = {}
        self.falkor = FalkorDBClient(falkordb_url) if use_falkordb else None

    def save_lineage(self, graph_id: str, lineage: NormalizedLineage) -> None:
        self._normalized_lineage[graph_id] = lineage

    def get_lineage(self, graph_id: str) -> NormalizedLineage | None:
        return self._normalized_lineage.get(graph_id)

    def save_graph(
        self,
        graph_id: str,
        graph: nx.MultiDiGraph,
        chunks: dict[str, str],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        self._graphs[graph_id] = graph
        self._chunks[graph_id] = chunks
        self._metadata[graph_id] = metadata

        mirror_status: dict[str, Any] = {
            "enabled": self.falkor is not None,
            "available": False,
            "graph_name": graph_id,
            "nodes_attempted": graph.number_of_nodes(),
            "edges_attempted": graph.number_of_edges(),
            "written": False,
            "error": None,
        }
        if self.falkor is not None:
            try:
                mirror_status = self.falkor.write_graph(graph, graph_name=graph_id)
            except Exception as exc:  # pragma: no cover - external system path
                logger.warning("Failed to mirror graph to FalkorDB: %s", exc)
                mirror_status["error"] = str(exc)
        return mirror_status

    def get_graph(self, graph_id: str) -> nx.MultiDiGraph | None:
        return self._graphs.get(graph_id)

    def get_chunks(self, graph_id: str) -> dict[str, str]:
        return self._chunks.get(graph_id, {})

    def get_metadata(self, graph_id: str) -> dict[str, Any]:
        return self._metadata.get(graph_id, {})
