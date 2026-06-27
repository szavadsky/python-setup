"""Pylint checker: no _-prefixed symbols in .pyi files.

Flags functions, classes, and module-level attributes whose names start
with ``_`` in ``.pyi`` stub files.  Private/internal symbols should not
appear in type stubs — they are implementation details that clutter the
public API surface.

Skips symbols inside ``if TYPE_CHECKING:`` blocks (they are conditional
and not part of the runtime public API).
"""

from typing import TYPE_CHECKING

from astroid import nodes
from pylint.checkers import BaseChecker

if TYPE_CHECKING:
    from pylint.lint import PyLinter

from python_setup_lint.checkers._base import LintRuleId, MessageDef

class PyiUnderscoreChecker(BaseChecker):
    """AST visitor that flags _-prefixed symbols in .pyi files."""

    name: str = "pyi-underscore"
    msgs: dict[LintRuleId, MessageDef]

    def visit_module(self, node: nodes.Module) -> None: ...
    def visit_functiondef(self, node: nodes.FunctionDef) -> None: ...
    def visit_asyncfunctiondef(self, node: nodes.AsyncFunctionDef) -> None: ...
    def visit_classdef(self, node: nodes.ClassDef) -> None: ...
    def visit_annassign(self, node: nodes.AnnAssign) -> None: ...
    def visit_assign(self, node: nodes.Assign) -> None: ...

def register(linter: PyLinter) -> None: ...
