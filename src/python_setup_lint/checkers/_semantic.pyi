"""Semantic justification adapter over an optional decision backend.

Production lint resolves no backend, so the caller keeps the heuristic verdict.
An injected or registered backend scores the justification and the result maps
through the pinned threshold. Verdicts are memoized in-process only.
"""

from python_setup_lint.checkers._decision_backend import DecisionBackend

def semantic_check_if_meaningful(
    text: str,
    *,
    rule: str | None = None,
    code_context: str | None = None,
    comment: str | None = None,
    backend: DecisionBackend | None = None,
) -> bool | None:
    """Check if a suppression justification is semantically meaningful.

    Args:
        text: The raw justification text (used as fallback when *comment*
            is not provided).
        rule: The lint rule identifier being suppressed (e.g. ``"E501"``).
        code_context: Surrounding source code lines.
        comment: The justification comment text (preferred over *text*).
        backend: A decision backend; when ``None``, the registered backend is
            resolved and a missing backend falls through to the heuristic.

    Returns:
        ``True`` if the backend confirms the justification, ``False`` if it
        vetoes it, or ``None`` when no backend is available.
    """
