# Evaluation Status

The current `src/lineage_graphrag/evaluation` package contains smoke-check utilities:

- `retrieval_smoke_check(triples)`
- `answer_smoke_check(answer)`
- `impact_smoke_check(report)`

These utilities verify that the main flows return non-empty outputs. They are not a benchmark harness and do not measure retrieval precision, answer faithfulness, or impact-analysis recall.

## Current Test Coverage

The test suite covers:

- ingestion, normalization, and graph building
- dual-path retrieval returning Path 1 and Path 2 results
- FalkorDB graph partitioning
- impact analysis scope filtering
- API flows for `agent` and `noagent`
- restart hydration from snapshots

## Suggested Future Evaluation Layers

For a more production-grade evaluation story, add:

- golden questions with expected impacted nodes
- expected evidence chunk ids for retrieval checks
- answer faithfulness checks against retrieved chunks
- snapshot compatibility tests across schema versions
- FalkorDB integration tests behind an optional marker

Keep these as separate evaluation assets so normal unit tests stay fast and deterministic.
