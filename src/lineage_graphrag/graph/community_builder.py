from __future__ import annotations

import re
from collections import Counter

import networkx as nx


STOPWORDS = {
    "the",
    "a",
    "an",
    "of",
    "to",
    "in",
    "on",
    "for",
    "and",
    "or",
    "by",
    "with",
    "is",
    "are",
    "be",
    "this",
    "that",
    "table",
    "job",
    "task",
    "field",
}


class CommunityBuilder:
    """
    Enhanced Level 3/4 construction:
    - Level 4: modularity-based community detection on entity relation graph.
    - Level 3: representative entity keywords + lexical keywords per community.
    """

    def build(self, graph: nx.MultiDiGraph) -> None:
        entity_nodes = [n for n, d in graph.nodes(data=True) if d.get("label") == "entity"]
        if not entity_nodes:
            return

        undirected = nx.Graph()
        undirected.add_nodes_from(entity_nodes)
        for u, v, edge_data in graph.edges(data=True):
            if u not in entity_nodes or v not in entity_nodes:
                continue
            relation = str(edge_data.get("relation", ""))
            if relation not in {"transitions", "has"}:
                continue
            if undirected.has_edge(u, v):
                undirected[u][v]["weight"] += 1.0
            else:
                undirected.add_edge(u, v, weight=1.0)

        communities = self._detect_communities(undirected)
        for idx, members in enumerate(communities):
            community_id = f"comm_4_{idx}"
            rep_entities = self._representative_entities(undirected, members, top_k=2)
            lex_keywords = self._lexical_keywords(graph, members, top_k=3)

            graph.add_node(
                community_id,
                label="community",
                level=4,
                properties={
                    "name": self._community_name(lex_keywords, idx),
                    "description": self._community_description(rep_entities, lex_keywords),
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

            self._create_keyword_nodes(graph, community_id, idx, rep_entities, lex_keywords)

    def _detect_communities(self, undirected: nx.Graph) -> list[list[str]]:
        if undirected.number_of_nodes() <= 2:
            return [list(c) for c in nx.connected_components(undirected)]
        try:
            groups = nx.algorithms.community.greedy_modularity_communities(undirected, weight="weight")
            if groups:
                return [list(g) for g in groups]
        except Exception:
            pass
        return [list(c) for c in nx.connected_components(undirected)]

    def _representative_entities(self, undirected: nx.Graph, members: list[str], top_k: int) -> list[str]:
        if not members:
            return []
        sub = undirected.subgraph(members).copy()
        if sub.number_of_nodes() == 1:
            return list(sub.nodes())
        try:
            scores = nx.pagerank(sub, weight="weight")
        except Exception:
            scores = {n: float(sub.degree(n)) for n in sub.nodes()}
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [n for n, _ in ranked[:top_k]]

    def _lexical_keywords(self, graph: nx.MultiDiGraph, members: list[str], top_k: int) -> list[str]:
        counter: Counter[str] = Counter()
        for member in members:
            props = graph.nodes[member].get("properties", {})
            text = " ".join([str(props.get("name", "")), str(props.get("description", ""))]).lower()
            tokens = re.findall(r"[a-z0-9_]+", text)
            for token in tokens:
                if token in STOPWORDS:
                    continue
                if len(token) <= 2:
                    continue
                counter[token] += 1
        return [token for token, _ in counter.most_common(top_k)]

    def _community_name(self, lex_keywords: list[str], idx: int) -> str:
        if not lex_keywords:
            return f"community_{idx}"
        return "community_" + "_".join(lex_keywords[:2])

    def _community_description(self, rep_entities: list[str], lex_keywords: list[str]) -> str:
        if not rep_entities and not lex_keywords:
            return "Auto-detected lineage community"
        reps = ", ".join(rep_entities) if rep_entities else "none"
        kws = ", ".join(lex_keywords) if lex_keywords else "none"
        return f"Representatives: {reps}; Keywords: {kws}"

    def _create_keyword_nodes(
        self,
        graph: nx.MultiDiGraph,
        community_id: str,
        idx: int,
        rep_entities: list[str],
        lex_keywords: list[str],
    ) -> None:
        for kw_idx, entity_id in enumerate(rep_entities):
            entity_name = graph.nodes[entity_id]["properties"].get("name", entity_id)
            keyword_id = f"kw_rep_{idx}_{kw_idx}"
            graph.add_node(
                keyword_id,
                label="keyword",
                level=3,
                properties={"name": str(entity_name), "kind": "representative"},
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

        for kw_idx, keyword in enumerate(lex_keywords):
            keyword_id = f"kw_term_{idx}_{kw_idx}"
            graph.add_node(
                keyword_id,
                label="keyword",
                level=3,
                properties={"name": keyword, "kind": "lexical"},
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

