from __future__ import annotations

import pytest

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


def test_controlled_transition_relation_is_materialized() -> None:
    payload = {
        "entities": {
            "src_risk_feature": {
                "id": "src_risk_feature",
                "name": "src_risk_feature",
                "properties": {"type": "feature"},
                "children": [],
            },
            "mdl_fraud_score": {
                "id": "mdl_fraud_score",
                "name": "mdl_fraud_score",
                "properties": {"type": "model"},
                "children": [],
            },
        },
        "transitions": [
            {
                "id": "tr_feature_to_model",
                "source": "src_risk_feature",
                "target": "mdl_fraud_score",
                "relation": "provides_to",
                "properties": {"feature_version": "v1"},
            }
        ],
    }

    graph = LineageKTBuilder().build(LineageNormalizer().normalize(LineageParser().parse(payload))).graph

    assert any(
        u == "src_risk_feature" and v == "mdl_fraud_score" and d.get("relation") == "provides_to"
        for u, v, d in graph.edges(data=True)
    )


def test_unknown_transition_relation_is_rejected() -> None:
    payload = {
        "entities": {
            "a": {"id": "a", "name": "a", "children": []},
            "b": {"id": "b", "name": "b", "children": []},
        },
        "transitions": [
            {
                "id": "tr_bad",
                "source": "a",
                "target": "b",
                "relation": "free_form_relation",
            }
        ],
    }

    with pytest.raises(ValueError, match="not supported"):
        LineageParser().parse(payload)
