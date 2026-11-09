from __future__ import annotations

import importlib
import os
from typing import Protocol, runtime_checkable

import structlog
from beartype import beartype

DECISION_THRESHOLD: float = 0.5
PROMPT_VERSION: str = "prompt-v1"
_LOG = structlog.get_logger(__name__)
_WARNED: set[str] = set()


@runtime_checkable
class DecisionBackend(Protocol):
    model_id: str

    def decide(self, justification: str, rule: str | None, context: str | None) -> float: ...  # pylint: disable=missing-beartype  # protocol method: never runtime-checked


class FakeBackend:
    model_id: str = "fake-backend rev test prompt-v1"

    def __init__(self, score: float = 1.0) -> None:
        self.score = score

    def decide(self, justification: str, rule: str | None, context: str | None) -> float:  # pylint: disable=missing-beartype  # noqa: ARG002  # fake ignores its inputs
        return self.score


def _reset_backend_state() -> None:  # pylint: disable=trivial-wrapper  # test seam resets warn-once state
    _WARNED.clear()


def _load_registered_backend() -> DecisionBackend | None:
    dotted = os.environ.get("PYTHON_SETUP_LINT_DECISION_BACKEND")
    if not os.environ.get("PYTEST_CURRENT_TEST") or not dotted:
        return None
    try:
        module_name, _, attribute = dotted.partition(":")
        return getattr(importlib.import_module(module_name), attribute)()
    except AttributeError, ImportError, TypeError, ValueError:
        _LOG.warning("decision_backend_load_failed", dotted_path=dotted)
        return None


@beartype
def get_backend() -> DecisionBackend | None:
    if os.environ.get("PYTHON_SETUP_LINT_RERANKER_MODEL") and "reranker" not in _WARNED:
        _WARNED.add("reranker")
        _LOG.warning("PYTHON_SETUP_LINT_RERANKER_MODEL is deprecated")
    backend = _load_registered_backend()
    model_id = os.environ.get("PYTHON_SETUP_LINT_DECISION_MODEL")
    if backend is None and model_id is not None and "model" not in _WARNED:
        _WARNED.add("model")
        _LOG.warning("decision_model_unavailable", model=model_id)
    return backend
