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
- `POST /v1/graphs/build`
- `POST /v1/queries/ask`
- `POST /v1/impact/what-if`
- `GET /v1/graphs/{graph_id}/subgraph`

## Notes

- `POST /v1/graphs/import` only imports and normalizes lineage JSON.
- Use `POST /v1/graphs/build` to construct graph and mirror it to FalkorDB (when `LINEAGE_USE_FALKORDB=true`).
- `/v1/graphs/build` response now includes `falkordb` status (enabled/available/written/error).
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
