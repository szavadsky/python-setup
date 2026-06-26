"""Semantic justification checker using sentence-transformers (Track B).

Two-stage NLP pipeline for evaluating suppression justification quality:

1. **Embedding similarity** (``BAAI/bge-small-en-v1.5``):
   Encode the justification and the code context, compute cosine similarity.
   If similarity is below a threshold, the justification is likely
   semantically empty or unrelated.

2. **Cross-encoder reranking** (``jina-reranker-v2-base-multilingual``):
   Re-score the justification against the rule and code context with a
   dedicated cross-encoder for higher accuracy.

Both models are loaded lazily (inside function calls, never at module level).
On ``ImportError`` (sentence-transformers not installed) or model download
failure, ``semantic_check_if_meaningful`` returns ``None``, signalling the
caller to fall back to the heuristic check.
"""

from __future__ import annotations

from pathlib import Path

# Cache directory for downloaded models (idempotent, .gitignored).
_CACHE_DIR = Path.home() / ".cache" / "python-setup" / "semantic"

# Model identifiers.
_EMBEDDER_MODEL = "BAAI/bge-small-en-v1.5"
_RERANKER_MODEL = "jina-reranker-v2-base-multilingual"

# Similarity threshold below which a justification is considered not meaningful.
_EMBED_SIMILARITY_THRESHOLD = 0.35


def _get_cache_dir() -> Path:
    """Return the model cache directory, creating it if necessary."""
    cache = _CACHE_DIR
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _load_embedder():
    """Lazy-load the sentence-transformer embedder model.

    Returns:
        SentenceTransformer instance, or ``None`` on failure.
    """
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return None

    try:
        cache = _get_cache_dir()
        return SentenceTransformer(
            _EMBEDDER_MODEL,
            cache_folder=str(cache),
        )
    except Exception:  # noqa: BLE001  # network / download failures are expected
        return None


def _load_reranker():
    """Lazy-load the cross-encoder reranker model.

    Returns:
        CrossEncoder instance, or ``None`` on failure.
    """
    try:
        from sentence_transformers import CrossEncoder
    except ImportError:
        return None

    try:
        cache = _get_cache_dir()
        return CrossEncoder(
            _RERANKER_MODEL,
            cache_folder=str(cache),
        )
    except Exception:  # noqa: BLE001  # network / download failures are expected
        return None


def semantic_check_if_meaningful(
    text: str,
    *,
    rule: str | None = None,
    code_context: str | None = None,
    comment: str | None = None,
) -> bool | None:
    """Check if a suppression justification is semantically meaningful.

    Two-stage NLP pipeline:

    1. Embed the justification and code context, compare cosine similarity.
    2. If the embedding passes, re-score with a cross-encoder reranker.

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

    # --- Stage 1: Embedding similarity ---
    embedder = _load_embedder()
    if embedder is None:
        return None  # signal fallback to heuristic

    # Build a query string from the available context.
    query_parts = [primary]
    if rule:
        query_parts.append(f"rule: {rule}")
    if code_context:
        query_parts.append(f"context: {code_context[:200]}")  # truncate to avoid OOM

    query = " | ".join(query_parts)

    try:
        emb_text = embedder.encode(primary, normalize_embeddings=True)
        emb_query = embedder.encode(query, normalize_embeddings=True)
    except Exception:  # noqa: BLE001
        return None

    similarity = float(emb_text @ emb_query)
    if similarity < _EMBED_SIMILARITY_THRESHOLD:
        return False

    # --- Stage 2: Cross-encoder reranking ---
    reranker = _load_reranker()
    if reranker is None:
        # Embedding passed but reranker unavailable — accept provisionally.
        return True

    try:
        pairs = [(primary, query)]
        scores = reranker.predict(pairs)
        score = float(scores[0])
    except Exception:  # noqa: BLE001
        return True  # embedding passed, reranker failed — accept provisionally

    # Cross-encoder scores are typically 0-1; use a higher bar.
    return score >= 0.5
