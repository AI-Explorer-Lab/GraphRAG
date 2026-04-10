from __future__ import annotations

from lineage_graphrag.graph.kt_builder import LineageKTBuilder
from lineage_graphrag.ingest.normalizer import LineageNormalizer
from lineage_graphrag.ingest.parser import LineageParser
from lineage_graphrag.retrieval.orchestrator import LineageRetriever


def test_dual_path_retrieval_returns_path1_and_path2(fixture_payload: dict) -> None:
    parser = LineageParser()
    normalizer = LineageNormalizer()
    builder = LineageKTBuilder()
    retriever = LineageRetriever(enable_faiss=True)

    build_result = builder.build(normalizer.normalize(parser.parse(fixture_payload)))
    graph = build_result.graph
    chunks = build_result.evidence_chunks

    result = retriever.retrieve(
        graph=graph,
        chunks=chunks,
        question="What is downstream impact of dwd_video_profile?",
        top_k=8,
    )
    assert isinstance(result.get("chunk_ids"), list)
    assert len(result.get("chunk_ids", [])) > 0
    assert len(result.get("path1_results", {}).get("one_hop_triples", [])) > 0
    assert len(result.get("path2_results", {}).get("scored_triples", [])) > 0
