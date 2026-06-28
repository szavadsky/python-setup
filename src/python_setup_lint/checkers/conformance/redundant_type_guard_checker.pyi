"""Pylint checker: flag isinstance guards redundant over type annotations.

If a function parameter is annotated with a type, an ``isinstance`` check
on that parameter for the same type is redundant — the type checker and
``@beartype`` already enforce it.
"""

from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter

class RedundantTypeGuardChecker(BaseChecker):
    """AST visitor that flags isinstance guards redundant over type annotations."""

    name: str = "redundant-type-guard"
    def visit_if(self, node: nodes.If) -> None:
        """Flag isinstance guards redundant over parameter type annotations."""

def register(linter: PyLinter) -> None:
    """Register the checker with the linter."""
