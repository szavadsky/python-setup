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

import contextlib
import hashlib
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from beartype import beartype

_LOG = structlog.get_logger(__name__)
if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder  # type: ignore[import-not-found]  # optional semantic extra

# Cache directory for downloaded models (idempotent, .gitignored).
_CACHE_DIR: Path | None = None

# Model singleton cache (loaded once, reused across calls).
_RERANKER_INSTANCE: CrossEncoder | None = None
_RERANKER_UNAVAILABLE: bool = False

# Persisted result cache file.
# Lazy-loaded on first call to semantic_check_if_meaningful.
_RESULT_CACHE: dict[int, bool] | None = None

_RERANKER_MODEL = os.environ.get(
    "PYTHON_SETUP_LINT_RERANKER_MODEL",
    "jina-reranker-v2-base-multilingual",
)


def _cache_dir() -> Path:
    """Lazily resolve cache dir on first use (respects test monkeypatch of Path.home).

    Returns:
        The path to the semantic cache directory.
    """
    global _CACHE_DIR  # pylint: disable=global-statement  # lazy init requires global
    if _CACHE_DIR is None:
        _CACHE_DIR = Path.home() / ".cache" / "python-setup" / "semantic"
    return _CACHE_DIR


def _result_cache_file() -> Path:
    return _cache_dir() / "results.json"



def _load_result_cache() -> dict[int, bool]:
    """Load the persisted result cache from disk.

    Returns:
        The loaded cache dict, or an empty dict if the cache file is missing or corrupt.
    """
    try:
        raw = _result_cache_file().read_text()
        return {int(k): v for k, v in json.loads(raw).items()}
    except FileNotFoundError:  # pylint: disable=W9740  # expected on first run, cache file doesn't exist yet
        return {}
    except (json.JSONDecodeError, OSError, ValueError):
        _LOG.warning("Failed to load result cache", exc_info=True)
        return {}


def _save_result_cache() -> None:
    """Persist the result cache to disk."""
    try:
        _cache_dir().mkdir(parents=True, exist_ok=True)
        assert _RESULT_CACHE is not None  # only called after lazy init
        _result_cache_file().write_text(
            json.dumps({str(k): v for k, v in _RESULT_CACHE.items()})
        )
    except OSError:
        _LOG.warning("Failed to save result cache", exc_info=True)


def _reset_cache() -> None:
    """Reset the result cache (test helper).

    Clears the in-memory cache and removes the persisted cache file.
    """
    global _RESULT_CACHE, _RERANKER_UNAVAILABLE  # pylint: disable=global-statement  # module-level cache reset requires global
    _RESULT_CACHE = None
    _RERANKER_UNAVAILABLE = False
    with contextlib.suppress(OSError):
        _result_cache_file().unlink(missing_ok=True)


def _get_cache_dir() -> Path:
    """Return the model cache directory, creating it if necessary.

    Returns:
        The cache directory path (created if it did not exist).
    """
    cache = _cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _load_reranker() -> CrossEncoder | None:
    """Lazy-load the cross-encoder reranker model.

    Returns:
        CrossEncoder instance, or ``None`` on failure.
    """
    global _RERANKER_INSTANCE, _RERANKER_UNAVAILABLE  # pylint: disable=global-statement  # lazy-load singleton requires global
    if _RERANKER_UNAVAILABLE:
        return None
    if _RERANKER_INSTANCE is not None:
        return _RERANKER_INSTANCE
    try:
        from sentence_transformers import CrossEncoder  # type: ignore[import-not-found]  # optional semantic extra
    except ImportError:
        _RERANKER_UNAVAILABLE = True
        _LOG.debug("sentence_transformers not available, reranker disabled")
        return None

    try:
        cache = _get_cache_dir()
        _RERANKER_INSTANCE = CrossEncoder(
            _RERANKER_MODEL,
            cache_folder=str(cache),
        )
        return _RERANKER_INSTANCE
    except OSError, RuntimeError, ValueError:
        _RERANKER_UNAVAILABLE = True
        _LOG.warning("Failed to load reranker model", exc_info=True)
        return None


@beartype
def semantic_check_if_meaningful(
    text: str,
    *,
    rule: str | None = None,
    code_context: str | None = None,
    comment: str | None = None,
) -> bool | None:
    # Use comment as primary text, fall back to raw text.
    primary = (comment or text).strip()
    # Lazy-init the result cache on first call.
    global _RESULT_CACHE  # pylint: disable=global-statement  # lazy-init result cache requires global
    if _RESULT_CACHE is None:
        _RESULT_CACHE = _load_result_cache()
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
    except (OSError, RuntimeError, ValueError):
        _LOG.warning("Reranker prediction failed", exc_info=True)
        return None

    result = score >= 0.5
    _RESULT_CACHE[cache_key_int] = result
    _save_result_cache()
    return result
