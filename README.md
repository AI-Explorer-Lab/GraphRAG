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
