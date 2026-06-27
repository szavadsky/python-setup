"""Semantic justification checker using a cross-encoder reranker (Track B).

Single-stage NLP pipeline for evaluating suppression justification quality:

1. **Cross-encoder reranking** (``jina-reranker-v2-base-multilingual``):
   Re-score the justification against the rule and code context with a
   dedicated cross-encoder for higher accuracy.

The model is loaded lazily (inside function calls, never at module level).
On ``ImportError`` (sentence-transformers not installed) or model download
failure, ``semantic_check_if_meaningful`` returns ``None``, signalling the
caller to fall back to the heuristic check.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

# Cache directory for downloaded models (idempotent, .gitignored).
_CACHE_DIR = Path.home() / ".cache" / "python-setup" / "semantic"

# Model singleton cache (loaded once, reused across calls).
_RERANKER_INSTANCE = None

# Persisted result cache file.
_RESULT_CACHE_FILE = _CACHE_DIR / "results.json"
# Loaded from disk at module level, written on new entries.
_RESULT_CACHE: dict[int, bool] = {}


def _load_result_cache() -> dict[int, bool]:
    """Load the persisted result cache from disk."""
    try:
        raw = _RESULT_CACHE_FILE.read_text()
        return {int(k): v for k, v in json.loads(raw).items()}
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return {}


def _save_result_cache() -> None:
    """Persist the result cache to disk."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _RESULT_CACHE_FILE.write_text(
            json.dumps({str(k): v for k, v in _RESULT_CACHE.items()})
        )
    except OSError:
        pass  # cache write is best-effort


# Load persisted cache at module level.
_RESULT_CACHE = _load_result_cache()

_RERANKER_MODEL = "jina-reranker-v2-base-multilingual"


def _get_cache_dir() -> Path:
    """Return the model cache directory, creating it if necessary."""
    cache = _CACHE_DIR
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _load_reranker():
    """Lazy-load the cross-encoder reranker model.

    Returns:
        CrossEncoder instance, or ``None`` on failure.
    """
    global _RERANKER_INSTANCE
    if _RERANKER_INSTANCE is not None:
        return _RERANKER_INSTANCE
    try:
        from sentence_transformers import CrossEncoder
    except ImportError:
        return None

    try:
        cache = _get_cache_dir()
        _RERANKER_INSTANCE = CrossEncoder(
            _RERANKER_MODEL,
            cache_folder=str(cache),
        )
        return _RERANKER_INSTANCE
    except (
        OSError,
        RuntimeError,
        ValueError,
    ):  # network / download failures are expected
        return None


def semantic_check_if_meaningful(
    text: str,
    *,
    rule: str | None = None,
    code_context: str | None = None,
    comment: str | None = None,
) -> bool | None:
    """Check if a suppression justification is semantically meaningful.

    Single-stage NLP pipeline using a cross-encoder reranker:

    1. Re-score the justification against the rule and code context.

    Args:
        text: The raw justification text (used as fallback when *comment*
            is not provided).
        rule: The lint rule identifier being suppressed (e.g. ``"E501"``).
        code_context: Surrounding source code lines.
        comment: The justification comment text (preferred over *text*).

    Returns:
        ``True`` if the justification is semantically meaningful,
        ``False`` otherwise, or ``None`` if the NLP pipeline is unavailable
        (sentence-transformers not installed or model download failed).
    """
    primary = (comment or text).strip()
    if not primary:
        return False

    # Compute cache key from all inputs + model identifier.
    cache_key = hashlib.sha256(
        "|".join(
            str(x)
            for x in (
                text,
                rule,
                code_context,
                comment,
                _RERANKER_MODEL,
            )
        ).encode()
    ).digest()
    cache_key_int = int.from_bytes(cache_key[:8], "big")
    if cache_key_int in _RESULT_CACHE:
        return _RESULT_CACHE[cache_key_int]

    # --- Cross-encoder reranking ---
    reranker = _load_reranker()
    if reranker is None:
        return None  # signal fallback to heuristic

    # Build a query string from the available context.
    query_parts = [primary]
    if rule:
        query_parts.append(f"rule: {rule}")
    if code_context:
        query_parts.append(f"context: {code_context[:200]}")  # truncate to avoid OOM

    query = " | ".join(query_parts)

    try:
        pairs = [(primary, query)]
        scores = reranker.predict(pairs)
        score = float(scores[0])
    except (
        OSError,
        RuntimeError,
        ValueError,
    ):  # network / download failures are expected
        return None

    result = score >= 0.5
    _RESULT_CACHE[cache_key_int] = result
    _save_result_cache()
    return result
