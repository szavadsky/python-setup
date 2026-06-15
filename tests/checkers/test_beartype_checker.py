"""Unit tests for python_setup_lint.checkers.beartype_checker.

Uses synthetic code strings parsed via astroid, with module.file patched to
simulate paths under a configured source root.
"""

from __future__ import annotations

from pathlib import Path

import astroid
from pylint.testutils import CheckerTestCase

from python_setup_lint.checkers.beartype_checker import BeartypeCoverageChecker


def _make_tc() -> CheckerTestCase:
    tc = CheckerTestCase()
    tc.CHECKER_CLASS = BeartypeCoverageChecker
    tc.setup_method()
    tc.checker.open()
    return tc


def _walk_and_release(code: str, *, file_path: str = "src/test_mod.py") -> list:
    tc = _make_tc()
    module = astroid.parse(code)
    module.file = file_path
    tc.walk(module)
    return tc.linter.release_messages()


def _msg_ids(msgs: list) -> set[str]:
    return {m.msg_id for m in msgs}


class TestDetectsMissingBeartype:
    """Checker must emit W9701 for public functions without @beartype."""

    def test_plain_def(self):
        msgs = _walk_and_release("def foo(): pass")
        assert len(msgs) == 1
        assert msgs[0].msg_id == "missing-beartype"

    def test_async_def(self):
        msgs = _walk_and_release("async def foo(): pass")
        assert len(msgs) == 1
        assert msgs[0].msg_id == "missing-beartype"

    def test_public_method_in_class(self):
        msgs = _walk_and_release("class X:\n    def method(self): pass")
        assert msgs[0].msg_id == "missing-beartype"
        assert msgs[0].args[0] == "method"

    def test_multiple_public_functions(self):
        msgs = _walk_and_release("def foo(): pass\ndef bar(): pass\n")
        assert len(msgs) == 2


class TestSkipsPrivate:
    """Checker must skip _-prefix functions."""

    def test_private_function(self):
        assert len(_walk_and_release("def _helper(): pass")) == 0

    def test_mixed_public_and_private(self):
        msgs = _walk_and_release("def public(): pass\ndef _private(): pass\n")
        assert len(msgs) == 1
        assert msgs[0].args[0] == "public"


class TestSkipsInitAndDunders:
    def test_init_skipped(self):
        assert len(_walk_and_release("class X:\n    def __init__(self): pass")) == 0

    def test_str_skipped(self):
        assert len(_walk_and_release("class X:\n    def __str__(self): pass")) == 0

    def test_dunder_only_init_skipped(self):
        msgs = _walk_and_release("class X:\n    def __init__(self): pass\n    def run(self): pass")
        assert len(msgs) == 1
        assert msgs[0].args[0] == "run"


class TestSkipsDecorated:
    def test_beartype_decorator(self):
        msgs = _walk_and_release("""
from beartype import beartype
@beartype
def foo(): pass
""")
        assert len(msgs) == 0

    def test_no_type_check_decorator(self):
        msgs = _walk_and_release("""
from typing import no_type_check
@no_type_check
def foo(): pass
""")
        assert len(msgs) == 0

    def test_typing_no_type_check(self):
        msgs = _walk_and_release("""
import typing
@typing.no_type_check
def foo(): pass
""")
        assert len(msgs) == 0

    def test_mixed_decorated_and_undecorated(self):
        msgs = _walk_and_release("""
from beartype import beartype
@beartype
def foo(): pass
def bar(): pass
""")
        assert len(msgs) == 1
        assert msgs[0].args[0] == "bar"


class TestSourceRootFiltering:
    def test_outside_source_root(self):
        assert len(_walk_and_release("def foo(): pass", file_path="tests/test_mod.py")) == 0

    def test_under_source_root(self):
        assert len(_walk_and_release("def foo(): pass", file_path="src/prod.py")) == 1