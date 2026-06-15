"""Shared test infrastructure for pylint checker tests.

Provides reusable helpers used across checker test files:
- ``_make_tc`` — creates a ``CheckerTestCase`` for a given checker class.
- ``_walk_and_release`` — parses code, walks checker, returns released messages.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import astroid
from pylint.testutils import CheckerTestCase

if TYPE_CHECKING:
    from pylint.checkers import BaseChecker

    import pytest


def _make_tc(checker_class: type[BaseChecker]) -> CheckerTestCase:
    """Create a ``CheckerTestCase`` for *checker_class*.

    Sets ``CHECKER_CLASS``, calls ``setup_method()``, returns the test case.
    """
    tc = CheckerTestCase()
    tc.CHECKER_CLASS = checker_class
    tc.setup_method()
    return tc


def _walk_and_release(
    code: str,
    checker_class: type[BaseChecker],
    *,
    file_path: str | None = None,
    module_name: str = "",
) -> list[Any]:
    """Parse *code*, walk *checker_class* over it, return released messages.

    Optionally set *file_path* for path-dependent logic (source-roots,
    test classification) and *module_name* for the astroid module name.
    """
    tc = _make_tc(checker_class)
    module = astroid.parse(code, module_name=module_name)
    if file_path is not None:
        module.file = file_path
    tc.walk(module)
    return tc.linter.release_messages()