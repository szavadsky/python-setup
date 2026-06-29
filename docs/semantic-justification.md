# Semantic Justification Checker

> **Experimental feature** — enabled by default via `PYTHON_SETUP_LINT_SEMANTIC=1` env var; activates when `sentence-transformers` is importable. Disable with `PYTHON_SETUP_LINT_SEMANTIC=0`.

# Overview

The standard suppression-justification checker uses a simple heuristic (non-empty, non-boilerplate, not equal to the rule symbol) to decide whether a `# pylint: disable=...`, `# noqa`, or `# type: ignore` comment carries a meaningful technical reason.

The semantic pipeline replaces that heuristic with a **reranker-first with heuristic fallback** pipeline for higher accuracy:

1. **Cross-encoder reranker** — re-scores the justification against its context with a pairwise model. Scores above 0.5 pass; below that threshold the justification is considered insufficient.
2. **Heuristic fallback** — fast, zero-dependency check that rejects empty, boilerplate, or rule-symbol-only justifications. Used when the reranker is unavailable or returns `None`.

If the reranker is unavailable (model download failure, OOM, `sentence-transformers` not installed), the pipeline defers to the heuristic fallback.

## Opt-in Mechanism

The semantic pipeline is **enabled by default** (``PYTHON_SETUP_LINT_SEMANTIC=1``). The ``_semantic`` module is imported lazily — only when the env var is set — inside ``check_if_meaningful``; the env var gates both the import and whether the reranker runs. With ``PYTHON_SETUP_LINT_SEMANTIC=0`` the module is never imported and the heuristic runs alone. Install the optional dependency:

```bash
pip install python-setup[semantic]
# or
uv pip install python-setup[semantic]
```

Once `sentence-transformers` is importable, the semantic pipeline activates automatically. If the package is not installed, the checker falls back to the original heuristic with no change in behaviour.

To disable the semantic pipeline without uninstalling:

```bash
PYTHON_SETUP_LINT_SEMANTIC=0 uv run lint
```

## Model Cache

Downloaded models are stored in `~/.cache/python-setup/semantic/`. This directory is `.gitignore`d and reused across runs. Models are loaded once and cached in memory (singleton pattern) — subsequent calls reuse the already-loaded instance.

## Result Cache

Semantic check results are cached both in-memory and on disk:

- **In-memory**: `_RESULT_CACHE` dict, keyed by SHA-256 hash of (text, rule, code_context, comment, model ID).
- **On disk**: `~/.cache/python-setup/semantic/results.json`, lazy-loaded on first access and written on new entries.

This prevents recomputation for identical inputs within and across processes.

## Fallback Behaviour

| Condition | Result |
|---|---|
| `sentence-transformers` not installed | Heuristic (original) |
| Model download fails | Heuristic (original) |
| Reranker score available | Accept at >= 0.5 threshold |
| Reranker score below threshold | Reject |

## Test Strategy

Tests that require network access (model download) are marked ``@pytest.mark.slow``. Tests that hit the local model cache are **not** marked slow. Semantic tests that require the model use ``pytest.importorskip``; cache-hit and heuristic tests run without the model.

## Research Status

This is an experimental feature. The model choices, thresholds, and pipeline architecture may change based on evaluation results. Contributions and feedback are welcome.
