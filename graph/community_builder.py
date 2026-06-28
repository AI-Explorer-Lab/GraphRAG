from __future__ import annotations

import re
from collections import Counter

import networkx as nx

from domain.models import ALLOWED_ENTITY_RELATIONS


class CommunityBuilder:
    """
    Level 3/4 construction (YouTu-Graph style adapted for graph):
    - Community detection fuses structural topology and semantic similarity.
    - Keywords are representative entity nodes (not free-form lexical tokens).
    - Representative links make member -> representative relation explicit.
    """

    def __init__(self, struct_weight: float = 0.3, keyword_top_k: int = 5) -> None:
        self.struct_weight = min(max(struct_weight, 0.0), 1.0)
        self.keyword_top_k = max(1, keyword_top_k)

    def build(self, graph: nx.MultiDiGraph) -> None:
        entity_nodes = [n for n, d in graph.nodes(data=True) if d.get("label") == "entity"]
        if not entity_nodes:
            return

        projected = self._build_projected_entity_graph(graph, entity_nodes)
        if projected.number_of_nodes() == 0:
            return

        token_map = {node_id: self._entity_tokens(graph, node_id) for node_id in entity_nodes}
        weighted_graph = self._build_dual_perceived_graph(projected, token_map)
        communities = self._detect_communities(weighted_graph)

        for idx, members in enumerate(communities):
            keyword_entities = self._keyword_representatives(weighted_graph, members, token_map, top_k=self.keyword_top_k)
            representative = keyword_entities[0] if keyword_entities else None
            community_id = f"comm_4_{idx}"

            graph.add_node(
                community_id,
                label="community",
                level=4,
                properties={
                    "name": self._community_name(graph, keyword_entities, idx),
                    "description": self._community_description(graph, representative, keyword_entities),
                    "members": members,
                    "representative": representative,
                    "keyword_entities": keyword_entities,
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

            self._link_representative(graph, community_id, members, representative)
            self._create_keyword_nodes(graph, community_id, idx, keyword_entities)

    def _build_projected_entity_graph(self, graph: nx.MultiDiGraph, entity_nodes: list[str]) -> nx.Graph:
        entity_set = set(entity_nodes)
        projected = nx.Graph()
        projected.add_nodes_from(entity_nodes)
        for u, v, edge_data in graph.edges(data=True):
            if u not in entity_set or v not in entity_set:
                continue
            relation = str(edge_data.get("relation", ""))
            if relation not in ALLOWED_ENTITY_RELATIONS and relation != "has":
                continue
            if projected.has_edge(u, v):
                projected[u][v]["weight"] += 1.0
            else:
                projected.add_edge(u, v, weight=1.0)
        return projected

    def _build_dual_perceived_graph(self, projected: nx.Graph, token_map: dict[str, set[str]]) -> nx.Graph:
        weighted = nx.Graph()
        weighted.add_nodes_from(projected.nodes())
        for u, v, edge_data in projected.edges(data=True):
            struct_score = float(edge_data.get("weight", 1.0))
            semantic_score = self._semantic_similarity(token_map.get(u, set()), token_map.get(v, set()))
            fused = self.struct_weight * struct_score + (1.0 - self.struct_weight) * semantic_score
            weighted.add_edge(u, v, weight=max(fused, 1e-4))
        return weighted

    def _detect_communities(self, weighted_graph: nx.Graph) -> list[list[str]]:
        if weighted_graph.number_of_nodes() <= 2 or weighted_graph.number_of_edges() == 0:
            return [sorted(list(c)) for c in nx.connected_components(weighted_graph)]
        try:
            groups = nx.algorithms.community.greedy_modularity_communities(weighted_graph, weight="weight")
            if groups:
                sorted_groups = [sorted(list(g)) for g in groups]
                return sorted(sorted_groups, key=lambda g: (len(g) * -1, g[0]))
        except Exception:
            pass
        return [sorted(list(c)) for c in nx.connected_components(weighted_graph)]

    def _keyword_representatives(
        self,
        weighted_graph: nx.Graph,
        members: list[str],
        token_map: dict[str, set[str]],
        top_k: int,
    ) -> list[str]:
        if not members:
            return []
        if len(members) == 1:
            return list(members)

        sub = weighted_graph.subgraph(members).copy()
        if sub.number_of_nodes() == 0:
            return []

        structural = {n: float(sub.degree(n, weight="weight")) for n in sub.nodes()}
        max_struct = max(structural.values()) if structural else 1.0
        structural_norm = {n: (score / max_struct if max_struct > 0 else 0.0) for n, score in structural.items()}

        semantic_raw = {n: self._community_semantic_score(n, members, token_map) for n in members}
        max_semantic = max(semantic_raw.values()) if semantic_raw else 1.0
        semantic_norm = {n: (score / max_semantic if max_semantic > 0 else 0.0) for n, score in semantic_raw.items()}

        combined = {
            n: self.struct_weight * structural_norm.get(n, 0.0) + (1.0 - self.struct_weight) * semantic_norm.get(n, 0.0)
            for n in members
        }
        ranked = sorted(combined.items(), key=lambda x: (-x[1], x[0]))
        return [n for n, _ in ranked[: min(top_k, len(ranked))]]

    def _community_semantic_score(
        self,
        node_id: str,
        members: list[str],
        token_map: dict[str, set[str]],
    ) -> float:
        self_tokens = token_map.get(node_id, set())
        if not self_tokens:
            return 0.0
        score = 0.0
        for other in members:
            if other == node_id:
                continue
            score += self._semantic_similarity(self_tokens, token_map.get(other, set()))
        return score / max(1, len(members) - 1)

    def _semantic_similarity(self, left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        inter = len(left & right)
        union = len(left | right)
        if union == 0:
            return 0.0
        return inter / union

    def _entity_tokens(self, graph: nx.MultiDiGraph, node_id: str) -> set[str]:
        props = graph.nodes[node_id].get("properties", {})
        parts = [
            str(props.get("name", "")),
            str(props.get("description", "")),
            str(props.get("schema_type", "")),
        ]
        raw_props = props.get("raw_properties", {})
        if isinstance(raw_props, dict):
            for k, v in raw_props.items():
                parts.append(str(k))
                parts.append(str(v))

        text = " ".join(parts).lower()
        tokens = re.findall(r"[a-z0-9_]+", text)
        counts = Counter(tok for tok in tokens if len(tok) > 2)
        for part in parts:
            compact = str(part).strip().lower()
            if compact and len(compact) > 1:
                counts[compact] += 1
        # Keep only informative tokens to avoid noise in tiny graphs.
        return {tok for tok, cnt in counts.items() if cnt >= 1}

    def _community_name(self, graph: nx.MultiDiGraph, keyword_entities: list[str], idx: int) -> str:
        if not keyword_entities:
            return f"community_{idx}"
        names = []
        for entity_id in keyword_entities[:2]:
            props = graph.nodes[entity_id].get("properties", {})
            raw_name = str(props.get("name", entity_id)).strip() or entity_id
            names.append(_slug(raw_name))
        return "community_" + "_".join(names)

    def _community_description(
        self,
        graph: nx.MultiDiGraph,
        representative: str | None,
        keyword_entities: list[str],
    ) -> str:
        if not representative and not keyword_entities:
            return "Auto-detected graph community."
        rep_name = _entity_display_name(graph, representative) if representative else "none"
        keyword_names = [_entity_display_name(graph, n) for n in keyword_entities]
        if not keyword_names:
            keyword_names = ["none"]
        return f"Representative: {rep_name}; Keywords: {', '.join(keyword_names)}"

    def _link_representative(
        self,
        graph: nx.MultiDiGraph,
        community_id: str,
        members: list[str],
        representative: str | None,
    ) -> None:
        if not representative:
            return

        graph.add_edge(
            representative,
            community_id,
            relation="represents_community",
            relation_properties={},
            source_id=representative,
            target_id=community_id,
            evidence_refs=[],
        )

        for member in members:
            if member == representative:
                continue
            graph.add_edge(
                member,
                representative,
                relation="represented_by",
                relation_properties={"community_id": community_id},
                source_id=member,
                target_id=representative,
                evidence_refs=[],
            )

    def _create_keyword_nodes(
        self,
        graph: nx.MultiDiGraph,
        community_id: str,
        idx: int,
        keyword_entities: list[str],
    ) -> None:
        for kw_idx, entity_id in enumerate(keyword_entities):
            keyword_id = f"kw_rep_{idx}_{kw_idx}_{_slug(entity_id)}"
            keyword_name = _entity_display_name(graph, entity_id)
            graph.add_node(
                keyword_id,
                label="keyword",
                level=3,
                properties={
                    "name": keyword_name,
                    "kind": "representative_entity",
                    "entity_id": entity_id,
                },
            )
            graph.add_edge(
                community_id,
                keyword_id,
                relation="has_keyword",
                relation_properties={},
                source_id=community_id,
                target_id=keyword_id,
                evidence_refs=[],
            )
            graph.add_edge(
                keyword_id,
                entity_id,
                relation="represents_entity",
                relation_properties={},
                source_id=keyword_id,
                target_id=entity_id,
                evidence_refs=[],
            )


def _entity_display_name(graph: nx.MultiDiGraph, entity_id: str | None) -> str:
    if not entity_id:
        return ""
    props = graph.nodes[entity_id].get("properties", {})
    name = str(props.get("name", entity_id)).strip()
    return name or entity_id


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "node"
