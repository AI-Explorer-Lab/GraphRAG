# FalkorDB Runtime

```bash
docker pull falkordb/falkordb:latest
docker compose -f deploy/docker-compose.falkordb.yml up -d
docker run -d --name falkordb -p 3000:3000 -p 6379:6379 falkordb/falkordb:latest
```

`6379:6379` is exposed by default for local visualization and client connectivity.

## API Import/Build Sequence

`/v1/graphs/import` now does import + build + FalkorDB mirror in one request.

To write graph data into FalkorDB:

1. Start API with FalkorDB enabled:
```powershell
$env:LINEAGE_USE_FALKORDB="true"
python scripts/run_api.py
```
2. Call `POST /v1/graphs/import`
3. Check import response field `falkordb.written` is `true`
