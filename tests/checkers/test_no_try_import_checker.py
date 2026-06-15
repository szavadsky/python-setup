"""Unit tests for python_setup_lint.checkers.no_try_import_checker.

Uses pylint.testutils.CheckerTestCase to verify the AST checker
detects (and does not detect) the correct patterns.
"""

from __future__ import annotations

from python_setup_lint.checkers.no_try_import_checker import NoTryImportChecker
from python_setup_lint.testing import _walk_and_release


class TestDetectsFixableViolations:
    """Checker must flag all try/except ImportError patterns."""

    def test_import_in_try_except_importerror(self):
        msgs = _walk_and_release("""
try:
    import litellm
except ImportError:
    pass
""", NoTryImportChecker)
        assert len(msgs) == 1
        assert msgs[0].msg_id == "no-try-import"
        assert msgs[0].args == ("ImportError",)

    def test_import_in_try_except_modulenotfound(self):
        msgs = _walk_and_release("""
try:
    import litellm
except ModuleNotFoundError:
    pass
""", NoTryImportChecker)
        assert len(msgs) == 1
        assert msgs[0].msg_id == "no-try-import"

    def test_from_import_in_try_except_importerror(self):
        msgs = _walk_and_release("""
try:
    from pydantic import ValidationError
except ImportError:
    pass
""", NoTryImportChecker)
        assert len(msgs) == 1
        assert msgs[0].msg_id == "no-try-import"

    def test_import_in_try_bare_except(self):
        msgs = _walk_and_release("""
try:
    import httpx
except:
    pass
""", NoTryImportChecker)
        assert len(msgs) == 1
        assert msgs[0].args == ("bare except",)

    def test_import_in_try_tuple_import_errors(self):
        msgs = _walk_and_release("""
try:
    import litellm
except (ImportError, ModuleNotFoundError):
    pass
""", NoTryImportChecker)
        assert len(msgs) == 1

    def test_two_imports_separate_try_blocks(self):
        msgs = _walk_and_release("""
try:
    import litellm
except ImportError:
    pass

try:
    import httpx
except ImportError:
    pass
""", NoTryImportChecker)
        assert len(msgs) == 2

    def test_two_imports_separate_handlers_one_try(self):
        msgs = _walk_and_release("""
try:
    import litellm
except ImportError:
    pass
except ModuleNotFoundError:
    pass
""", NoTryImportChecker)
        assert len(msgs) == 2

    def test_import_in_try_non_import_handler_not_flagged(self):
        msgs = _walk_and_release("""
try:
    import litellm
except ValueError:
    pass
""", NoTryImportChecker)
        assert len(msgs) == 0

    def test_handler_mixed_import_and_non_import(self):
        msgs = _walk_and_release("""
try:
    import httpx
except ValueError:
    pass
except ImportError:
    pass
except OSError:
    pass
""", NoTryImportChecker)
        assert len(msgs) == 1

    def test_proxy_module_level_guard(self):
        msgs = _walk_and_release("""
try:
    import litellm as _litellm
except ImportError:
    _litellm = None
""", NoTryImportChecker)
        assert len(msgs) == 1


class TestDoesNotDetect:
    """Checker does NOT flag valid code."""

    def test_try_without_import(self):
        msgs = _walk_and_release("""
try:
    x = 1 / 0
except ZeroDivisionError:
    pass
""", NoTryImportChecker)
        assert len(msgs) == 0

    def test_import_outside_try(self):
        msgs = _walk_and_release("""
import os
x = os.path.join('a', 'b')
""", NoTryImportChecker)
        assert len(msgs) == 0

    def test_empty_module(self):
        msgs = _walk_and_release("", NoTryImportChecker)
        assert len(msgs) == 0

    def test_non_import_exception_handling(self):
        msgs = _walk_and_release("""
try:
    result = api_call()
except ConnectionError:
    result = None
""", NoTryImportChecker)
        assert len(msgs) == 0