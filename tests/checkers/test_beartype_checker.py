"""Unit tests for python_setup_lint.checkers.beartype_checker.

Uses synthetic code strings parsed via astroid, walked over
``BeartypeCoverageChecker``.  Fixture src / file-path rows live in
``tests/checkers/_factories.py`` (free LOC, not counted against the gate).
"""

from __future__ import annotations

from typing import Any

import astroid
import pytest
from pylint.testutils import CheckerTestCase

from python_setup_lint.checkers.conformance.beartype_checker import BeartypeCoverageChecker
from python_setup_lint.testing import _make_tc as _make_tc_factory
from tests.checkers._factories import (
    _BEARTYPE_MISS_CASES,
    _BEARTYPE_SKIP_CASES,
    _BEARTYPE_SOURCE_ROOT_CASES,
)


def _make_tc() -> CheckerTestCase:
    return _make_tc_factory(BeartypeCoverageChecker)


def _walk_and_release(code: str, *, file_path: str = "src/test_mod.py") -> list[Any]:
    tc = _make_tc()
    tc.checker.open()
    module = astroid.parse(code)
    module.file = file_path
    tc.walk(module)
    return tc.linter.release_messages()


@pytest.mark.parametrize(
    ("code", "expected_count", "expected_first_arg"), _BEARTYPE_MISS_CASES
)
def test_detects_missing_beartype(
    code: str,
    expected_count: int,
    expected_first_arg: str | None,
) -> None:
    """Checker emits ``missing-beartype`` for the listed public-function rows.

    ``expected_first_arg`` is asserted as ``msg.args[0]`` when non-None (used
    for class methods where args[0] is the method name); module-level rows
    pass ``None`` to skip the args[0] check.
    """
    msgs = _walk_and_release(code)
    missing = [m for m in msgs if m.msg_id == "missing-beartype"]
    assert len(missing) == expected_count, (
        f"src={code!r} → {len(missing)} missing-beartype (expected {expected_count})"
    )
    if expected_first_arg is not None and missing:
        assert missing[0].args[0] == expected_first_arg


@pytest.mark.parametrize(("code", "expected_missing_count"), _BEARTYPE_SKIP_CASES)
def test_skips(code: str, expected_missing_count: int) -> None:
    """Rows that should NOT trigger missing-beartype (or only the public one).

    ``expected_missing_count=0`` rows are pure-skip cases
    (private/init/str/solo). ``=1`` rows are mixed cases where only the one
    public function is flagged.
    """
    msgs = _walk_and_release(code)
    missing = [m for m in msgs if m.msg_id == "missing-beartype"]
    assert len(missing) == expected_missing_count


@pytest.mark.parametrize(
    ("decorator_expr",),
    [
        pytest.param(
            "from beartype import beartype\n@beartype\n", id="beartype_decorator"
        ),
        pytest.param(
            "from typing import no_type_check\n@no_type_check\n",
            id="no_type_check_decorator",
        ),
        pytest.param(
            "import typing\n@typing.no_type_check\n", id="typing_no_type_check"
        ),
    ],
)
def test_decorated_skipped(decorator_expr: str) -> None:
    """Decorated functions (beartype / no_type_check) are NOT flagged."""
    msgs = _walk_and_release(f"{decorator_expr}def foo(): pass\n")
    assert len([m for m in msgs if m.msg_id == "missing-beartype"]) == 0


def test_mixed_decorated_and_undecorated() -> None:
    """Only the undecorated public fn is flagged in a mixed module."""
    msgs = _walk_and_release(
        "from beartype import beartype\n@beartype\ndef foo(): pass\ndef bar(): pass\n"
    )
    missing = [m for m in msgs if m.msg_id == "missing-beartype"]
    assert len(missing) == 1
    assert missing[0].args[0] == "bar"


@pytest.mark.parametrize(
    ("code", "file_path", "expected_count"), _BEARTYPE_SOURCE_ROOT_CASES
)
def test_source_root_filtering(code: str, file_path: str, expected_count: int) -> None:
    """File under ``src/`` is checked; file under ``tests/`` is skipped."""
    msgs = _walk_and_release(code, file_path=file_path)
    missing = [m for m in msgs if m.msg_id == "missing-beartype"]
    assert len(missing) == expected_count
