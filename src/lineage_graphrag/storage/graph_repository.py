from __future__ import annotations

from typing import Any

import networkx as nx

from lineage_graphrag.common.logging import get_logger
from lineage_graphrag.domain.lineage_models import NormalizedLineage
from lineage_graphrag.storage.falkordb_client import FalkorDBClient

logger = get_logger(__name__)


class GraphRepository:
    """Graph storage facade.

    When FalkorDB is enabled, FalkorDB is the durable source of truth and the
    in-memory maps are a request-time cache populated by startup/manual sync.
    Without FalkorDB, graphs live only in memory for the current API process.
    """

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
        falkor_status: dict[str, Any] = {
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
                falkor_status = self.falkor.write_graph(graph, graph_name=graph_id, chunks=chunks)
            except Exception as exc:  # pragma: no cover - external system path
                logger.warning("Failed to write graph to FalkorDB: %s", exc)
                falkor_status["error"] = str(exc)
            if not falkor_status.get("written"):
                return falkor_status

        self._graphs[graph_id] = graph
        self._chunks[graph_id] = chunks
        self._metadata[graph_id] = metadata
        return falkor_status

    def restore_graph(
        self,
        graph_id: str,
        graph: nx.MultiDiGraph,
        chunks: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._graphs[graph_id] = graph
        self._chunks[graph_id] = chunks or {}
        self._metadata[graph_id] = metadata or {}

    def hydrate_startup(self) -> dict[str, Any]:
        status: dict[str, Any] = {
            "falkordb_enabled": self.falkor is not None,
            "falkordb_loaded": 0,
            "errors": [],
        }

        if self.falkor is not None:
            try:
                sync_status = self.sync_from_falkordb(clear_existing=True)
                status["falkordb_loaded"] = sync_status["loaded"]
                status["errors"].extend(sync_status["errors"])
            except Exception as exc:
                status["errors"].append(f"falkordb_sync_failed: {exc}")
            return status

        return status

    def sync_from_falkordb(self, clear_existing: bool = True) -> dict[str, Any]:
        if self.falkor is None:
            return {"enabled": False, "available": False, "loaded": 0, "graphs": [], "errors": ["falkordb disabled"]}
        if not self.falkor.is_available():
            return {"enabled": True, "available": False, "loaded": 0, "graphs": [], "errors": ["falkordb unavailable"]}

        errors: list[str] = []
        try:
            graph_ids = self.falkor.list_graphs()
        except Exception as exc:
            return {"enabled": True, "available": True, "loaded": 0, "graphs": [], "errors": [f"falkordb_list_failed: {exc}"]}

        loaded_graphs: dict[str, nx.MultiDiGraph] = {}
        loaded_chunks: dict[str, dict[str, str]] = {}
        loaded_metadata: dict[str, dict[str, Any]] = {}
        for graph_id in graph_ids:
            try:
                graph = self.falkor.read_graph(graph_id)
                if graph is None:
                    errors.append(f"falkordb_graph_empty:{graph_id}")
                    continue
                loaded_graphs[graph_id] = graph
                loaded_chunks[graph_id] = self.falkor.read_chunks(graph_id)
                loaded_metadata[graph_id] = {"source": "falkordb"}
            except Exception as exc:
                errors.append(f"falkordb_load_failed:{graph_id}:{exc}")

        if clear_existing:
            self._graphs = loaded_graphs
            self._chunks = loaded_chunks
            self._metadata = loaded_metadata
        else:
            self._graphs.update(loaded_graphs)
            self._chunks.update(loaded_chunks)
            self._metadata.update(loaded_metadata)

        return {
            "enabled": True,
            "available": True,
            "loaded": len(loaded_graphs),
            "graphs": sorted(loaded_graphs.keys()),
            "errors": errors,
        }

    def get_graph(self, graph_id: str) -> nx.MultiDiGraph | None:
        return self._graphs.get(graph_id)

    def get_chunks(self, graph_id: str) -> dict[str, str]:
        return self._chunks.get(graph_id, {})

    def get_metadata(self, graph_id: str) -> dict[str, Any]:
        return self._metadata.get(graph_id, {})

    def list_graph_ids(self) -> list[str]:
        return sorted(self._graphs.keys())
