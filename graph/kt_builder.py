from __future__ import annotations

import networkx as nx

from utils.types import GraphBuildResult
from domain.models import NormalizedGraph
from graph.community_builder import CommunityBuilder
from ingest.evidence_builder import EvidenceBuilder


class GraphKTBuilder:
    """Deterministic Level1/2 construction + community augmentation."""

    def __init__(self) -> None:
        self.community_builder = CommunityBuilder()
        self.evidence_builder = EvidenceBuilder()

    def build(self, normalized_graph: NormalizedGraph) -> GraphBuildResult:
        nx_graph = nx.MultiDiGraph()
        chunks = self.evidence_builder.build(normalized_graph)

        for entity in normalized_graph.entities:
            entity_id = entity.id
            entity_chunk = f"entity::{entity_id}"
            schema_type = str(entity.properties.get("type", "entity"))
            entity_name = entity.name.strip() if isinstance(entity.name, str) else ""
            if not entity_name:
                entity_name = entity_id
            nx_graph.add_node(
                entity_id,
                label="entity",
                level=2,
                properties={
                    "id": entity_id,
                    "name": entity_name,
                    "description": entity.description,
                    "schema_type": schema_type,
                    "raw_properties": dict(entity.properties),
                },
            )

            for key, value in entity.properties.items():
                attr_id = f"attr::{entity_id}::{key}"
                nx_graph.add_node(
                    attr_id,
                    label="attribute",
                    level=1,
                    properties={
                        "name": str(value),
                        "attr_key": key,
                        "attr_value": value,
                    },
                )
                nx_graph.add_edge(
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
                nx_graph.add_node(
                    attr_id,
                    label="attribute",
                    level=1,
                    properties={
                        "name": entity.description,
                        "attr_key": "description",
                        "attr_value": entity.description,
                    },
                )
                nx_graph.add_edge(
                    entity_id,
                    attr_id,
                    relation="has_attribute",
                    relation_properties={},
                    source_id=entity_id,
                    target_id=attr_id,
                    evidence_refs=[entity_chunk],
                )

        for i, relation in enumerate(normalized_graph.has_relations):
            self._ensure_child_entity_node(nx_graph, relation.target)
            nx_graph.add_edge(
                relation.source,
                relation.target,
                relation="has",
                relation_properties=dict(relation.properties),
                source_id=relation.source,
                target_id=relation.target,
                evidence_refs=[f"subgraph::{relation.source}"],
            )

        for transition in normalized_graph.transitions:
            self._ensure_child_entity_node(nx_graph, transition.source)
            self._ensure_child_entity_node(nx_graph, transition.target)
            rel_props = dict(transition.properties)
            rel_props["transition_id"] = transition.id
            nx_graph.add_edge(
                transition.source,
                transition.target,
                relation=transition.relation,
                relation_properties=rel_props,
                source_id=transition.source,
                target_id=transition.target,
                evidence_refs=[f"transition::{transition.id}"],
            )

        self.community_builder.build(nx_graph)
        metadata = {
            "entity_nodes": len([1 for _, d in nx_graph.nodes(data=True) if d.get("label") == "entity"]),
            "attribute_nodes": len([1 for _, d in nx_graph.nodes(data=True) if d.get("label") == "attribute"]),
            "keyword_nodes": len([1 for _, d in nx_graph.nodes(data=True) if d.get("label") == "keyword"]),
            "community_nodes": len([1 for _, d in nx_graph.nodes(data=True) if d.get("label") == "community"]),
            "edges": nx_graph.number_of_edges(),
        }
        return GraphBuildResult(graph=nx_graph, evidence_chunks=chunks, metadata=metadata)

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
