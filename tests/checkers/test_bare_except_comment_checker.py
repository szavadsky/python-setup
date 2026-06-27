"""Unit tests for python_setup_lint.checkers.bare_except_comment_checker.

Uses synthetic code strings parsed via astroid.
"""

from __future__ import annotations


from typing import Any

from python_setup_lint.checkers.conformance.bare_except_comment_checker import (
    BareExceptCommentChecker,
)
from python_setup_lint.testing import _make_tc as _make_tc_factory


def _make_tc() -> Any:
    return _make_tc_factory(BareExceptCommentChecker)


def _walk_and_release(code: str, *, file_path: str = "tests/test_mod.py") -> list[Any]:
    tc = _make_tc()
    import astroid

    module = astroid.parse(code, module_name="test_mod")
    if file_path is not None:
        module.file = file_path
    tc.walk(module)
    return tc.linter.release_messages()


def _msg_ids(msgs: list[Any]) -> set[str]:
    return {m.msg_id for m in msgs}


class TestDetectsBareExceptWithoutComment:
    """Checker must emit W9738 for bare except without justification."""

    def test_detects_bare_except_no_comment(self) -> None:
        msgs = _walk_and_release(
            """
try:
    x = 1
except:
    pass
"""
        )
        assert len(msgs) == 1
        assert msgs[0].msg_id == "bare-except-comment"

    def test_detects_except_exception_no_comment(self) -> None:
        msgs = _walk_and_release(
            """
try:
    x = 1
except Exception:
    pass
"""
        )
        assert len(msgs) == 1
        assert msgs[0].msg_id == "bare-except-comment"

    def test_detects_bare_except_with_logging(self) -> None:
        msgs = _walk_and_release(
            """
try:
    x = 1
except:
    logger.exception("failed")
"""
        )
        assert len(msgs) == 1
        assert msgs[0].msg_id == "bare-except-comment"


class TestSkipsBareExceptWithComment:
    """Checker must NOT flag bare except with justifying comment."""

    def test_skips_bare_except_with_trailing_comment(self) -> None:
        msgs = _walk_and_release(
            """
try:
    x = 1
except:  # expected when network is down
    pass
"""
        )
        assert len(msgs) == 0

    def test_skips_bare_except_with_preceding_comment(self) -> None:
        msgs = _walk_and_release(
            """
try:
    x = 1
# expected when network is down
except:
    pass
"""
        )
        assert len(msgs) == 0

    def test_skips_except_exception_with_comment(self) -> None:
        msgs = _walk_and_release(
            """
try:
    x = 1
except Exception:  # expected during shutdown
    pass
"""
        )
        assert len(msgs) == 0


class TestSkipsBareExceptWithReraise:
    """Checker must NOT flag bare except that re-raises."""

    def test_skips_bare_except_with_bare_raise(self) -> None:
        msgs = _walk_and_release(
            """
try:
    x = 1
except:
    raise
"""
        )
        assert len(msgs) == 0

    def test_skips_except_exception_with_bare_raise(self) -> None:
        msgs = _walk_and_release(
            """
try:
    x = 1
except Exception:
    raise
"""
        )
        assert len(msgs) == 0

    def test_skips_bare_except_with_conditional_raise(self) -> None:
        msgs = _walk_and_release(
            """
try:
    x = 1
except:
    if condition:
        raise
    cleanup()
"""
        )
        assert len(msgs) == 0


class TestSkipsNamedExcept:
    """Checker must NOT flag named except handlers (not bare)."""

    def test_skips_value_error(self) -> None:
        msgs = _walk_and_release(
            """
try:
    x = 1
except ValueError:
    pass
"""
        )
        assert len(msgs) == 0

    def test_skips_os_error(self) -> None:
        msgs = _walk_and_release(
            """
try:
    x = 1
except OSError:
    pass
"""
        )
        assert len(msgs) == 0
