"""Decision backend contract for semantic justification checks.

Production lint resolves no model: :func:`get_backend` returns ``None`` and the
caller falls back to the heuristic. Tests inject a backend directly or register
one through ``PYTHON_SETUP_LINT_DECISION_BACKEND`` while ``PYTEST_CURRENT_TEST``
is set.
"""

from typing import Protocol, runtime_checkable

DECISION_THRESHOLD: float
PROMPT_VERSION: str

@runtime_checkable
class DecisionBackend(Protocol):
    """Score a suppression justification against its rule and code context."""

    model_id: str

    def decide(self, justification: str, rule: str | None, context: str | None) -> float:
        """Return a meaningfulness score in ``[0.0, 1.0]``."""

class FakeBackend:
    """Deterministic backend for tests; returns *score* for every call."""

    model_id: str

    def __init__(self, score: float = 1.0) -> None: ...
    def decide(self, justification: str, rule: str | None, context: str | None) -> float:
        """Return the configured score."""

def get_backend() -> DecisionBackend | None:
    """Resolve the configured backend, or ``None`` when no model is available."""
