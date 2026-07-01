from __future__ import annotations

from domain.models import HasRelation, GraphInput, NormalizedGraph


class GraphNormalizer:
    """Normalize graph input and materialize hidden `has` relations."""

    def normalize(self, graph: GraphInput) -> NormalizedGraph:
        has_relations: list[HasRelation] = []
        seen_has_pairs: set[tuple[str, str]] = set()
        entities = [graph.entities[k] for k in sorted(graph.entities.keys())]

        for relation in graph.has_relations:
            pair = (relation.source, relation.target)
            if pair in seen_has_pairs:
                continue
            seen_has_pairs.add(pair)
            has_relations.append(relation)

        for entity in entities:
            for child in entity.children:
                pair = (entity.id, child)
                if pair in seen_has_pairs:
                    continue
                seen_has_pairs.add(pair)
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
