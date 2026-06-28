"""Unit tests for python_setup_lint.checkers.no_try_import_checker.

Verifies the AST checker detects (and does not detect) the correct
try/except+import patterns. All fixture src strings live in
``tests/checkers/_factories.py`` (free LOC, not counted against the gate).
"""

from __future__ import annotations

from typing import Any

import pytest

from python_setup_lint.checkers.conformance.no_try_import_checker import (
    NoTryImportChecker,
)
from python_setup_lint.testing import _walk_and_release
from tests.checkers._factories import (
    _NO_TRY_DETECT_CASES,
    _NO_TRY_DO_NOT_DETECT_CASES,
)


@pytest.mark.parametrize(
    ("code", "expected_count", "expected_args"),
    _NO_TRY_DETECT_CASES,
)
def test_detects_no_try_import(
    code: str,
    expected_count: int,
    expected_args: tuple[Any, ...],
) -> None:
    """Checker must flag all flagged-pattern rows with the expected message count.

    For the two rows with non-empty ``expected_args`` the body asserts the
    first message's ``args`` tuple matches (verifying the labelled reason).
    """
    msgs = _walk_and_release(code, NoTryImportChecker)
    assert len(msgs) == expected_count, (
        f"src={code!r} → {len(msgs)} messages (expected {expected_count})"
    )
    if expected_args:
        assert msgs[0].msg_id == "no-try-import"
        assert msgs[0].args == expected_args, (
            f"args={msgs[0].args!r} (expected {expected_args!r})"
        )


@pytest.mark.parametrize("code", _NO_TRY_DO_NOT_DETECT_CASES)
def test_does_not_detect_no_try_import(code: str) -> None:
    """Checker must NOT flag the listed valid-code rows."""
    msgs = _walk_and_release(code, NoTryImportChecker)
    assert len(msgs) == 0, f"src={code!r} flagged {len(msgs)} messages (expected none)"
