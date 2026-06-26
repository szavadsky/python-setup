"""Pylint checker: ban try/except ImportError patterns.

Imports must be unconditional — missing dependencies should fail fast at
startup rather than silently degrade at runtime.
"""

from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter
from typing import ClassVar


class NoTryImportChecker(BaseChecker):
    """AST visitor that flags try blocks containing imports caught by ImportError / ModuleNotFoundError."""

    name: ClassVar[str] = "no-try-import"

    def visit_try(self, node: nodes.Try) -> None: ...


def register(linter: PyLinter) -> None: ...
