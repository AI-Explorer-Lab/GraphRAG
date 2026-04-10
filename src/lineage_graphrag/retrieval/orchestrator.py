from __future__ import annotations

from typing import Any

import networkx as nx

from lineage_graphrag.common.config import AppConfig
from lineage_graphrag.retrieval.dual_faiss_retriever import DualPathFAISSRetriever
from lineage_graphrag.retrieval.evidence_ranker import rank_chunk_ids


class LineageRetriever:
    def __init__(
        self,
        embedding_model: str = "all-MiniLM-L6-v2",
        enable_faiss: bool = True,
    ) -> None:
        self.dual = DualPathFAISSRetriever(
            embedding_model=embedding_model,
            enable_faiss=enable_faiss,
        )

    @classmethod
    def from_config(cls, cfg: AppConfig) -> "LineageRetriever":
        return cls(
            embedding_model=cfg.retrieval_embedding_model,
            enable_faiss=cfg.enable_faiss,
        )

    def retrieve(
        self,
        graph: nx.MultiDiGraph,
        chunks: dict[str, str],
        question: str,
        top_k: int = 8,
        involved_types: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        _ = involved_types  # kept for compatibility; not required in lineage has/transitions scope
        dual_result = self.dual.retrieve(graph=graph, chunks=chunks, question=question, top_k=top_k)
        path1_results = dual_result["path1_results"]
        path2_results = dual_result["path2_results"]

        triples: list[str] = []
        all_chunk_ids: list[str] = list(dual_result.get("chunk_ids", []))

        for u, r, v, _ in path1_results.get("one_hop_triples", []):
            triples.append(f"({u}, {r}, {v})")

        for u, r, v, _ in path2_results.get("scored_triples", []):
            triples.append(f"({u}, {r}, {v})")

        dedup_triples = list(dict.fromkeys(triples))[: max(top_k * 2, top_k)]
        ranked_chunk_ids = rank_chunk_ids(question, chunks, all_chunk_ids, top_k=max(top_k * 2, top_k))
        chunk_contents = [chunks[cid] for cid in ranked_chunk_ids if cid in chunks]

        return {
            "triples": dedup_triples,
            "chunk_ids": ranked_chunk_ids,
            "chunk_contents": chunk_contents,
            "paths": path2_results.get("scored_triples", []),
            "path1_results": path1_results,
            "path2_results": path2_results,
        }

