# Semantic Justification Checker (Track B)

> **Research track** — not enabled by default. Requires the `semantic` extra.

## Overview

The standard suppression-justification checker uses a simple heuristic
(non-empty, non-boilerplate, contains a noun) to decide whether a
`# pylint: disable=...`, `# noqa`, or `# type: ignore` comment carries
a meaningful technical reason.

Track B replaces that heuristic with a **two-stage NLP pipeline** for
higher accuracy:

1. **Embedding similarity** — encodes the justification and its context
   into dense vectors and measures cosine similarity.
2. **Cross-encoder reranking** — re-scores the top candidates with a
   more expensive but more accurate pairwise model.

## Opt-in Mechanism

Install the optional dependency:

```bash
pip install python-setup[semantic]
# or
uv pip install python-setup[semantic]
```

Once `sentence-transformers` is importable, the semantic pipeline
activates automatically. If the package is not installed, the checker
falls back to the original heuristic with no change in behaviour.

## Two-Stage Pipeline

### Stage 1: Embedding (``BAAI/bge-small-en-v1.5``)

- **Model**: `BAAI/bge-small-en-v1.5` — a lightweight English embedding
  model (33M parameters) optimised for semantic similarity.
- **Input**: The justification text is encoded alongside a query string
  that includes the rule identifier and (when available) surrounding code
  context.
- **Decision**: Cosine similarity between the justification embedding
  and the query embedding. Below a threshold of 0.35, the justification
  is rejected as semantically unrelated or empty.

### Stage 2: Reranking (``jina-reranker-v2-base-multilingual``)

- **Model**: `jina-reranker-v2-base-multilingual` — a cross-encoder
  reranker that scores pairs of texts for relevance.
- **Input**: Pairs of (justification, query) where the query includes
  the rule and code context.
- **Decision**: Scores above 0.5 pass; below that threshold the
  justification is considered insufficient.

If the reranker is unavailable (download failure, OOM), the pipeline
accepts the justification provisionally when the embedding stage passes.

## Model Cache

Downloaded models are stored in `~/.cache/python-setup/semantic/`.
This directory is `.gitignore`d and reused across runs. Cache hits
avoid network downloads, making repeated invocations fast.

## Fallback Behaviour

| Condition | Result |
|---|---|
| `sentence-transformers` not installed | Heuristic (original) |
| Model download fails | Heuristic (original) |
| Embedding stage passes, reranker unavailable | Accept (provisional) |
| Both stages pass | Accept |
| Either stage rejects | Reject |

## Research Status

This is an experimental feature. The model choices, thresholds, and
pipeline architecture may change based on evaluation results.
Contributions and feedback are welcome.
