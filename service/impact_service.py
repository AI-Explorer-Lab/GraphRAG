from __future__ import annotations

from domain.req import ImpactRequest
from exceptions import NotFoundException
from impact.propagation import ImpactAnalyzer
from mapper.graph_repository import GraphRepository


class ImpactService:
    def __init__(self, repo: GraphRepository) -> None:
        self.repo = repo

    def what_if_impact(self, payload: ImpactRequest) -> dict:
        graph = self.repo.get_graph(payload.graph_id)
        if graph is None:
            raise NotFoundException(f"graph_id '{payload.graph_id}' not built")

        analyzer = ImpactAnalyzer()
        report = analyzer.analyze(
            graph=graph,
            change_spec=payload.change_spec,
            target_node_id=payload.target_node_id,
        )
        return report.model_dump()
