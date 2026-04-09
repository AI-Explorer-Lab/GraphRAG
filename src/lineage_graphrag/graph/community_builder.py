from __future__ import annotations

import networkx as nx


class CommunityBuilder:
    """
    Lightweight Level 3/4 construction:
    - Level 4: communities from connected components on entity-only undirected graph.
    - Level 3: keyword nodes from top-degree entities in each community.
    """

    def build(self, graph: nx.MultiDiGraph) -> None:
        entity_nodes = [n for n, d in graph.nodes(data=True) if d.get("label") == "entity"]
        if not entity_nodes:
            return

        undirected = nx.Graph()
        undirected.add_nodes_from(entity_nodes)

        for u, v, edge_data in graph.edges(data=True):
            if u in entity_nodes and v in entity_nodes:
                relation = edge_data.get("relation")
                if relation in {"transitions", "has"}:
                    undirected.add_edge(u, v)

        for idx, members in enumerate(nx.connected_components(undirected)):
            members = list(members)
            community_id = f"comm_4_{idx}"
            graph.add_node(
                community_id,
                label="community",
                level=4,
                properties={
                    "name": f"community_{idx}",
                    "description": f"Auto-detected community {idx}",
                    "members": members,
                },
            )
            for member in members:
                graph.add_edge(
                    member,
                    community_id,
                    relation="member_of",
                    relation_properties={},
                    source_id=member,
                    target_id=community_id,
                    evidence_refs=[],
                )

            degree_scores = sorted(undirected.degree(members), key=lambda x: x[1], reverse=True)
            top_keywords = [node for node, _ in degree_scores[: min(2, len(degree_scores))]]

            for kw_idx, entity_id in enumerate(top_keywords):
                entity_name = graph.nodes[entity_id]["properties"].get("name", entity_id)
                keyword_id = f"kw_{idx}_{kw_idx}"
                graph.add_node(
                    keyword_id,
                    label="keyword",
                    level=3,
                    properties={"name": entity_name},
                )
                graph.add_edge(
                    entity_id,
                    keyword_id,
                    relation="represented_by",
                    relation_properties={},
                    source_id=entity_id,
                    target_id=keyword_id,
                    evidence_refs=[],
                )
                graph.add_edge(
                    keyword_id,
                    community_id,
                    relation="keyword_of",
                    relation_properties={},
                    source_id=keyword_id,
                    target_id=community_id,
                    evidence_refs=[],
                )

