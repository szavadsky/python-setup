"""Unit tests for python_setup_lint.checkers.conformance.pyi_underscore_checker.

Verifies the AST checker flags _-prefixed symbols in .pyi files but
not in .py files, and respects TYPE_CHECKING guards.
"""

from __future__ import annotations

from python_setup_lint.checkers.conformance.pyi_underscore_checker import (
    PyiUnderscoreChecker,
)
from python_setup_lint.testing import _walk_and_release

# ── Failing cases: _-prefixed symbols in .pyi files ──


def test_detects_private_function_in_pyi() -> None:
    """Checker must flag _-prefixed functions in .pyi files."""
    code = """
def _private_func() -> None: ...
"""
    msgs = _walk_and_release(code, PyiUnderscoreChecker, file_path="test.pyi")
    assert len(msgs) == 1
    assert msgs[0].msg_id == "W9707"


def test_detects_private_class_in_pyi() -> None:
    """Checker must flag _-prefixed classes in .pyi files."""
    code = """
class _PrivateClass: ...
"""
    msgs = _walk_and_release(code, PyiUnderscoreChecker, file_path="test.pyi")
    assert len(msgs) == 1
    assert msgs[0].msg_id == "W9707"


def test_detects_private_attr_in_pyi() -> None:
    """Checker must flag _-prefixed annotated attributes in .pyi files."""
    code = """
_private_attr: int
"""
    msgs = _walk_and_release(code, PyiUnderscoreChecker, file_path="test.pyi")
    assert len(msgs) == 1
    assert msgs[0].msg_id == "W9707"


def test_detects_private_assign_in_pyi() -> None:
    """Checker must flag _-prefixed assignments in .pyi files."""
    code = """
_private_const: int = 42
"""
    msgs = _walk_and_release(code, PyiUnderscoreChecker, file_path="test.pyi")
    assert len(msgs) == 1
    assert msgs[0].msg_id == "W9707"


def test_detects_multiple_private_symbols() -> None:
    """Checker must flag multiple _-prefixed symbols in one .pyi file."""
    code = """
_private_func: int
_another_func: str

class _PrivateClass: ...
"""
    msgs = _walk_and_release(code, PyiUnderscoreChecker, file_path="test.pyi")
    assert len(msgs) == 3
    for m in msgs:
        assert m.msg_id == "W9707"


# ── Passing cases: public symbols, .py files, TYPE_CHECKING guards ──


def test_public_symbols_in_pyi() -> None:
    """Checker must NOT flag public symbols in .pyi files."""
    code = """
def public_func() -> None: ...

class PublicClass: ...

public_attr: int
"""
    msgs = _walk_and_release(code, PyiUnderscoreChecker, file_path="test.pyi")
    assert len(msgs) == 0, f"Expected no messages, got {len(msgs)}"


def test_no_flag_in_py_files() -> None:
    """Checker must NOT flag _-prefixed symbols in .py files."""
    code = """
def _private_func() -> None: ...

class _PrivateClass: ...

_private_attr: int
"""
    msgs = _walk_and_release(code, PyiUnderscoreChecker, file_path="test.py")
    assert len(msgs) == 0, f"Expected no messages, got {len(msgs)}"


def test_type_checking_guard() -> None:
    """Checker must NOT flag _-prefixed symbols inside TYPE_CHECKING blocks."""
    code = """
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    _type_checking_only: int
    def _type_checking_func() -> None: ...
    class _TypeCheckingClass: ...
"""
    msgs = _walk_and_release(code, PyiUnderscoreChecker, file_path="test.pyi")
    assert len(msgs) == 0, f"Expected no messages, got {len(msgs)}"


def test_dunders_not_flagged() -> None:
    """Checker must NOT flag dunder names (__name__) in .pyi files."""
    code = """
def __str__() -> str: ...
__all__: list[str]
"""
    msgs = _walk_and_release(code, PyiUnderscoreChecker, file_path="test.pyi")
    assert len(msgs) == 0, f"Expected no messages, got {len(msgs)}"
