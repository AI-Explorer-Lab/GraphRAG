from __future__ import annotations

from lineage_graphrag.domain.impact_models import ImpactPath


def filter_paths_for_target(paths: list[ImpactPath], target_node_id: str) -> list[ImpactPath]:
    return [p for p in paths if p.path and p.path[-1] == target_node_id]

