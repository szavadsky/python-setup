"""Unit tests for python_setup_lint.checkers.redundant_type_guard_checker.

Uses synthetic code strings parsed via astroid.
"""

from __future__ import annotations

from typing import Any

from python_setup_lint.checkers.conformance.redundant_type_guard_checker import (
    RedundantTypeGuardChecker,
)
from python_setup_lint.testing import _make_tc as _make_tc_factory


def _make_tc() -> Any:  # pylint: disable=trivial-wrapper  # test helper; readability over DRY
    return _make_tc_factory(RedundantTypeGuardChecker)


def _walk_and_release(code: str) -> list[Any]:
    tc = _make_tc()
    module = __import__("astroid").parse(code)
    tc.walk(module)
    return tc.linter.release_messages()  # type: ignore[no-any-return]  # test fixture builds typed list from Any checker introspection


def _msg_ids(msgs: list[Any]) -> set[str]:
    return {m.msg_id for m in msgs}


class TestDetectsRedundantTypeGuard:
    """Checker must emit W9729 for redundant isinstance guards."""

    def test_simple_redundant_guard(self) -> None:
        code = """
def process(x: int) -> None:
    if not isinstance(x, int):
        raise TypeError("bad")
    return x
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 1
        assert msgs[0].msg_id == "redundant-type-guard"
        assert msgs[0].args == ("x", "int", "x", "int")

    def test_different_param_name(self) -> None:
        code = """
def process(value: str) -> None:
    if not isinstance(value, str):
        raise ValueError("bad")
    return value
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 1
        assert msgs[0].msg_id == "redundant-type-guard"

    def test_float_type(self) -> None:
        code = """
def process(score: float) -> None:
    if not isinstance(score, float):
        raise TypeError("bad")
    return score
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 1
        assert msgs[0].msg_id == "redundant-type-guard"

    def test_bool_type(self) -> None:
        code = """
def process(flag: bool) -> None:
    if not isinstance(flag, bool):
        raise TypeError("bad")
    return flag
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 1
        assert msgs[0].msg_id == "redundant-type-guard"


class TestSkipsNonRedundantGuards:
    """Checker must NOT flag non-redundant isinstance guards."""

    def test_no_annotation(self) -> None:
        code = """
def process(x) -> None:
    if not isinstance(x, int):
        raise TypeError("bad")
    return x
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0

    def test_type_mismatch(self) -> None:
        code = """
def process(x: int) -> None:
    if not isinstance(x, str):
        raise TypeError("bad")
    return x
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0

    def test_union_annotation(self) -> None:
        code = """
def process(x: int | str) -> None:
    if not isinstance(x, int):
        raise TypeError("bad")
    return x
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0

    def test_tuple_isinstance(self) -> None:
        code = """
def process(x: int) -> None:
    if not isinstance(x, (int, str)):
        raise TypeError("bad")
    return x
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0

    def test_no_raise_in_body(self) -> None:
        code = """
def process(x: int) -> None:
    if not isinstance(x, int):
        return
    return x
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0

    def test_not_not_isinstance(self) -> None:
        code = """
def process(x: int) -> None:
    if isinstance(x, int):
        raise TypeError("bad")
    return x
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0

    def test_not_isinstance_other_func(self) -> None:
        code = """
def process(x: int) -> None:
    if not hasattr(x, "foo"):
        raise TypeError("bad")
    return x
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0

    def test_guard_on_non_param(self) -> None:
        code = """
def process(x: int) -> None:
    y = get_value()
    if not isinstance(y, int):
        raise TypeError("bad")
    return x
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0

    def test_guard_on_different_param(self) -> None:
        code = """
def process(x: int, y: str) -> None:
    if not isinstance(y, int):
        raise TypeError("bad")
    return x
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0


class TestSkipsClassScope:
    """Checker must NOT flag isinstance guards inside class methods."""

    def test_class_method(self) -> None:
        code = """
class MyClass:
    def process(self, x: int) -> None:
        if not isinstance(x, int):
            raise TypeError("bad")
        return x
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0

    def test_static_method(self) -> None:
        code = """
class MyClass:
    @staticmethod
    def process(x: int) -> None:
        if not isinstance(x, int):
            raise TypeError("bad")
        return x
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0


class TestEdgeCases:
    """Edge cases for the checker."""

    def test_multiple_params_one_guard(self) -> None:
        code = """
def process(x: int, y: str) -> None:
    if not isinstance(x, int):
        raise TypeError("bad")
    return x
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 1
        assert msgs[0].msg_id == "redundant-type-guard"

    def test_multiple_ifs_only_one_redundant(self) -> None:
        code = """
def process(x: int, y: str) -> None:
    if not isinstance(x, int):
        raise TypeError("bad")
    if not isinstance(y, str):
        raise ValueError("bad")
    return x
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 2
        assert _msg_ids(msgs) == {"redundant-type-guard"}

    def test_guard_with_else(self) -> None:
        code = """
def process(x: int) -> None:
    if not isinstance(x, int):
        raise TypeError("bad")
    else:
        return x
    return x
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 1
        assert msgs[0].msg_id == "redundant-type-guard"
