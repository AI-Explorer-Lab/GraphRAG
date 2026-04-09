from __future__ import annotations

import argparse
import json

from lineage_graphrag.graph.kt_builder import LineageKTBuilder
from lineage_graphrag.ingest.normalizer import LineageNormalizer
from lineage_graphrag.ingest.parser import LineageParser
from lineage_graphrag.storage.snapshot_store import SnapshotStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="lineage json path")
    parser.add_argument("--graph-id", required=True)
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        raw = json.load(f)

    lineage_parser = LineageParser()
    normalizer = LineageNormalizer()
    builder = LineageKTBuilder()
    snapshot = SnapshotStore("data/normalized")

    parsed = lineage_parser.parse(raw)
    normalized = normalizer.normalize(parsed)
    result = builder.build(normalized)
    snapshot.save(args.graph_id, result.graph, result.evidence_chunks)
    print(
        json.dumps(
            {
                "graph_id": args.graph_id,
                "metadata": result.metadata,
                "chunks": len(result.evidence_chunks),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

