"""Pylint checker: require error chaining (raise X from Y) inside except handlers.

Bare ``raise SomeException(...)`` inside an ``except`` block loses the original
traceback.  The checker flags any ``raise`` with an explicit exception that
lacks a ``from`` clause when it appears inside an ``except`` handler.
"""

from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter

class MissingErrorChainChecker(BaseChecker):
    """AST visitor that flags bare raises inside except handlers."""

    name: str = "missing-error-chain"

    def __init__(self, linter: PyLinter) -> None: ...
    def visit_raise(self, node: nodes.Raise) -> None: ...

def register(linter: PyLinter) -> None: ...
