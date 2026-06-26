# FalkorDB Runtime

FalkorDB is the durable graph store when enabled. The API keeps an in-memory cache for requests, and startup/manual sync load that cache from FalkorDB.

## Start FalkorDB

Recommended local startup:

```bash
docker compose -f deploy/docker-compose.falkordb.yml up -d
```

Exposed ports:

| Port | Purpose |
| --- | --- |
| `6379` | FalkorDB Redis-compatible endpoint |
| `3000` | FalkorDB browser/UI |

Open the browser UI at:

```text
http://localhost:3000
```

## Start API With FalkorDB Enabled

Linux/macOS:

```bash
LINEAGE_USE_FALKORDB=true python main.py --reload
```

Windows PowerShell:

```powershell
$env:LINEAGE_USE_FALKORDB="true"
python main.py --reload
```

## Import And Verify

`POST /v1/graphs/import` performs import, normalization, graph construction, and FalkorDB persistence in one request.

```bash
curl -X POST "http://localhost:8001/v1/graphs/import" \
  -H "Content-Type: application/json" \
  --data @data/api_requests/01_graphs_import.json
```

Check the response:

```json
{
  "falkordb": {
    "enabled": true,
    "available": true,
    "written": true
  }
}
```

If `written` is false, the API returns an error when FalkorDB is enabled. The graph is not treated as successfully imported.

## Sync Runtime Cache

Startup automatically syncs from FalkorDB when it is enabled. You can also trigger a manual sync:

```bash
curl -X POST "http://localhost:8001/v1/graphs/sync"
```

The frontend `Sync FalkorDB` button calls the same endpoint, then refreshes the graph id dropdown.


