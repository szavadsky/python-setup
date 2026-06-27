"""Unit tests for python_setup_lint.checkers.missing_return_annotation_checker.

Uses synthetic code strings parsed via astroid, walked over
``MissingReturnAnnotationChecker``.
"""

from __future__ import annotations

from typing import Any

import astroid
import pytest
from pylint.testutils import CheckerTestCase

from python_setup_lint.checkers.conformance.missing_return_annotation_checker import (
    MissingReturnAnnotationChecker,
)
from python_setup_lint.testing import _make_tc as _make_tc_factory


def _make_tc() -> CheckerTestCase:
    return _make_tc_factory(MissingReturnAnnotationChecker)


def _walk_and_release(code: str, *, file_path: str = "src/test_mod.py") -> list[Any]:
    tc = _make_tc()
    module = astroid.parse(code)
    module.name = "test_mod"
    module.file = file_path
    tc.checker.open()
    tc.walk(module)
    return tc.linter.release_messages()


# ── Detect cases ──

_DETECT_CASES: list[tuple[str, str]] = [
    pytest.param(
        "def _helper():\n    return 42\n",
        "_helper",
        id="simple_private_no_annotation",
    ),
    pytest.param(
        "def _process(data):\n    return data.strip()\n",
        "_process",
        id="private_with_param_no_annotation",
    ),
    pytest.param(
        "async def _fetch():\n    return await get_data()\n",
        "_fetch",
        id="async_private_no_annotation",
    ),
    pytest.param(
        "def _compute(x, y):\n    return x + y\n",
        "_compute",
        id="private_multi_param_no_annotation",
    ),
]


@pytest.mark.parametrize(("code", "expected_name"), _DETECT_CASES)
def test_detects_missing_return_annotation(code: str, expected_name: str) -> None:
    """Checker emits ``missing-return-annotation`` for _-prefixed fns without return annotation."""
    msgs = _walk_and_release(code)
    missing = [m for m in msgs if m.msg_id == "missing-return-annotation"]
    assert len(missing) == 1, f"Expected 1 message, got {len(missing)}"
    assert missing[0].args[0] == expected_name


# ── Non-detect cases ──

_NON_DETECT_CASES: list[tuple[str, int]] = [
    pytest.param(
        "def _helper() -> int:\n    return 42\n",
        0,
        id="private_with_annotation",
    ),
    pytest.param(
        "def public_func():\n    return 42\n",
        0,
        id="public_function_skipped",
    ),
    pytest.param(
        "def __init__(self):\n    pass\n",
        0,
        id="dunder_init_skipped",
    ),
    pytest.param(
        "def __post_init__(self):\n    pass\n",
        0,
        id="dunder_post_init_skipped",
    ),
    pytest.param(
        "def __str__(self) -> str:\n    return 'x'\n",
        0,
        id="dunder_with_annotation_skipped",
    ),
    pytest.param(
        "def _helper() -> str | None:\n    return None\n",
        0,
        id="private_with_union_annotation",
    ),
    pytest.param(
        "async def _fetch() -> dict:\n    return {}\n",
        0,
        id="async_private_with_annotation",
    ),
]


@pytest.mark.parametrize(("code", "expected_count"), _NON_DETECT_CASES)
def test_skips(code: str, expected_count: int) -> None:
    """Rows that should NOT trigger missing-return-annotation."""
    msgs = _walk_and_release(code)
    missing = [m for m in msgs if m.msg_id == "missing-return-annotation"]
    assert len(missing) == expected_count


# ── Source root filtering ──

_SOURCE_ROOT_CASES: list[tuple[str, str, int]] = [
    pytest.param(
        "def _helper():\n    return 42\n",
        "src/my_mod.py",
        1,
        id="under_src_detected",
    ),
    pytest.param(
        "def _helper():\n    return 42\n",
        "tests/test_my_mod.py",
        0,
        id="under_tests_skipped",
    ),
    pytest.param(
        "def _helper():\n    return 42\n",
        "docs/conf.py",
        0,
        id="under_docs_skipped",
    ),
]


@pytest.mark.parametrize(("code", "file_path", "expected_count"), _SOURCE_ROOT_CASES)
def test_source_root_filtering(code: str, file_path: str, expected_count: int) -> None:
    """File under ``src/`` is checked; file under ``tests/`` or ``docs/`` is skipped."""
    msgs = _walk_and_release(code, file_path=file_path)
    missing = [m for m in msgs if m.msg_id == "missing-return-annotation"]
    assert len(missing) == expected_count


# ── Mixed: one flagged, one not ──


def test_mixed_annotated_and_unannotated() -> None:
    """Only the unannotated _-prefixed fn is flagged."""
    code = """
def _annotated() -> int:
    return 1

def _bare():
    return 2

def public_func():
    return 3
"""
    msgs = _walk_and_release(code)
    missing = [m for m in msgs if m.msg_id == "missing-return-annotation"]
    assert len(missing) == 1
    assert missing[0].args[0] == "_bare"
