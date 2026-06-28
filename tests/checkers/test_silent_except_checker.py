"""Unit tests for python_setup_lint.checkers.silent_except_checker.

Uses synthetic code strings parsed via astroid.
"""

from __future__ import annotations

from typing import Any

from python_setup_lint.checkers.conformance.silent_except_checker import (
    SilentExceptChecker,
)
from python_setup_lint.testing import _make_tc as _make_tc_factory


def _make_tc() -> Any:  # pylint: disable=W9728  # test helper: type-specific alias for _make_tc_factory, avoids repeated imports
    return _make_tc_factory(SilentExceptChecker)


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


class TestDetectsSilentExcept:
    """Checker must emit W9740 for except handlers that neither log nor re-raise."""

    def test_silent_bare_except(self) -> None:
        code = """
def foo():
    try:
        risky()
    except:
        pass
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 1
        assert msgs[0].msg_id == "silent-except"

    def test_silent_named_except(self) -> None:
        code = """
def foo():
    try:
        risky()
    except ValueError:
        pass
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 1
        assert msgs[0].msg_id == "silent-except"

    def test_silent_multi_except(self) -> None:
        code = """
def foo():
    try:
        risky()
    except (ValueError, KeyError):
        pass
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 1
        assert msgs[0].msg_id == "silent-except"

    def test_silent_except_with_comment(self) -> None:
        code = """
def foo():
    try:
        risky()
    except ValueError:
        # expected
        pass
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 1
        assert msgs[0].msg_id == "silent-except"

    def test_silent_except_with_ellipsis(self) -> None:
        code = """
def foo():
    try:
        risky()
    except ValueError:
        ...
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 1
        assert msgs[0].msg_id == "silent-except"


class TestSkipsExceptWithRaise:
    """Checker must NOT flag except handlers that re-raise."""

    def test_bare_raise(self) -> None:
        code = """
def foo():
    try:
        risky()
    except ValueError:
        raise
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0

    def test_named_raise(self) -> None:
        code = """
def foo():
    try:
        risky()
    except ValueError as e:
        raise e
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0

    def test_raise_other(self) -> None:
        code = """
def foo():
    try:
        risky()
    except ValueError:
        raise RuntimeError("wrapped")
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0


class TestSkipsExceptWithLogging:
    """Checker must NOT flag except handlers that log."""

    def test_log_call(self) -> None:
        code = """
import logging

def foo():
    try:
        risky()
    except ValueError:
        logging.warning("oops")
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0

    def test_logger_call(self) -> None:
        code = """
import logging

logger = logging.getLogger(__name__)

def foo():
    try:
        risky()
    except ValueError:
        logger.error("oops")
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0

    def test_log_object_call(self) -> None:
        code = """
import logging

log = logging.getLogger(__name__)

def foo():
    try:
        risky()
    except ValueError:
        log.exception("oops")
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0

    def test_log_exception_call(self) -> None:
        code = """
import logging

log = logging.getLogger(__name__)

def foo():
    try:
        risky()
    except ValueError:
        log.exception("oops")
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0

    def test_logging_exception(self) -> None:
        code = """
import logging

def foo():
    try:
        risky()
    except ValueError:
        logging.exception("oops")
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0


class TestSkipsNonExcept:
    """Checker must not flag code outside except handlers."""

    def test_no_except(self) -> None:
        code = """
def foo():
    pass
"""
        msgs = _walk_and_release(code)
        assert len(msgs) == 0
