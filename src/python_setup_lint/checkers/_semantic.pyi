"""Semantic justification checker using sentence-transformers (Track B)."""

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


def _reset_cache() -> None:
    """Reset the in-memory result cache and remove the persisted cache file."""