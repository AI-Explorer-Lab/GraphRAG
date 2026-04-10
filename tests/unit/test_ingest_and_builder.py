from __future__ import annotations

from lineage_graphrag.graph.kt_builder import LineageKTBuilder
from lineage_graphrag.ingest.normalizer import LineageNormalizer
from lineage_graphrag.ingest.parser import LineageParser


def test_parser_normalizer_build(fixture_payload: dict) -> None:
    parser = LineageParser()
    normalizer = LineageNormalizer()
    builder = LineageKTBuilder()

    parsed = parser.parse(fixture_payload)
    normalized = normalizer.normalize(parsed)
    result = builder.build(normalized)
    graph = result.graph

    assert len(normalized.entities) == 7
    assert len(normalized.transitions) == 6
    assert len(normalized.has_relations) > 0

    assert "job_video_tag_enrich" in graph.nodes
    assert any(
        d.get("relation") == "transitions"
        and u == "job_video_tag_enrich"
        and v == "dwd_video_profile"
        and "logic" in d.get("relation_properties", {})
        for u, v, d in graph.edges(data=True)
    )
    assert any(d.get("label") == "community" for _, d in graph.nodes(data=True))
    assert any(d.get("label") == "keyword" for _, d in graph.nodes(data=True))
    assert not any(d.get("relation") == "keyword_of" for _, _, d in graph.edges(data=True))
    assert any(
        d.get("relation") == "represented_by" and graph.nodes[v].get("label") == "entity"
        for u, v, d in graph.edges(data=True)
    )
    assert any(d.get("relation") == "has_keyword" for _, _, d in graph.edges(data=True))
