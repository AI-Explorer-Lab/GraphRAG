# Operations

## Snapshots

Graphs are persisted as JSON snapshots under `snapshot_dir`.

Each graph has two files:

```text
<graph_id>_graph.json
<graph_id>_chunks.json
```

On startup, the API loads snapshots first. If FalkorDB is enabled, it then loads remote graphs that were not already restored from snapshots.

Snapshot files are generated runtime artifacts. If demo results look stale, clear the snapshot directory configured by `snapshot_dir` and import the graph again.

## FalkorDB

Start FalkorDB with Docker Compose:

```bash
docker compose -f deploy/docker-compose.falkordb.yml up -d
```

Default ports:

| Port | Purpose |
| --- | --- |
| `6379` | Redis-compatible FalkorDB endpoint |
| `3000` | FalkorDB browser/UI |

Enable FalkorDB mirroring when starting the API:

```bash
LINEAGE_USE_FALKORDB=true python scripts/run_api.py --config configs/base.yaml
```

On Windows PowerShell:

```powershell
$env:LINEAGE_USE_FALKORDB="true"
python scripts/run_api.py --config configs/base.yaml
```

The import response includes `falkordb.written`. A value of `true` means the graph mirror write succeeded.

## Common Checks

Check Python version:

```bash
python --version
```

The project supports Python `>=3.9`.

Run tests:

```bash
python -m pytest -q
```

Build retrieval indexes against a saved snapshot:

```bash
python scripts/build_indices.py --graph-id enterprise_video_lineage_complex
```

Import lineage from a local JSON file without starting the API:

```bash
python scripts/import_lineage.py --input tests/fixtures/video_platform_lineage.json --graph-id video_demo
```
