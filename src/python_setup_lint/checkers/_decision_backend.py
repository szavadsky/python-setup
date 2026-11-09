# Decision backend contract for semantic justification checks.
#
# Iteration 4 ships infrastructure only: production lint resolves no model, so
# get_backend() returns None and callers fall back to the heuristic. Tests
# inject a backend directly or register one through
# PYTHON_SETUP_LINT_DECISION_BACKEND while PYTEST_CURRENT_TEST is set.

from __future__ import annotations

from typing import Protocol, runtime_checkable

from beartype import beartype

__all__ = [
    "DECISION_THRESHOLD",
    "PROMPT_VERSION",
    "DecisionBackend",
    "FakeBackend",
    "get_backend",
]

DECISION_THRESHOLD: float = 0.5
PROMPT_VERSION: str = "prompt-v1"


@runtime_checkable
class DecisionBackend(Protocol):
    model_id: str

    @beartype
    def decide(self, justification: str, rule: str | None, context: str | None) -> float: ...


class FakeBackend:
    model_id: str = "fake-backend rev test prompt-v1"

    def __init__(self, score: float = 1.0) -> None:
        raise NotImplementedError("_decision_backend.FakeBackend is an interface stub")

    @beartype
    def decide(self, justification: str, rule: str | None, context: str | None) -> float:
        raise NotImplementedError("_decision_backend.FakeBackend.decide is an interface stub")


@beartype
def get_backend() -> DecisionBackend | None:
    raise NotImplementedError("_decision_backend.get_backend is an interface stub")


def _reset_backend_state() -> None:
    pass
