from __future__ import annotations

from astroid import nodes
from beartype import beartype
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter  # TYPE_CHECKING-only import; pylint is a dev dependency

from python_setup_lint.checkers._base import (
    MessageDef,
    _matches_path,
    _msgs,
)


class TempFileChecker(BaseChecker):
    name: str = "tempfile-mkdtemp-in-test"
    msgs = _msgs(
        W9702=MessageDef(
            message="Use pytest tmp_path instead of '%s' in test files",
            symbol="tempfile-mkdtemp-in-test",
            description="Test files should use pytest's built-in tmp_path fixture "
            "instead of manual tempfile calls that leak directories.",
        ),
    )
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
        self.add_message("tempfile-mkdtemp-in-test", node=node, args=(self._call_name(node),))

    def _is_tempfile_call(self, node: nodes.Call) -> bool:
        if not isinstance(node.func, nodes.Attribute):
            return False
        if node.func.attrname not in self._TEMP_FILE_FUNCS:
            return False
        return isinstance(node.func.expr, nodes.Name) and node.func.expr.name == "tempfile"

    @staticmethod
    def _is_named_temporary(node: nodes.Call) -> bool:
        return isinstance(node.func, nodes.Attribute) and node.func.attrname == "NamedTemporaryFile"

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
        return _matches_path(file_path, self._test_patterns)


def register(linter: PyLinter) -> None:  # pylint: disable=missing-beartype  # pylint entry point, signature fixed by pylint API; @beartype cannot resolve PyLinter forward ref
    linter.register_checker(TempFileChecker(linter))
