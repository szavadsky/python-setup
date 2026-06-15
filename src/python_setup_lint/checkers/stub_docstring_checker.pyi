"""Pylint checker: docstring-in-.pyi verification.

CodingRules.md rule: ".pyi only: all usage docstrings".

Public entry points:
- ``StubDocstringChecker`` — ``BaseChecker`` subclass registered via ``register()``.
- ``register(linter)`` — pylint plugin entrypoint, called from ``pyproject.toml``.
"""

from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter

class StubDocstringChecker(BaseChecker):
    """AST visitor that flags usage docstrings in .py files with companion .pyi."""

    name: str  # "stub-docstring-checker"
    _enabled_for_module: bool
    _current_module_name: str | None

    def visit_module(self, node: nodes.Module) -> None: ...
    def visit_functiondef(self, node: nodes.FunctionDef) -> None: ...
    def visit_asyncfunctiondef(self, node: nodes.AsyncFunctionDef) -> None: ...
    def _emit_if_docstring(
        self, func_node: nodes.FunctionDef | nodes.AsyncFunctionDef
    ) -> None: ...


def register(linter: PyLinter) -> None: ...