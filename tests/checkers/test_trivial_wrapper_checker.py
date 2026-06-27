"""Unit tests for python_setup_lint.checkers.trivial_wrapper_checker.

Tests the TrivialWrapperChecker (W9728) which flags functions that are
trivial wrappers — 1-3 line functions that only delegate to another
function with a matching signature.
"""

from __future__ import annotations

from typing import Any

from python_setup_lint.checkers.conformance.trivial_wrapper_checker import (
    TrivialWrapperChecker,
)
from python_setup_lint.testing import _make_tc as _make_tc_factory


def _make_tc() -> Any:
    return _make_tc_factory(TrivialWrapperChecker)


def _walk_and_release(code: str) -> list[Any]:
    tc = _make_tc()
    tc.checker.open()
    module = __import__("astroid").parse(code)
    tc.walk(module)
    return tc.linter.release_messages()


def _msg_ids(msgs: list[Any]) -> set[str]:
    return {m.msg_id for m in msgs}


# ── Detect cases ────────────────────────────────────────────────────


class TestDetectsTrivialWrapper:
    """Checker must emit W9728 for trivial wrapper functions."""

    def test_bare_call(self) -> None:
        code = """
def my_func(x: int) -> int:
    return other_func(x)
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 1
        assert msgs[0].msg_id == "trivial-wrapper"
        assert msgs[0].args == ("my_func", "other_func")

    def test_expression_statement(self) -> None:
        code = """
def my_func(x: int) -> None:
    other_func(x)
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 1
        assert msgs[0].msg_id == "trivial-wrapper"

    def test_assign_and_return(self) -> None:
        code = """
def my_func(x: int) -> int:
    result = other_func(x)
    return result
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 1
        assert msgs[0].msg_id == "trivial-wrapper"

    def test_async_function(self) -> None:
        code = """
async def my_func(x: int) -> int:
    return await other_func(x)
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 1
        assert msgs[0].msg_id == "trivial-wrapper"

    def test_module_level_function(self) -> None:
        code = """
def get_config() -> dict:
    return load_config()
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 1
        assert msgs[0].args == ("get_config", "load_config")


# ── Non-detect cases ────────────────────────────────────────────────


class TestSkipsNonTrivial:
    """Checker must NOT flag non-trivial functions."""

    def test_complex_body(self) -> None:
        code = """
def my_func(x: int) -> int:
    result = other_func(x)
    result += 1
    return result
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0

    def test_empty_body(self) -> None:
        code = """
def my_func() -> None:
    ...
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0

    def test_docstring_only(self) -> None:
        code = """
def my_func() -> None:
    \"\"\"Just a docstring.\"\"\"
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0

    def test_actual_logic(self) -> None:
        code = """
def my_func(x: int) -> int:
    return x + 1
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0

    def test_conditional(self) -> None:
        code = """
def my_func(x: int) -> int:
    if x > 0:
        return other_func(x)
    return 0
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0


class TestSkipsExemptNames:
    """Checker must NOT flag exempt function names."""

    def test_register(self) -> None:
        code = """
def register(linter: object) -> None:
    linter.register_checker(MyChecker(linter))
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0


class TestSkipsOverload:
    """Checker must NOT flag @overload decorated functions."""

    def test_overload_stubs_skipped(self) -> None:
        """Overload stubs with ... body are skipped."""
        code = """
from typing import overload

@overload
def my_func(x: int) -> int: ...

@overload
def my_func(x: str) -> str: ...
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0

    def test_overload_implementation_flagged(self) -> None:
        """The actual implementation of an overloaded function is still checked."""
        code = """
from typing import overload

@overload
def my_func(x: int) -> int: ...

@overload
def my_func(x: str) -> str: ...

def my_func(x: int | str) -> int | str:
    return other_func(x)
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 1
        assert msgs[0].msg_id == "trivial-wrapper"


class TestSkipsAbstractMethods:
    """Checker must NOT flag abstract methods."""

    def test_abstractmethod(self) -> None:
        code = """
from abc import abstractmethod

class MyBase:
    @abstractmethod
    def my_func(self, x: int) -> int:
        return other_func(x)
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0

    def test_protocol_method(self) -> None:
        code = """
from typing import Protocol

class MyProto(Protocol):
    def my_func(self, x: int) -> int:
        return other_func(x)
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0

    def test_abc_method(self) -> None:
        code = """
from abc import ABC

class MyAbc(ABC):
    def my_func(self, x: int) -> int:
        return other_func(x)
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0


class TestSkipsSelfDelegation:
    """Checker must NOT flag self-method delegation."""

    def test_self_call(self) -> None:
        code = """
class MyClass:
    def my_func(self, x: int) -> int:
        return self._internal(x)
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0


class TestSkipsRecursive:
    """Checker must NOT flag recursive calls."""

    def test_recursive(self) -> None:
        code = """
def my_func(x: int) -> int:
    return my_func(x - 1)
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0


class TestSkipsSignatureMismatch:
    """Checker must NOT flag when signatures don't match."""

    def test_different_arg_count(self) -> None:
        code = """
def my_func(x: int) -> int:
    return other_func(x, 42, extra)
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0
