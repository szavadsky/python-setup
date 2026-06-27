"""Pylint checker: flag trivial wrapper functions.

Wrappers that simply delegate to another function with a matching signature
are unnecessary indirection — justified only if removing them forces callers
to understand an internal dependency's interface. Otherwise inline.
"""

from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter

class TrivialWrapperChecker(BaseChecker):
    """AST visitor that flags trivial wrapper functions."""

    name: str = "trivial-wrapper"

    def visit_functiondef(self, node: nodes.FunctionDef) -> None: ...
    def visit_asyncfunctiondef(self, node: nodes.AsyncFunctionDef) -> None: ...

def register(linter: PyLinter) -> None: ...
