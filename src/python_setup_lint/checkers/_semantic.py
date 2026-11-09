# Semantic justification adapter over an optional decision backend.
#
# Production lint resolves no backend: the loader returns None and the caller
# keeps the heuristic verdict. When a backend is available, one call is made
# per unique (justification, rule, model) triple and the score is mapped
# through the pinned threshold. Verdicts are memoized in-process only;
# nothing is written to disk.

from __future__ import annotations

from beartype import beartype

from python_setup_lint.checkers import _decision_backend
from python_setup_lint.checkers._decision_backend import DecisionBackend

__all__ = [
    "_reset_cache",
    "semantic_check_if_meaningful",
]

_MEMO: dict[tuple[str, str | None, str], bool] = {}


def _reset_cache() -> None:  # pylint: disable=trivial-wrapper  # test seam resets the process-wide memo between cases
    _MEMO.clear()


@beartype
def semantic_check_if_meaningful(
    text: str,
    *,
    rule: str | None = None,
    code_context: str | None = None,
    comment: str | None = None,
    backend: DecisionBackend | None = None,
) -> bool | None:
    primary = (comment or text).strip()
    if not primary:
        return False
    resolved = backend if backend is not None else _decision_backend.get_backend()
    if resolved is None:
        return None
    memo_key = (primary, rule, resolved.model_id)
    if memo_key in _MEMO:
        return _MEMO[memo_key]
    verdict = resolved.decide(primary, rule, code_context) >= _decision_backend.DECISION_THRESHOLD
    _MEMO[memo_key] = verdict
    return verdict
