# Demo Walkthrough

This walkthrough uses the bundled video platform lineage example.

## 1. Start API

```bash
python -m pip install -e ".[dev]"
python scripts/run_api.py --config configs/base.yaml
```

## 2. Import Graph

```bash
curl -X POST "http://localhost:8001/v1/graphs/import" \
  -H "Content-Type: application/json" \
  --data @data/api_requests/01_graphs_import.json
```

Expected response shape:

```json
{
  "graph_id": "enterprise_video_lineage_complex",
  "metadata": {
    "entity_nodes": 0,
    "attribute_nodes": 0,
    "keyword_nodes": 0,
    "community_nodes": 0,
    "edges": 0
  },
  "chunks": 0,
  "auto_built": true
}
```

The exact counts depend on the input payload.

## 3. Inspect A Subgraph

```bash
curl "http://localhost:8001/v1/graphs/enterprise_video_lineage_complex/subgraph?node_id=dwd_video_profile&hops=2"
```

This returns graph nodes and edges around `dwd_video_profile`.

## 4. Ask A Question

```bash
curl -X POST "http://localhost:8001/v1/queries/ask" \
  -H "Content-Type: application/json" \
  --data @data/api_requests/03_queries_ask.json
```

Look for these fields:

- `answer`
- `sub_questions`
- `retrieval.triples`
- `retrieval.chunk_ids`
- `retrieval.reasoning_steps`

## 5. Run What-If Analysis

```bash
curl -X POST "http://localhost:8001/v1/impact/what-if" \
  -H "Content-Type: application/json" \
  --data @data/api_requests/04_impact_what_if.json
```

Look for:

- `direct_impacts`
- `indirect_impacts`
- `scoped_impact`
- `evidence_paths`
