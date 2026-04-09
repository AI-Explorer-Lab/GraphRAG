from __future__ import annotations

from lineage_graphrag.domain.impact_models import ChangeSpecModel
from lineage_graphrag.graph.kt_builder import LineageKTBuilder
from lineage_graphrag.impact.propagation import ImpactAnalyzer
from lineage_graphrag.ingest.normalizer import LineageNormalizer
from lineage_graphrag.ingest.parser import LineageParser


def test_impact_analysis_scope(fixture_payload: dict) -> None:
    parser = LineageParser()
    normalizer = LineageNormalizer()
    builder = LineageKTBuilder()
    analyzer = ImpactAnalyzer()

    graph = builder.build(normalizer.normalize(parser.parse(fixture_payload))).graph

    report = analyzer.analyze(
        graph,
        ChangeSpecModel(
            source="job_video_tag_enrich",
            target="dwd_video_profile",
            relation="transitions",
            scope="moderation",
            max_depth=3,
        ),
    )
    assert "moderation_rule_engine" in report.scoped_impact
    assert len(report.direct_impacts) >= 1

