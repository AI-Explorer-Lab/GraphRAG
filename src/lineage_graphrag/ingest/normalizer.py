from __future__ import annotations

from lineage_graphrag.domain.lineage_models import HasRelation, LineageInput, NormalizedLineage


class LineageNormalizer:
    """Normalize lineage input and materialize hidden `has` relations."""

    def normalize(self, lineage: LineageInput) -> NormalizedLineage:
        has_relations = list(lineage.has_relations)
        entities = [lineage.entities[k] for k in sorted(lineage.entities.keys())]

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

        return NormalizedLineage(
            entities=entities,
            transitions=lineage.transitions,
            has_relations=has_relations,
        )
