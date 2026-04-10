# lineage-graphrag

Lineage GraphRAG implementation for deterministic lineage JSON ingestion, four-level graph construction, retrieval, and what-if impact analysis.

## Quick Start

```bash
python -m pip install -e .[dev]
python scripts/run_api.py
```

`scripts/run_api.py` will load `configs/local.yaml` first (if present), otherwise `configs/base.yaml`.

Example:
```bash
python scripts/run_api.py --config configs/local.yaml
```

## API

- `POST /v1/graphs/import`
- `POST /v1/queries/ask`
- `POST /v1/impact/what-if`
- `GET /v1/graphs/{graph_id}/subgraph`

## Notes

- `POST /v1/graphs/import` now does import + normalize + build + snapshot + FalkorDB mirror in one step.
- `/v1/graphs/import` response includes `metadata/chunks/falkordb` and `auto_built=true`.
- New lineage import format:
  - `entities` is an object map keyed by entity id.
  - each entity includes `name/id/properties/description/children`, and `children` must be existing entity ids (or `[]`).
  - each transition includes `id/source/target/properties`, where `source/target` are entity ids.
- On service startup, graphs are auto-hydrated into memory:
  - First from snapshot files in `snapshot_dir` (`*_graph.json` + `*_chunks.json`).
  - Then from FalkorDB for graph IDs not already loaded (when FalkorDB is enabled/available).
- `POST /v1/queries/ask` supports `mode`:
  - `agent`: LLM decomposition + IRCoT iterative retrieval chain.
  - `noagent`: one-pass retrieval and answer generation.
- Retrieval is now dual-path FAISS-style:
  - Path 1: node + relation retrieval.
  - Path 2: triple + community retrieval.
- LLM provider selection supports multi-provider config in `app.llm`:
  - `active_provider` picks one provider in `providers`.
  - Provider item supports `provider/model/api_key/base_url/timeout_seconds`.
  - Environment override priority: `LINEAGE_LLM_ACTIVE_PROVIDER`, `LINEAGE_LLM_PROVIDER`, `LINEAGE_LLM_MODEL`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`.
  - For `active_provider: anyrouter`, `ANTHROPIC_BASE_URL` is also accepted as `base_url` override.
