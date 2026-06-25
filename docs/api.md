# API

The API is served by FastAPI. Start it with:

```bash
python scripts/run_api.py --config configs/base.yaml
```

Default URL:

```text
http://localhost:8001
```

## Import Graph

```http
POST /v1/graphs/import
```

Example:

```bash
curl -X POST "http://localhost:8001/v1/graphs/import" \
  -H "Content-Type: application/json" \
  --data @data/api_requests/01_graphs_import.json
```

Response fields:

| Field | Meaning |
| --- | --- |
| `graph_id` | Imported graph id |
| `metadata` | Graph node and edge counts |
| `chunks` | Number of generated evidence chunks |
| `falkordb` | Optional mirror write status |
| `entities` | Number of normalized entities |
| `transitions` | Number of transitions |
| `has_relations` | Number of hierarchy relations |
| `auto_built` | Always true for the current import flow |

`lineage_json.transitions[*].relation` is optional for backward compatibility. When provided, it must be one of:

```text
owns, uses, transfers_to, provides_to, scores, triggers
```

When omitted, the relation defaults to `transitions`.

## Ask Question

```http
POST /v1/queries/ask
```

Example:

```bash
curl -X POST "http://localhost:8001/v1/queries/ask" \
  -H "Content-Type: application/json" \
  --data @data/api_requests/03_queries_ask.json
```

Request fields:

| Field | Required | Meaning |
| --- | --- | --- |
| `graph_id` | yes | Graph id imported earlier |
| `question` | yes | Natural language question |
| `top_k` | no | Retrieval limit, default 8 |
| `mode` | no | `agent` or `noagent` |
| `max_steps` | no | Max IRCoT steps in agent mode |

Response fields:

| Field | Meaning |
| --- | --- |
| `answer` | Generated answer or deterministic fallback summary |
| `sub_questions` | Decomposition result |
| `involved_types` | Reserved compatibility field |
| `retrieval` | Triples, chunk ids, chunk contents, paths, mode, and reasoning steps |

## Get Subgraph

```http
GET /v1/graphs/{graph_id}/subgraph?node_id=<node>&hops=1
```

Example:

```bash
curl "http://localhost:8001/v1/graphs/enterprise_video_lineage_complex/subgraph?node_id=dwd_video_profile&hops=2"
```

The response contains `nodes` and `edges` with labels, levels, properties, relation properties, and evidence references.

## What-If Impact

```http
POST /v1/impact/what-if
```

Example:

```bash
curl -X POST "http://localhost:8001/v1/impact/what-if" \
  -H "Content-Type: application/json" \
  --data @data/api_requests/04_impact_what_if.json
```

Response fields:

| Field | Meaning |
| --- | --- |
| `direct_impacts` | Nodes at depth 1 downstream |
| `indirect_impacts` | Nodes at depth greater than 1 |
| `target_impact` | Paths to requested target node, when provided |
| `scoped_impact` | Impacted nodes filtered by scope/domain |
| `evidence_paths` | BFS paths and traversed relations |
