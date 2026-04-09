from __future__ import annotations

from lineage_graphrag.domain.lineage_models import HasRelation, LineageInput, NormalizedLineage


class LineageNormalizer:
    """Normalize lineage input and materialize hidden `has` relations."""

    def normalize(self, lineage: LineageInput) -> NormalizedLineage:
        has_relations = list(lineage.has_relations)

        if not has_relations:
            for entity in lineage.entities:
                for child in entity.children:
                    has_relations.append(
                        HasRelation(
                            source=entity.id,
                            target=child,
                            properties={"origin": "children"},
                        )
                    )

        return NormalizedLineage(
            entities=lineage.entities,
            transitions=lineage.transitions,
            has_relations=has_relations,
        )

