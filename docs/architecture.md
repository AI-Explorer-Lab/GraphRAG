# Architecture

Lineage GraphRAG has three main paths:

1. Ingestion and graph construction.
2. Graph-aware retrieval and QA.
3. What-if downstream impact analysis.

## Ingestion Path

```text
ImportRequest
  -> LineageParser.parse()
  -> LineageNormalizer.normalize()
  -> LineageKTBuilder.build()
  -> GraphRepository.save_graph()
  -> SnapshotStore.save()
  -> optional FalkorDBClient.write_graph()
```

Key implementation files:

- `src/lineage_graphrag/ingest/parser.py`
- `src/lineage_graphrag/ingest/normalizer.py`
- `src/lineage_graphrag/ingest/evidence_builder.py`
- `src/lineage_graphrag/graph/kt_builder.py`
- `src/lineage_graphrag/graph/community_builder.py`

The parser accepts the canonical lineage format:

```json
{
  "entities": {
    "entity_id": {
      "id": "entity_id",
      "name": "entity_id",
      "properties": {},
      "description": "",
      "children": []
    }
  },
  "transitions": [
    {
      "id": "transition_id",
      "source": "source_entity_id",
      "target": "target_entity_id",
      "relation": "transitions",
      "properties": {}
    }
  ]
}
```

The normalizer materializes missing `has_relations` from entity `children`, making hierarchy explicit in the graph.

## Four-Level Graph

The graph is a `networkx.MultiDiGraph` with four labels:

| Level | Label | Meaning |
| --- | --- | --- |
| 1 | `attribute` | Property and description nodes derived from entities |
| 2 | `entity` | Core lineage nodes such as tables, jobs, services, topics, or domains |
| 3 | `keyword` | Representative entity keyword nodes for communities |
| 4 | `community` | Automatically detected lineage communities |

Entity-to-entity transition relations are intentionally controlled. New business examples should use one of these six relation types:

| Relation | Meaning |
| --- | --- |
| `owns` | Ownership or binding, such as user owns account or account owns wallet |
| `uses` | Usage relation, such as user uses device or account uses channel |
| `transfers_to` | Money or value moves from one entity to another |
| `provides_to` | Data, feature, profile, or signal flows from upstream to downstream |
| `scores` | Model, rule, or service scores an entity |
| `triggers` | Event, rule, score, or decision triggers another step |

The legacy `transitions` relation remains supported for existing lineage payloads.

Internal graph relation types:

| Relation | Source -> Target | Meaning |
| --- | --- | --- |
| `has_attribute` | entity -> attribute | Entity owns a property or description attribute |
| `has` | entity -> entity | Parent-child lineage hierarchy |
| `transitions` | entity -> entity | Backward-compatible default lineage transition |
| `member_of` | entity -> community | Entity belongs to an auto-detected community |
| `represents_community` | entity -> community | Representative entity for a community |
| `represented_by` | entity -> entity | Entity is represented by the community representative |
| `has_keyword` | community -> keyword | Community has a representative keyword node |
| `represents_entity` | keyword -> entity | Keyword node points back to the representative entity |

Edges carry `evidence_refs`, which point to evidence chunks such as `entity::<id>`, `transition::<id>`, or `subgraph::<id>`.

## Community Construction

`CommunityBuilder` projects the graph down to entity nodes and keeps `has` plus controlled entity transition relations. It then builds a weighted graph by fusing:

- structural edge weight
- token overlap similarity from entity name, description, schema type, and raw properties

The default structural weight is `0.3`. Community detection uses NetworkX greedy modularity. Representative entities are selected by combining weighted degree and semantic similarity to other members.

## Retrieval Path

```text
AskRequest
  -> AgenticIRCoT.run()
  -> LineageQuestionDecomposer.decompose()
  -> LineageRetriever.retrieve()
  -> DualPathFAISSRetriever.retrieve()
  -> rank_chunk_ids()
  -> AnswerGenerator.generate()
```

`DualPathFAISSRetriever` builds five indexes:

- entity node texts
- relation texts
- triple texts
- community texts
- evidence chunk texts

Path 1 retrieves entity nodes and relation texts, then expands one-hop incoming and outgoing graph edges.

Path 2 retrieves triples and communities. Community hits expand through membership and keyword/representative links.

Evidence chunk ids are merged, deduplicated, and reranked with token overlap.

## QA Modes

`agent` mode:

1. Decompose the question into retrievable sub-questions.
2. Retrieve evidence for each sub-question.
3. Generate an initial answer.
4. If an LLM is available, run iterative retrieval chain-of-thought prompts.
5. Stop when the LLM emits a final answer or no useful new query is produced.

`noagent` mode:

1. Decompose the question.
2. Retrieve once.
3. Generate a single answer.

## Impact Path

`ImpactAnalyzer` starts from `change_spec.target` and walks downstream along outgoing graph edges with BFS. It returns:

- `direct_impacts`: depth 1 nodes
- `indirect_impacts`: depth greater than 1 nodes
- `target_impact`: paths ending at a requested target node
- `scoped_impact`: impacted nodes whose domain matches `change_spec.scope`
- `evidence_paths`: traversed paths and relation names
