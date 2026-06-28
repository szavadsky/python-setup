"""Unit tests for python_setup_lint.checkers.unnamed_tuple_dict_checker.

Verifies the AST checker detects bare tuple literals as dict values
when the dict is annotated ``dict[str, ...]``, and does NOT flag
named-tuple or dataclass dict values.
"""

from __future__ import annotations

from typing import Any

import pytest

from python_setup_lint.checkers.conformance.unnamed_tuple_dict_checker import (
    UnnamedTupleDictChecker,
)
from python_setup_lint.testing import _walk_and_release

# ── Failing cases: bare tuple literals as dict values ──

_DETECT_CASES: list[Any] = [
    pytest.param(
        "x: dict[str, tuple[str, str]] = {'a': ('hello', 'world')}",
        "unnamed-tuple-dict-value",
        2,
        id="two-str-tuple",
    ),
    pytest.param(
        "x: dict[str, tuple[str, str, str]] = {'a': ('x', 'y', 'z')}",
        "unnamed-tuple-dict-value",
        3,
        id="three-str-tuple",
    ),
    pytest.param(
        "x: dict[str, tuple[int, str]] = {'a': (1, 'two')}",
        "unnamed-tuple-dict-value",
        2,
        id="mixed-int-str-tuple",
    ),
    pytest.param(
        "x: dict[str, tuple[str, str]] = {'a': ('hello', 'world'), 'b': ('foo', 'bar')}",
        "unnamed-tuple-dict-value",
        2,
        id="multiple-entries",
    ),
]


@pytest.mark.parametrize(
    ("code", "expected_symbol", "expected_field_count"), _DETECT_CASES
)
def test_detects_unnamed_tuple_dict_values(
    code: str, expected_symbol: str, expected_field_count: int
) -> None:
    """Checker must flag bare tuple literals as dict values."""
    msgs = _walk_and_release(code, UnnamedTupleDictChecker)
    assert len(msgs) >= 1
    matching = [m for m in msgs if m.msg_id == expected_symbol]
    assert len(matching) >= 1
    for m in matching:
        assert m.args[0] == expected_field_count


# ── Passing cases: named tuples, dataclasses, or non-tuple values ──

_DO_NOT_DETECT_CASES: list[Any] = [
    pytest.param(
        "x: dict[str, str] = {'a': 'hello'}",
        id="str-value-not-tuple",
    ),
    pytest.param(
        "x: dict[str, int] = {'a': 42}",
        id="int-value-not-tuple",
    ),
    pytest.param(
        "x: dict[str, tuple[str, str]] = {}",
        id="empty-dict",
    ),
    pytest.param(
        "x: dict[str, tuple[str]] = {'a': ('single',)}",
        id="single-element-tuple",
    ),
    pytest.param(
        "x: dict[str, list[str]] = {'a': ['hello', 'world']}",
        id="list-value-not-tuple",
    ),
    pytest.param(
        "x: dict[int, tuple[str, str]] = {1: ('a', 'b')}",
        id="non-str-key-dict",
    ),
    pytest.param(
        "x: dict[str, tuple[str, str]] = {'a': ('hello',)}",
        id="single-element-tuple-in-dict",
    ),
]


@pytest.mark.parametrize("code", _DO_NOT_DETECT_CASES)
def test_does_not_detect(code: str) -> None:
    """Checker must NOT flag named-tuple, dataclass, or non-tuple values."""
    msgs = _walk_and_release(code, UnnamedTupleDictChecker)
    matching = [m for m in msgs if m.msg_id == "unnamed-tuple-dict-value"]
    assert len(matching) == 0, f"Expected no messages, got {len(matching)}"
