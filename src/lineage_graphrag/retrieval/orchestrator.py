from __future__ import annotations

from typing import Any

import networkx as nx

from lineage_graphrag.retrieval.community_retriever import CommunityRetriever
from lineage_graphrag.retrieval.evidence_ranker import rank_chunk_ids
from lineage_graphrag.retrieval.node_relation_retriever import NodeRelationRetriever


class LineageRetriever:
    def __init__(self) -> None:
        self.path1 = NodeRelationRetriever()
        self.path2 = CommunityRetriever()

    def retrieve(
        self,
        graph: nx.MultiDiGraph,
        chunks: dict[str, str],
        question: str,
        top_k: int = 8,
        involved_types: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        path1_results = self.path1.retrieve(graph, chunks, question, top_k=top_k, involved_types=involved_types)
        path2_results = self.path2.retrieve(graph, question, top_k=top_k)

        triples: list[str] = []
        all_chunk_ids: list[str] = list(path1_results.get("chunk_ids", []))

        for u, r, v, _ in path1_results.get("one_hop_triples", []):
            triples.append(f"({u}, {r}, {v})")

        for u, r, v, _ in path2_results.get("scored_triples", []):
            triples.append(f"({u}, {r}, {v})")

        dedup_triples = list(dict.fromkeys(triples))[:top_k]
        ranked_chunk_ids = rank_chunk_ids(question, chunks, all_chunk_ids, top_k=top_k)
        chunk_contents = [chunks[cid] for cid in ranked_chunk_ids if cid in chunks]

        return {
            "triples": dedup_triples,
            "chunk_ids": ranked_chunk_ids,
            "chunk_contents": chunk_contents,
            "paths": path2_results.get("scored_triples", []),
            "path1_results": path1_results,
            "path2_results": path2_results,
        }

