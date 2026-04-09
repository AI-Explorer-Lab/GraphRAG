from __future__ import annotations

import networkx as nx

from lineage_graphrag.common.types import GraphBuildResult
from lineage_graphrag.domain.lineage_models import NormalizedLineage
from lineage_graphrag.graph.community_builder import CommunityBuilder
from lineage_graphrag.ingest.evidence_builder import EvidenceBuilder


class LineageKTBuilder:
    """Deterministic Level1/2 construction + community augmentation."""

    def __init__(self) -> None:
        self.community_builder = CommunityBuilder()
        self.evidence_builder = EvidenceBuilder()

    def build(self, lineage: NormalizedLineage) -> GraphBuildResult:
        graph = nx.MultiDiGraph()
        chunks = self.evidence_builder.build(lineage)

        for entity in lineage.entities:
            entity_id = entity.id
            entity_chunk = f"entity::{entity_id}"
            schema_type = str(entity.properties.get("type", "entity"))
            graph.add_node(
                entity_id,
                label="entity",
                level=2,
                properties={
                    "id": entity_id,
                    "name": entity_id,
                    "description": entity.description,
                    "schema_type": schema_type,
                    "raw_properties": dict(entity.properties),
                },
            )

            for key, value in entity.properties.items():
                attr_id = f"attr::{entity_id}::{key}"
                graph.add_node(
                    attr_id,
                    label="attribute",
                    level=1,
                    properties={
                        "name": f"{key}:{value}",
                        "attr_key": key,
                        "attr_value": value,
                    },
                )
                graph.add_edge(
                    entity_id,
                    attr_id,
                    relation="has_attribute",
                    relation_properties={},
                    source_id=entity_id,
                    target_id=attr_id,
                    evidence_refs=[entity_chunk],
                )

            if entity.description:
                attr_id = f"attr::{entity_id}::description"
                graph.add_node(
                    attr_id,
                    label="attribute",
                    level=1,
                    properties={
                        "name": f"description:{entity.description}",
                        "attr_key": "description",
                        "attr_value": entity.description,
                    },
                )
                graph.add_edge(
                    entity_id,
                    attr_id,
                    relation="has_attribute",
                    relation_properties={},
                    source_id=entity_id,
                    target_id=attr_id,
                    evidence_refs=[entity_chunk],
                )

        for i, relation in enumerate(lineage.has_relations):
            self._ensure_child_entity_node(graph, relation.target)
            graph.add_edge(
                relation.source,
                relation.target,
                relation="has",
                relation_properties=dict(relation.properties),
                source_id=relation.source,
                target_id=relation.target,
                evidence_refs=[f"subgraph::{relation.source}"],
            )

        for i, transition in enumerate(lineage.transitions):
            self._ensure_child_entity_node(graph, transition.source)
            self._ensure_child_entity_node(graph, transition.target)
            graph.add_edge(
                transition.source,
                transition.target,
                relation="transitions",
                relation_properties=dict(transition.properties),
                source_id=transition.source,
                target_id=transition.target,
                evidence_refs=[f"transition::{transition.source}->{transition.target}::{i}"],
            )

        self.community_builder.build(graph)
        metadata = {
            "entity_nodes": len([1 for _, d in graph.nodes(data=True) if d.get("label") == "entity"]),
            "attribute_nodes": len([1 for _, d in graph.nodes(data=True) if d.get("label") == "attribute"]),
            "keyword_nodes": len([1 for _, d in graph.nodes(data=True) if d.get("label") == "keyword"]),
            "community_nodes": len([1 for _, d in graph.nodes(data=True) if d.get("label") == "community"]),
            "edges": graph.number_of_edges(),
        }
        return GraphBuildResult(graph=graph, evidence_chunks=chunks, metadata=metadata)

    def _ensure_child_entity_node(self, graph: nx.MultiDiGraph, entity_id: str) -> None:
        if entity_id in graph:
            return
        graph.add_node(
            entity_id,
            label="entity",
            level=2,
            properties={
                "id": entity_id,
                "name": entity_id,
                "description": "",
                "schema_type": "entity",
                "raw_properties": {},
            },
        )

