from __future__ import annotations

from domain.models import HasRelation, GraphInput, NormalizedGraph


class GraphNormalizer:
    """Normalize graph input and materialize hidden `has` relations."""

    def normalize(self, graph: GraphInput) -> NormalizedGraph:
        has_relations = list(graph.has_relations)
        entities = [graph.entities[k] for k in sorted(graph.entities.keys())]

        if not has_relations:
            for entity in entities:
                for child in entity.children:
                    has_relations.append(
                        HasRelation(
                            source=entity.id,
                            target=child,
                            properties={"origin": "children"},
                        )
                    )

        return NormalizedGraph(
            entities=entities,
            transitions=graph.transitions,
            has_relations=has_relations,
        )
