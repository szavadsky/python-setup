"""Unit tests for python_setup_lint.checkers.stub_docstring_checker.

Tests docstring detection logic and full pipeline with stub_checker.
Fixture src rows live in ``tests/checkers/_factories.py`` (free LOC).
"""

from __future__ import annotations

from pathlib import Path

import astroid
import pytest

from python_setup_lint.checkers.stub_docstring_checker import StubDocstringChecker
from python_setup_lint.testing import _make_tc as _make_tc_factory

from tests.checkers._factories import (
    _DOCSTRING_DETECT_CASES,
    _DOCSTRING_DOES_NOT_DETECT_CASES,
    _DOCSTRING_NO_COMPANION_CASES,
    walk_both_release_for_pyi,
)


_make_tc = lambda: _make_tc_factory(StubDocstringChecker)


def _walk_and_release(code: str, file_path: str = "/workspace/src/mod.py") -> list:
    """Walk only ``StubDocstringChecker`` (no .pyi companion required)."""
    tc = _make_tc()
    module = astroid.parse(code)
    module.file = file_path
    tc.walk(module)
    return tc.linter.release_messages()


def _doc_msg_count(msgs: list) -> int:
    return sum(1 for m in msgs if m.msg_id == "docstring-in-impl")


# ── No companion .pyi → no docstring-in-impl messages ──────────────


@pytest.mark.parametrize("code, expected_count", _DOCSTRING_NO_COMPANION_CASES)
def test_no_companion_stub_no_message(code: str, expected_count: int) -> None:
    """When no companion .pyi exists, ``docstring-in-impl`` MUST NOT fire."""
    msgs = _walk_and_release(code)
    assert _doc_msg_count(msgs) == expected_count


# ── Does NOT detect — negative cases ────────────────────────────────


@pytest.mark.parametrize("code", _DOCSTRING_DOES_NOT_DETECT_CASES)
def test_does_not_detect(code: str) -> None:
    """W9700 must NOT fire for the listed valid cases."""
    msgs = _walk_and_release(code)
    assert _doc_msg_count(msgs) == 0


# ── Detects: companion .pyi exists → W9700 fires ────────────────────


@pytest.mark.parametrize("code, expected_count, expected_args1", _DOCSTRING_DETECT_CASES)
def test_detects_docstring_in_impl(
    tmp_path: Path,
    code: str,
    expected_count: int,
    expected_args1: str | None,
) -> None:
    """Companion .pyi present + .py has docstrings → ``docstring-in-impl`` fires.

    For rows where ``expected_args1`` is set the body asserts ``args[1]``
    (the function name carried in W9700) matches.
    """
    py_path = tmp_path / "src" / "mod.py"
    py_path.parent.mkdir(exist_ok=True)
    msgs = walk_both_release_for_pyi(
        code, py_path=py_path, source_roots=[str(tmp_path / "src")],
    )
    doc_msgs = [m for m in msgs if m.msg_id == "docstring-in-impl"]
    assert len(doc_msgs) == expected_count
    if expected_args1 is not None:
        assert doc_msgs[0].args[1] == expected_args1