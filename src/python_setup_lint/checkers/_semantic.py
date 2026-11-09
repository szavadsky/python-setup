from __future__ import annotations

import hashlib

from beartype import beartype

from python_setup_lint.checkers import _decision_backend
from python_setup_lint.checkers._decision_backend import DecisionBackend

__all__ = [
    "_reset_cache",
    "semantic_check_if_meaningful",
]

# Lazy-loaded on first call to semantic_check_if_meaningful.
_RESULT_CACHE: dict[int, bool] | None = None


def _reset_cache() -> None:
    """Reset the result cache (test helper).

    Clears the in-process memo.
    """
    global _RESULT_CACHE  # pylint: disable=global-statement  # memo reset requires global
    _RESULT_CACHE = None


@beartype
def semantic_check_if_meaningful(
    text: str,
    *,
    rule: str | None = None,
    code_context: str | None = None,
    comment: str | None = None,
    backend: DecisionBackend | None = None,
) -> bool | None:
    # Use comment as primary text, fall back to raw text.
    primary = (comment or text).strip()
    global _RESULT_CACHE  # pylint: disable=global-statement  # lazy-init memo requires global
    if _RESULT_CACHE is None:
        _RESULT_CACHE = {}
    if not primary:
        return False
    resolved = backend if backend is not None else _decision_backend.get_backend()
    if resolved is None:
        return None
    # Compute cache key from all inputs + model identifier.
    cache_key = hashlib.sha256(
        "|".join(
            str(x)
            for x in (
                primary,
                rule,
                code_context,
                resolved.model_id,
            )
        ).encode()
    ).digest()
    cache_key_int = int.from_bytes(cache_key[:8], "big")
    if cache_key_int in _RESULT_CACHE:
        return _RESULT_CACHE[cache_key_int]

    result = resolved.decide(primary, rule, code_context) >= _decision_backend.DECISION_THRESHOLD
    _RESULT_CACHE[cache_key_int] = result
    return result
