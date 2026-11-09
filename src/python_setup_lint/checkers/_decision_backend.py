# Decision backend contract for semantic justification checks.
#
# Production lint resolves no model: get_backend() returns None and callers
# keep the heuristic verdict. Tests inject a backend directly or register one
# through PYTHON_SETUP_LINT_DECISION_BACKEND while PYTEST_CURRENT_TEST is set.

from __future__ import annotations

import importlib
import os
from typing import Protocol, runtime_checkable

import structlog
from beartype import beartype

__all__ = [
    "DECISION_THRESHOLD",
    "PROMPT_VERSION",
    "DecisionBackend",
    "FakeBackend",
    "get_backend",
]

_LOG = structlog.get_logger(__name__)

DECISION_THRESHOLD: float = 0.5
PROMPT_VERSION: str = "prompt-v1"

_BACKEND_ENV = "PYTHON_SETUP_LINT_DECISION_BACKEND"
_MODEL_ENV = "PYTHON_SETUP_LINT_DECISION_MODEL"
_RERANKER_ENV = "PYTHON_SETUP_LINT_RERANKER_MODEL"
_PYTEST_MARKER = "PYTEST_CURRENT_TEST"

_WARNED: set[str] = set()


@runtime_checkable
class DecisionBackend(Protocol):
    model_id: str

    @beartype
    def decide(self, justification: str, rule: str | None, context: str | None) -> float: ...


class FakeBackend:
    model_id: str = "fake-backend rev test prompt-v1"

    def __init__(self, score: float = 1.0) -> None:
        self.score = score

    @beartype
    def decide(self, justification: str, rule: str | None, context: str | None) -> float:  # noqa: ARG002  # deterministic fake ignores its inputs
        return self.score


def _warn_once(key: str, event: str, **fields: object) -> None:
    if key in _WARNED:
        return
    _WARNED.add(key)
    _LOG.warning(event, **fields)


def _load_registered_backend() -> DecisionBackend | None:
    if not os.environ.get(_PYTEST_MARKER):
        return None
    dotted_path = os.environ.get(_BACKEND_ENV)
    if not dotted_path:
        return None
    module_name, _, attribute = dotted_path.partition(":")
    try:
        factory = getattr(importlib.import_module(module_name), attribute)
        return factory()
    except AttributeError, ImportError, TypeError, ValueError:
        _LOG.warning("decision_backend_load_failed", dotted_path=dotted_path)
        return None


def _reset_backend_state() -> None:  # pylint: disable=trivial-wrapper  # test seam resets once-per-process warning state between cases
    _WARNED.clear()


@beartype
def get_backend() -> DecisionBackend | None:
    if os.environ.get(_RERANKER_ENV):
        _warn_once(
            "reranker-model",
            "PYTHON_SETUP_LINT_RERANKER_MODEL is deprecated; the bundled reranker was removed",
        )
    backend = _load_registered_backend()
    if backend is not None:
        return backend
    model_id = os.environ.get(_MODEL_ENV)
    if model_id is not None:
        _warn_once(
            "decision-model",
            "decision_model_unavailable",
            model=model_id,
            reason="no decision model backend is bundled in iteration 4",
        )
    return None
