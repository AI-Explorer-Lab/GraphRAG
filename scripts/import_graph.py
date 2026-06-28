from __future__ import annotations

import argparse
import json

from graph.kt_builder import GraphKTBuilder
from ingest.normalizer import GraphNormalizer
from ingest.parser import GraphParser
from mapper.snapshot_store import SnapshotStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="graph json path")
    parser.add_argument("--graph-id", required=True)
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        raw = json.load(f)

    graph_parser = GraphParser()
    normalizer = GraphNormalizer()
    builder = GraphKTBuilder()
    snapshot = SnapshotStore("data/normalized")

    parsed = graph_parser.parse(raw)
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
