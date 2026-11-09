"""Unit tests for ``python_setup_lint.checkers._semantic``.

The semantic pipeline is now a thin backend adapter: it resolves an optional
``DecisionBackend`` (or uses the injected one), maps its score through the
pinned ``0.5`` threshold, and memoizes one call per unique input/model pair.
No model package is imported and nothing is written to disk.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from python_setup_lint.checkers import _decision_backend, _semantic
from python_setup_lint.checkers._semantic import (  # type: ignore[attr-defined]  # private test helper omitted from .pyi
    _reset_cache,
    semantic_check_if_meaningful,
)


class _RecordingBackend:
    """Test double that records the pairs it is asked to score."""

    def __init__(self, score: float = 1.0, model_id: str = "recording-backend rev test prompt-v1") -> None:
        self.score = score
        self.model_id = model_id
        self.calls: list[tuple[str, str | None, str | None]] = []

    def decide(self, justification: str, rule: str | None, context: str | None) -> float:
        """Record the pair and return the configured score."""
        self.calls.append((justification, rule, context))
        return self.score


@pytest.fixture(autouse=True)
def _reset_semantic_state() -> Iterator[None]:
    """Clear the in-process memo between tests."""
    _reset_cache()
    yield
    _reset_cache()


def test_signature_exposes_backend_keyword_defaulting_to_none() -> None:
    parameter = inspect.signature(semantic_check_if_meaningful).parameters.get("backend")

    assert parameter is not None
    assert parameter.default is None
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


def test_empty_primary_returns_false_without_calling_backend() -> None:
    backend = _RecordingBackend()

    assert semantic_check_if_meaningful("", backend=backend) is False
    assert semantic_check_if_meaningful("   ", backend=backend) is False
    assert backend.calls == []


def test_loader_none_maps_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_decision_backend, "get_backend", lambda: None)

    assert semantic_check_if_meaningful("guarded by a lock", comment="guarded by a lock") is None


@pytest.mark.parametrize(("score", "expected"), [(0.0, False), (0.499, False), (0.5, True), (1.0, True)])
def test_backend_score_maps_at_pinned_threshold(score: float, expected: bool) -> None:
    backend = _RecordingBackend(score=score)

    result = semantic_check_if_meaningful(
        "guarded by a lock",
        rule="W9704",
        code_context="lock = Lock()",
        comment="guarded by a lock",
        backend=backend,
    )

    assert result is expected


def test_one_backend_call_per_unique_pair() -> None:
    backend = _RecordingBackend()
    kwargs: dict[str, Any] = {
        "rule": "W9704",
        "code_context": "lock = Lock()",
        "comment": "guarded by a lock",
    }

    first = semantic_check_if_meaningful("guarded by a lock", backend=backend, **kwargs)
    second = semantic_check_if_meaningful("guarded by a lock", backend=backend, **kwargs)

    assert first is True
    assert second is True
    assert backend.calls == [("guarded by a lock", "W9704", "lock = Lock()")]


def test_distinct_pairs_call_backend_again() -> None:
    backend = _RecordingBackend()

    semantic_check_if_meaningful("guarded by a lock", comment="guarded by a lock", backend=backend)
    semantic_check_if_meaningful("retry is idempotent", comment="retry is idempotent", backend=backend)

    assert len(backend.calls) == 2


def test_memo_key_includes_backend_model_id() -> None:
    first = _RecordingBackend(score=1.0, model_id="model-a rev test prompt-v1")
    second = _RecordingBackend(score=0.0, model_id="model-b rev test prompt-v1")

    assert semantic_check_if_meaningful("guarded by a lock", comment="guarded by a lock", backend=first) is True
    assert semantic_check_if_meaningful("guarded by a lock", comment="guarded by a lock", backend=second) is False
    assert len(first.calls) == 1
    assert len(second.calls) == 1


def test_module_does_not_reference_sentence_transformers() -> None:
    source = Path(_semantic.__file__).read_text()

    assert "sentence_transformers" not in source
    assert "sentence-transformers" not in source


def test_check_writes_no_disk_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_dir = tmp_path / "semantic"
    monkeypatch.setattr(_semantic, "_CACHE_DIR", cache_dir, raising=False)
    monkeypatch.setattr(_semantic, "_RESULT_CACHE_FILE", cache_dir / "results.json", raising=False)
    backend = _RecordingBackend()

    assert semantic_check_if_meaningful("guarded by a lock", comment="guarded by a lock", backend=backend) is True
    assert not cache_dir.exists()
