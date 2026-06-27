"""Semantic justification checker using sentence-transformers (Track B)."""



def semantic_check_if_meaningful(
    text: str,
    *,
    rule: str | None = None,
    code_context: str | None = None,
    comment: str | None = None,
) -> bool | None:
    """Check if a suppression justification is semantically meaningful.

    Two-stage NLP pipeline: embedding similarity + cross-encoder reranking.
    Returns ``None`` when the NLP pipeline is unavailable (fallback to heuristic).
    """
