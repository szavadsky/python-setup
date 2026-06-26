"""Pylint checker: ban tempfile.mkdtemp/mkstemp/NamedTemporaryFile in tests.

Test files should use pytest's built-in ``tmp_path`` fixture instead of
manual ``tempfile`` calls that leak directories.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

from astroid import nodes
from beartype import beartype
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter  # noqa: TC002

from python_setup_lint.checkers._base import MessageDef


class TempFileChecker(BaseChecker):
    """AST visitor that flags tempfile leakage in test files."""

    name: str = "tempfile-mkdtemp-in-test"
    msgs: dict[str, MessageDef] = {
        "W9702": MessageDef(
            message="Use pytest tmp_path instead of '%s' in test files",
            symbol="tempfile-mkdtemp-in-test",
            description="Test files should use pytest's built-in tmp_path fixture "
            "instead of manual tempfile calls that leak directories.",
        ),
    }
    options = (
        (
            "test-patterns",
            {
                "type": "csv",
                "metavar": "<patterns>",
                "default": ["tests/", "test_*.py", "*_test.py", "conftest.py"],
                "help": "Glob patterns for test file paths.",
            },
        ),
    )

    _TEMP_FILE_FUNCS = frozenset({"mkdtemp", "mkstemp", "NamedTemporaryFile"})

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._test_patterns: list[str] = []

    @beartype
    def open(self) -> None:
        config = self.linter.config
        raw_patterns = getattr(config, "test_patterns", None)
        self._test_patterns = (
            [p.strip() for p in raw_patterns if p.strip()]
            if raw_patterns
            else ["tests/", "test_*.py", "*_test.py", "conftest.py"]
        )

    @beartype
    def visit_call(self, node: nodes.Call) -> None:
        if not self._is_tempfile_call(node):
            return
        if not self._is_test_file(node):
            return
        # For NamedTemporaryFile, only flag if NOT used as context manager
        if self._is_named_temporary(node) and self._is_context_manager(node):
            return
        self.add_message(
            "tempfile-mkdtemp-in-test", node=node, args=(self._call_name(node),)
        )

    def _is_tempfile_call(self, node: nodes.Call) -> bool:
        if not isinstance(node.func, nodes.Attribute):
            return False
        if node.func.attrname not in self._TEMP_FILE_FUNCS:
            return False
        return (
            isinstance(node.func.expr, nodes.Name) and node.func.expr.name == "tempfile"
        )

    @staticmethod
    def _is_named_temporary(node: nodes.Call) -> bool:
        return (
            isinstance(node.func, nodes.Attribute)
            and node.func.attrname == "NamedTemporaryFile"
        )

    @staticmethod
    def _is_context_manager(node: nodes.Call) -> bool:
        parent = node.parent
        if isinstance(parent, nodes.With):
            for expr, _ in parent.items:
                if expr is node:
                    return True
        return False

    def _call_name(self, node: nodes.Call) -> str:
        if isinstance(node.func, nodes.Attribute):
            return f"tempfile.{node.func.attrname}"
        return "tempfile.*"

    def _is_test_file(self, node: nodes.Call) -> bool:
        file_path = getattr(node.root(), "file", None)
        if file_path is None:
            return False
        return self._matches_path(file_path, self._test_patterns)

    @staticmethod
    def _matches_path(str_path: str, patterns: list[str]) -> bool:
        for pattern in patterns:
            if "/" in pattern or "\\" in pattern:
                if (
                    str_path.startswith(pattern)
                    or f"/{pattern.lstrip('/')}" in str_path
                ):
                    return True
            elif fnmatch.fnmatch(str_path, pattern) or fnmatch.fnmatch(
                Path(str_path).name, pattern
            ):
                return True
        return False


@beartype
def register(linter: PyLinter) -> None:
    linter.register_checker(TempFileChecker(linter))
