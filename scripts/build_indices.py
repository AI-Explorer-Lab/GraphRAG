from __future__ import annotations

import argparse
import json
from pathlib import Path

from lineage_graphrag.common.config import AppConfig
from lineage_graphrag.graph.serializer import load_graph_from_json
from lineage_graphrag.retrieval.orchestrator import LineageRetriever


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph-id", required=True, help="graph id used in data/normalized snapshots")
    parser.add_argument("--config", default="configs/base.yaml")
    parser.add_argument("--graph-path", default=None)
    parser.add_argument("--chunk-path", default=None)
    parser.add_argument("--probe-query", default="lineage impact analysis")
    args = parser.parse_args()

    graph_path = Path(args.graph_path or f"data/normalized/{args.graph_id}_graph.json")
    chunk_path = Path(args.chunk_path or f"data/normalized/{args.graph_id}_chunks.json")

    graph = load_graph_from_json(graph_path)
    with open(chunk_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    cfg = AppConfig.from_yaml(args.config)
    retriever = LineageRetriever.from_config(cfg)
    result = retriever.retrieve(graph=graph, chunks=chunks, question=args.probe_query, top_k=8)
    print(
        json.dumps(
            {
                "graph_id": args.graph_id,
                "graph_nodes": graph.number_of_nodes(),
                "graph_edges": graph.number_of_edges(),
                "chunks": len(chunks),
                "retrieved_triples": len(result.get("triples", [])),
                "retrieved_chunk_ids": len(result.get("chunk_ids", [])),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

