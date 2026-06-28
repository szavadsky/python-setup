"""Unit tests for python_setup_lint.checkers.missing_error_chain_checker.

Uses synthetic code strings parsed via astroid.
"""

from __future__ import annotations

from typing import Any

from python_setup_lint.checkers.conformance.missing_error_chain_checker import (
    MissingErrorChainChecker,
)
from python_setup_lint.testing import _make_tc as _make_tc_factory


def _make_tc() -> Any:  # pylint: disable=W9728  # test helper: type-specific alias for _make_tc_factory, avoids repeated imports
    return _make_tc_factory(MissingErrorChainChecker)


def _walk_and_release(code: str, *, file_path: str = "tests/test_mod.py") -> list[Any]:
    tc = _make_tc()
    import astroid

    module = astroid.parse(code, module_name="test_mod")
    if file_path is not None:
        module.file = file_path
    tc.walk(module)
    return tc.linter.release_messages()  # type: ignore[no-any-return]  # test fixture builds typed list from Any checker introspection


def _msg_ids(msgs: list[Any]) -> set[str]:
    return {m.msg_id for m in msgs}


class TestDetectsMissingErrorChain:
    """Checker must emit W9739 for raise inside except without from."""

    def test_detects_raise_valueerror(self) -> None:
        msgs = _walk_and_release(
            """
try:
    x = 1
except ValueError:
    raise ValueError("bad")
"""
        )
        assert len(msgs) == 1
        assert msgs[0].msg_id == "missing-error-chain"
        assert "ValueError" in msgs[0].args[0]
        assert "ValueError" in msgs[0].args[1]

    def test_detects_raise_runtimeerror(self) -> None:
        msgs = _walk_and_release(
            """
try:
    risky()
except OSError:
    raise RuntimeError("failed")
"""
        )
        assert len(msgs) == 1
        assert msgs[0].msg_id == "missing-error-chain"

    def test_detects_raise_in_nested_except(self) -> None:
        msgs = _walk_and_release(
            """
try:
    try:
        pass
    except KeyError:
        raise ValueError("inner")
except ValueError:
    pass
"""
        )
        assert len(msgs) == 1
        assert msgs[0].msg_id == "missing-error-chain"

    def test_detects_raise_bare_except(self) -> None:
        msgs = _walk_and_release(
            """
try:
    x = 1
except:
    raise ValueError("bad")
"""
        )
        assert len(msgs) == 1
        assert msgs[0].msg_id == "missing-error-chain"
        assert "bare except" in msgs[0].args[1]


class TestSkipsChainedRaises:
    """Checker must NOT flag raise with from clause."""

    def test_skips_raise_from(self) -> None:
        msgs = _walk_and_release(
            """
try:
    x = 1
except ValueError as e:
    raise ValueError("bad") from e
"""
        )
        assert len(msgs) == 0

    def test_skips_raise_from_cause(self) -> None:
        msgs = _walk_and_release(
            """
try:
    x = 1
except OSError as e:
    raise RuntimeError("failed") from e
"""
        )
        assert len(msgs) == 0


class TestSkipsBareRaise:
    """Checker must NOT flag bare raise (re-raise)."""

    def test_skips_bare_raise(self) -> None:
        msgs = _walk_and_release(
            """
try:
    x = 1
except ValueError:
    raise
"""
        )
        assert len(msgs) == 0

    def test_skips_bare_raise_with_name(self) -> None:
        msgs = _walk_and_release(
            """
try:
    x = 1
except ValueError as e:
    raise
"""
        )
        assert len(msgs) == 0


class TestSkipsRaiseOutsideExcept:
    """Checker must NOT flag raise outside except handlers."""

    def test_skips_raise_in_function(self) -> None:
        msgs = _walk_and_release(
            """
def func():
    raise ValueError("bad")
"""
        )
        assert len(msgs) == 0

    def test_skips_raise_in_try_body(self) -> None:
        msgs = _walk_and_release(
            """
try:
    raise ValueError("bad")
except ValueError:
    pass
"""
        )
        assert len(msgs) == 0

    def test_skips_raise_in_else_block(self) -> None:
        msgs = _walk_and_release(
            """
try:
    pass
except ValueError:
    pass
else:
    raise ValueError("bad")
"""
        )
        assert len(msgs) == 0

    def test_skips_raise_in_finally_block(self) -> None:
        msgs = _walk_and_release(
            """
try:
    pass
except ValueError:
    pass
finally:
    raise ValueError("bad")
"""
        )
        assert len(msgs) == 0
