# Configuration

Configuration is loaded by `AppConfig.from_yaml()` in `src/lineage_graphrag/common/config.py`.

The default runtime config is:

```text
configs/base.yaml
```

`scripts/run_api.py` accepts an explicit config path:

```bash
python scripts/run_api.py --config configs/base.yaml
```

## Core Settings

| Key | Meaning |
| --- | --- |
| `use_falkordb` | Whether to mirror graphs to FalkorDB |
| `falkordb_url` | Redis/FalkorDB connection URL |
| `snapshot_dir` | Directory for `*_graph.json` and `*_chunks.json` snapshots |
| `default_top_k` | Default retrieval limit |
| `default_ask_mode` | Default query mode, usually `agent` |
| `agent_max_steps` | Max IRCoT iterations |
| `decomposer_max_sub_questions` | Max decomposed sub-questions |
| `retrieval_embedding_model` | SentenceTransformers model name |
| `enable_faiss` | Use FAISS when installed |

## LLM Settings

The default config uses the `stub` provider. With `stub`, no remote LLM call is made and answer generation falls back to deterministic summaries.

Provider config lives under:

```yaml
app:
  llm:
    active_provider: stub
    providers:
      stub:
        provider: stub
      openai:
        provider: openai
```

Environment variables can override YAML values:

| Environment variable | Meaning |
| --- | --- |
| `LINEAGE_LLM_ACTIVE_PROVIDER` | Selects one provider block |
| `LINEAGE_LLM_PROVIDER` | Runtime provider value |
| `LINEAGE_LLM_MODEL` | Model name |
| `OPENAI_API_KEY` | API key for OpenAI-compatible providers |
| `OPENAI_BASE_URL` | Optional OpenAI-compatible base URL |
| `OPENAI_TIMEOUT_SECONDS` | Request timeout |

## Retrieval Runtime

Embeddings are produced by `EmbeddingIndex`.

Behavior:

1. Try to load `sentence-transformers` with `local_files_only=True`.
2. If unavailable, fall back to deterministic hashed bag-of-words vectors.
3. Use FAISS when available and `enable_faiss=true`.
4. Fall back to NumPy dot-product search when FAISS is unavailable.

This makes the project runnable in offline environments, with lower retrieval quality when no embedding model is locally cached.
