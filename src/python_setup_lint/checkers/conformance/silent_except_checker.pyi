"""Pylint checker: flag except handlers that neither log nor re-raise.

Caught errors must be logged or re-raised (CodingRules: fail-fast, no swallowed
exceptions).  Every ``except`` clause whose body contains no logging call and
no ``raise`` statement is flagged.
"""

from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter

class SilentExceptChecker(BaseChecker):
    """AST visitor that flags except handlers that neither log nor re-raise."""

    name: str = "silent-except"

    def visit_excepthandler(self, node: nodes.ExceptHandler) -> None:
        """Check except handlers for silent exception swallowing."""
        ...

def register(linter: PyLinter) -> None:
    """Register the checker with the linter."""
    ...
