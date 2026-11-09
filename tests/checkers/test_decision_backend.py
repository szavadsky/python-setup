"""Behavioral tests for the veto ``DecisionBackend`` pipeline.

These tests pin ADR-010 (runtime pinning, hermetic production default) and
ADR-014 (heuristic-first veto, backend injection, ``None`` fallback, pinned
threshold/prompt, in-process deduplication).  No model is downloaded or
imported: every backend used here is a test double.
"""

from __future__ import annotations

import inspect
import tomllib
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import cast

import pytest
from structlog.testing import capture_logs

from python_setup_lint.checkers import _base, _decision_backend, _semantic
from python_setup_lint.checkers._base import check_if_meaningful
from python_setup_lint.checkers._decision_backend import (  # type: ignore[attr-defined]  # private test helper omitted from .pyi
    DECISION_THRESHOLD,
    PROMPT_VERSION,
    DecisionBackend,
    FakeBackend,
    _reset_backend_state,
    get_backend,
)
from python_setup_lint.checkers._semantic import (  # type: ignore[attr-defined]  # private test helper omitted from .pyi
    _reset_cache,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_ENV = "PYTHON_SETUP_LINT_DECISION_BACKEND"
_MODEL_ENV = "PYTHON_SETUP_LINT_DECISION_MODEL"
_RERANKER_ENV = "PYTHON_SETUP_LINT_RERANKER_MODEL"
_SEMANTIC_ENV = "PYTHON_SETUP_LINT_SEMANTIC"
_PYTEST_MARKER = "PYTEST_CURRENT_TEST"
_MEANINGFUL = "circular import — PyLinter not available at runtime"
_BRUSH_OFF = "pre-existing"


class _RecordingBackend:
    """Test double that records every ``decide`` call."""

    def __init__(self, score: float = 1.0, model_id: str = "recording-backend rev test prompt-v1") -> None:
        self.score = score
        self.model_id = model_id
        self.calls: list[tuple[str, str | None, str | None]] = []

    def decide(self, justification: str, rule: str | None, context: str | None) -> float:
        """Record the pair and return the configured score."""
        self.calls.append((justification, rule, context))
        return self.score


def _make_loader_backend() -> _RecordingBackend:
    """Module-level factory resolved through the dotted-path override."""
    return _RecordingBackend(score=1.0, model_id="dotted-loader rev test prompt-v1")


def _make_rejecting_loader_backend() -> _RecordingBackend:
    """Module-level factory that vetoes a heuristic-meaningful justification."""
    return _RecordingBackend(score=0.0, model_id="dotted-rejector rev test prompt-v1")


@pytest.fixture(autouse=True)
def _isolate_backend_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Reset loader/warning state and environment around every test."""
    _reset_backend_state()
    _reset_cache()
    for variable in (_BACKEND_ENV, _MODEL_ENV, _RERANKER_ENV):
        monkeypatch.delenv(variable, raising=False)
    yield
    _reset_backend_state()
    _reset_cache()


# ── Pinned constants ────────────────────────────────────────────────


def test_decision_threshold_is_pinned_at_half() -> None:
    assert DECISION_THRESHOLD == 0.5


def test_prompt_version_is_pinned() -> None:
    assert PROMPT_VERSION == "prompt-v1"


# ── FakeBackend ─────────────────────────────────────────────────────


def test_fake_backend_defaults_to_one_and_pinned_model_id() -> None:
    backend = FakeBackend()
    assert backend.model_id == "fake-backend rev test prompt-v1"
    assert backend.decide("guarded by a lock", "W9704", "lock = Lock()") == 1.0


def test_fake_backend_returns_configured_score() -> None:
    assert FakeBackend(score=0.25).decide("guarded by a lock", None, None) == 0.25


def test_fake_backend_satisfies_protocol() -> None:
    backend = FakeBackend()
    assert isinstance(backend, DecisionBackend)
    assert backend.model_id == "fake-backend rev test prompt-v1"


# ── Loader ──────────────────────────────────────────────────────────


def test_get_backend_is_none_without_configuration() -> None:
    assert get_backend() is None


def test_get_backend_honors_dotted_path_under_pytest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        _PYTEST_MARKER,
        "tests/checkers/test_decision_backend.py::test_get_backend (call)",
    )
    monkeypatch.setenv(_BACKEND_ENV, f"{__name__}:_make_loader_backend")

    backend = get_backend()

    assert backend is not None
    assert backend.model_id == "dotted-loader rev test prompt-v1"


def test_get_backend_ignores_dotted_path_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(_PYTEST_MARKER, raising=False)
    monkeypatch.setenv(_BACKEND_ENV, "does.not.exist:backend")

    assert get_backend() is None


def test_decision_model_parses_but_yields_none_with_exactly_one_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_MODEL_ENV, "glide-0.4b")

    with capture_logs() as logs:
        assert get_backend() is None
        assert get_backend() is None

    warnings = [entry for entry in logs if entry.get("log_level") == "warning"]
    assert len(warnings) == 1


def test_reranker_model_env_is_deprecated_with_exactly_one_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_RERANKER_ENV, "jina-reranker-v2-base-multilingual")

    with capture_logs() as logs:
        get_backend()
        get_backend()

    warnings = [entry for entry in logs if entry.get("log_level") == "warning"]
    assert len(warnings) == 1
    assert "deprecated" in str(warnings[0]["event"]).lower()


# ── Function contracts ──────────────────────────────────────────────


def test_check_if_meaningful_has_backend_keyword_defaulting_to_none() -> None:
    parameter = inspect.signature(check_if_meaningful).parameters.get("backend")
    assert parameter is not None
    assert parameter.default is None
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


# ── Heuristic-first veto in ``check_if_meaningful`` ─────────────────


def test_registered_backend_rejects_a_meaningful_heuristic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_BACKEND_ENV, f"{__name__}:_make_rejecting_loader_backend")

    assert check_if_meaningful(_MEANINGFUL, rule="missing-beartype") is False


def test_brush_off_is_vetoed_before_the_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_SEMANTIC_ENV, "1")
    backend = _RecordingBackend(score=1.0)

    result = check_if_meaningful(
        _BRUSH_OFF,
        rule="unjustified-suppression",
        code_context="x = 1",
        comment=_BRUSH_OFF,
        backend=backend,
    )

    assert result is False
    assert backend.calls == []


def test_brush_off_does_not_reach_the_semantic_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_SEMANTIC_ENV, "1")

    def _unexpected_semantic_check(*args: object, **kwargs: object) -> None:
        raise AssertionError("brush-off must be vetoed before semantic evaluation")

    monkeypatch.setattr(_semantic, "semantic_check_if_meaningful", _unexpected_semantic_check)

    assert check_if_meaningful(_BRUSH_OFF, comment=_BRUSH_OFF) is False


def test_meaningful_heuristic_is_confirmed_by_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_SEMANTIC_ENV, "1")
    backend = _RecordingBackend(score=1.0)

    result = check_if_meaningful(_MEANINGFUL, rule="missing-beartype", backend=backend)

    assert result is True
    assert len(backend.calls) == 1


def test_backend_below_threshold_rejects_a_meaningful_heuristic() -> None:
    backend = _RecordingBackend(score=0.0)

    assert check_if_meaningful(_MEANINGFUL, backend=backend) is False


def test_loader_none_falls_back_to_the_heuristic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_decision_backend, "get_backend", lambda: None)

    assert check_if_meaningful(_MEANINGFUL) is True


def test_semantic_disabled_never_calls_the_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_SEMANTIC_ENV, "0")
    backend = _RecordingBackend(score=1.0)

    assert check_if_meaningful(_MEANINGFUL, backend=backend) is True
    assert backend.calls == []


# ── Suppressed-code normalization ──────────────────────────────────


def _normalize(comment: str) -> str:
    helper = getattr(_base, "normalize_suppressed_codes", None)
    assert callable(helper), "_base.normalize_suppressed_codes must be implemented"
    return cast("Callable[[str], str]", helper)(comment)  # pylint: disable=not-callable  # typing.cast result is callable; pylint cannot infer it


@pytest.mark.parametrize(
    "comment",
    [
        "type: ignore[assignment]  # assignment",
        "type: ignore[assignment,arg-type]  # arg-type, assignment",
        "noqa: E501, W9704  # W9704,E501",
    ],
)
def test_normalize_suppressed_codes_drops_reason_that_echoes_codes(
    comment: str,
) -> None:
    assert _normalize(comment) == ""


@pytest.mark.parametrize(
    "comment",
    [
        "type: ignore[assignment]  # carried from library httpx for type compatibility",
        "carried from library httpx for type compatibility",
    ],
)
def test_normalize_suppressed_codes_keeps_a_real_reason(comment: str) -> None:
    assert _normalize(comment) == "carried from library httpx for type compatibility"


@pytest.mark.parametrize(("comment", "expected"), [("W9704,E501", "W9704,E501"), ("assignment", "assignment")])
def test_normalize_suppressed_codes_leaves_bare_text_unchanged(comment: str, expected: str) -> None:
    assert _normalize(comment) == expected


def test_check_if_meaningful_rejects_code_echo_justification() -> None:
    comment = "type: ignore[assignment]  # assignment"

    assert (
        check_if_meaningful(
            comment,
            comment=comment,
            rule="unjustified-suppression",
            code_context="x: Any = 1",
        )
        is False
    )


# ── Packaging pins ──────────────────────────────────────────────────


def test_semantic_extra_is_empty() -> None:
    pyproject = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text())

    assert pyproject["project"]["optional-dependencies"]["semantic"] == []


def test_uv_lock_has_no_sentence_transformers_edge() -> None:
    lock = tomllib.loads((_REPO_ROOT / "uv.lock").read_text())
    packages = {package["name"]: package for package in lock["package"]}
    root = packages["python-setup"]

    assert "sentence-transformers" not in packages
    assert root.get("optional-dependencies", {}).get("semantic", []) == []
    requires_dist = root.get("metadata", {}).get("requires-dist", [])
    assert all(dependency["name"] != "sentence-transformers" for dependency in requires_dist)
