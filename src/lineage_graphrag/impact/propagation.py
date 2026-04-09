from __future__ import annotations

from collections import deque
from typing import Any

import networkx as nx

from lineage_graphrag.domain.impact_models import ChangeSpecModel, ImpactPath, ImpactReport


class ImpactAnalyzer:
    def analyze(
        self,
        graph: nx.MultiDiGraph,
        change_spec: ChangeSpecModel,
        target_node_id: str | None = None,
    ) -> ImpactReport:
        paths = self._downstream_paths(graph, change_spec.target, max_depth=change_spec.max_depth)
        direct = sorted({p.path[-1] for p in paths if p.depth == 1})
        indirect = sorted({p.path[-1] for p in paths if p.depth > 1})

        target_impact: list[str] = []
        if target_node_id:
            target_impact = self._target_impact(paths, target_node_id)

        scoped = self._scope_impact(graph, direct + indirect, change_spec.scope)
        return ImpactReport(
            direct_impacts=direct,
            indirect_impacts=indirect,
            target_impact=target_impact,
            scoped_impact=scoped,
            evidence_paths=paths,
        )

    def _downstream_paths(self, graph: nx.MultiDiGraph, start: str, max_depth: int) -> list[ImpactPath]:
        if start not in graph:
            return []
        queue = deque([(start, [start], [], 0)])
        seen: set[tuple[str, int]] = set()
        paths: list[ImpactPath] = []

        while queue:
            node, path_nodes, path_relations, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for _, nxt, edge_data in graph.out_edges(node, data=True):
                relation = edge_data.get("relation", "")
                next_depth = depth + 1
                state = (nxt, next_depth)
                if state in seen:
                    continue
                seen.add(state)
                next_nodes = path_nodes + [nxt]
                next_relations = path_relations + [relation]
                paths.append(ImpactPath(path=next_nodes, relations=next_relations, depth=next_depth))
                queue.append((nxt, next_nodes, next_relations, next_depth))
        return paths

    def _target_impact(self, paths: list[ImpactPath], target_node_id: str) -> list[str]:
        impacts = []
        for p in paths:
            if p.path and p.path[-1] == target_node_id:
                impacts.append(" -> ".join(p.path))
        return impacts

    def _scope_impact(self, graph: nx.MultiDiGraph, impacted_nodes: list[str], scope: str | None) -> list[str]:
        if not scope:
            return []
        scope_l = scope.lower()
        output = []
        for node in impacted_nodes:
            props: dict[str, Any] = graph.nodes[node].get("properties", {})
            domain = str(props.get("raw_properties", {}).get("domain", props.get("domain", ""))).lower()
            if scope_l and scope_l == domain:
                output.append(node)
        return sorted(set(output))

