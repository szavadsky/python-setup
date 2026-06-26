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
    """AST visitor that flags usage docstrings in .py files with companion .pyi.

    Also enforces:
    - Generic-return-requires-Returns: functions with non-None concrete return
      type annotations must have a ``Returns:`` clause in their docstring.
    - Internal-helper-docstring-allowed: ``_``-prefixed helpers MAY have a
      docstring (relaxes the existing rule for public functions).
    """

    name: str  # "stub-docstring-checker"

    def visit_module(self, node: nodes.Module) -> None:
        """Decide whether this module should be processed; set up state."""

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Check function for docstring and returns-clause rules."""

    def visit_asyncfunctiondef(self, node: nodes.AsyncFunctionDef) -> None:
        """Check async function for docstring and returns-clause rules."""

        self, func_node: nodes.FunctionDef | nodes.AsyncFunctionDef
    ) -> None:
        """Apply all docstring rules to *func_node*."""

        self, func_node: nodes.FunctionDef | nodes.AsyncFunctionDef
    ) -> None:
        """Emit W9701 if function has a non-None return type but no Returns: clause."""

    @staticmethod
        """Check if a docstring contains a Returns: or Yields: clause."""

def register(linter: PyLinter) -> None: ...
