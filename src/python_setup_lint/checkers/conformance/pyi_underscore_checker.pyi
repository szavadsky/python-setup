"""Pylint checker: flag _-prefixed symbols in .pyi files."""


from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter
from pylint.typing import MessageDefinitionTuple

class PyiUnderscoreChecker(BaseChecker):
    """AST visitor that flags _-prefixed symbols in .pyi files."""

    name: str = "pyi-underscore"
    msgs: dict[str, MessageDefinitionTuple]

    def visit_module(self, node: nodes.Module) -> None:
        """Determine if this module is a .pyi file."""

    def visit_classdef(self, node: nodes.ClassDef) -> None:
        """Check class names for _-prefix."""

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Check function names for _-prefix."""


def register(linter: PyLinter) -> None:
    """Register the checker with the linter."""
