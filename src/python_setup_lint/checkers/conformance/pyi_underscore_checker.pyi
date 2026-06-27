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
from pylint.typing import ExtraMessageOptions

if TYPE_CHECKING:
    from pylint.lint import PyLinter

from python_setup_lint.checkers._base import LintRuleId, MessageDef

class PyiUnderscoreChecker(BaseChecker):
    """AST visitor that flags _-prefixed symbols in .pyi files."""

    name: str = "pyi-underscore"
    msgs: dict[str, tuple[str, str, str] | tuple[str, str, str, ExtraMessageOptions]]

    def visit_module(self, node: nodes.Module) -> None:
        """Determine if this module is a .pyi file."""
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Check function names in .pyi files.

        Flags functions whose names start with ``_`` in ``.pyi`` stub files.
        Skips symbols inside ``if TYPE_CHECKING:`` blocks.
        """
    def visit_asyncfunctiondef(self, node: nodes.AsyncFunctionDef) -> None:
        """Check async function names in .pyi files.

        Flags async functions whose names start with ``_`` in ``.pyi`` stub files.
        Skips symbols inside ``if TYPE_CHECKING:`` blocks.
        """
    def visit_classdef(self, node: nodes.ClassDef) -> None:
        """Check class names in .pyi files.

        Flags classes whose names start with ``_`` in ``.pyi`` stub files.
        Skips symbols inside ``if TYPE_CHECKING:`` blocks.
        """
    def visit_annassign(self, node: nodes.AnnAssign) -> None:
        """Check annotated assignment targets in .pyi files.

        Flags annotated assignments whose target names start with ``_``.
        Skips symbols inside ``if TYPE_CHECKING:`` blocks.
        """
    def visit_assign(self, node: nodes.Assign) -> None:
        """Check assignment targets in .pyi files.

        Flags assignments whose target names start with ``_``.
        Skips symbols inside ``if TYPE_CHECKING:`` blocks.
        """

def register(linter: PyLinter) -> None:
    """Register the checker with the linter."""
