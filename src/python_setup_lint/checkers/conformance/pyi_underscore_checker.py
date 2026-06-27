"""Pylint checker: no _-prefixed symbols in .pyi files.

Flags functions, classes, and module-level attributes whose names start
with ``_`` in ``.pyi`` stub files.  Private/internal symbols should not
appear in type stubs — they are implementation details that clutter the
public API surface.

Skips symbols inside ``if TYPE_CHECKING:`` blocks (they are conditional
and not part of the runtime public API).
"""

from __future__ import annotations

from astroid import nodes
from beartype import beartype
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter  # noqa: TCH002  # TYPE_CHECKING-only import; pylint is a dev dependency

from python_setup_lint.checkers._base import LintRuleId, MessageDef


class PyiUnderscoreChecker(BaseChecker):
    """AST visitor that flags _-prefixed symbols in .pyi files."""

    name: str = "pyi-underscore"
    msgs: dict[LintRuleId, MessageDef] = {
        "W9707": MessageDef(
            message="Private symbol '%s' in .pyi stub file; remove it from the public API surface",
            symbol="pyi-underscore-symbol",
            description="Functions, classes, and module-level attributes with "
            "_-prefixed names should not appear in .pyi stub files.",
        ),
    }

    _is_pyi: bool = False

    @staticmethod
    def _is_private(name: str) -> bool:
        """Check if *name* is a private (underscore-prefixed) symbol.

        Skips dunder names (``__name__``) — they are protocol methods,
        not private implementation details.

        Returns:
            True if *name* is a private (underscore-prefixed) symbol.
        """
        return name.startswith("_") and not (
            name.startswith("__") and name.endswith("__")
        )

    @beartype
    def visit_module(self, node: nodes.Module) -> None:
        # Determine if this module is a .pyi file.
        file_val = node.file
        self._is_pyi = file_val is not None and file_val.endswith(".pyi")

    @beartype
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        # Check function names in .pyi files.
        if not self._is_pyi:
            return
        if self._is_private(node.name) and not _in_type_checking_block(node):
            self.add_message("W9707", node=node, args=(node.name,))

    @beartype
    def visit_asyncfunctiondef(self, node: nodes.AsyncFunctionDef) -> None:
        # Check async function names in .pyi files.
        if not self._is_pyi:
            return
        if self._is_private(node.name) and not _in_type_checking_block(node):
            self.add_message("W9707", node=node, args=(node.name,))

    @beartype
    def visit_classdef(self, node: nodes.ClassDef) -> None:
        # Check class names in .pyi files.
        if not self._is_pyi:
            return
        if self._is_private(node.name) and not _in_type_checking_block(node):
            self.add_message("W9707", node=node, args=(node.name,))

    @beartype
    def visit_annassign(self, node: nodes.AnnAssign) -> None:
        # Check annotated assignment targets in .pyi files.
        if not self._is_pyi:
            return
        if isinstance(node.target, nodes.AssignName) and self._is_private(
            node.target.name
        ):
            if not _in_type_checking_block(node):
                self.add_message("W9707", node=node, args=(node.target.name,))

    @beartype
    def visit_assign(self, node: nodes.Assign) -> None:
        # Check assignment targets in .pyi files.
        if not self._is_pyi:
            return
        for target in node.targets:
            if isinstance(target, nodes.AssignName) and self._is_private(target.name):
                if not _in_type_checking_block(node):
                    self.add_message("W9707", node=node, args=(target.name,))


def _in_type_checking_block(node: nodes.NodeNG) -> bool:
    """Check if *node* is inside an ``if TYPE_CHECKING:`` block.

    Returns:
        True if *node* is inside an ``if TYPE_CHECKING:`` block.
    """
    parent = node.parent
    while parent is not None:
        if isinstance(parent, nodes.If):
            if _is_type_checking_guard(parent.test):
                return True
        parent = parent.parent
    return False


def _is_type_checking_guard(test: nodes.NodeNG) -> bool:
    """Check if *test* is a ``TYPE_CHECKING`` name (Name or Attribute form).

    Returns:
        True if *test* is a ``TYPE_CHECKING`` name (Name or Attribute form).
    """
    if isinstance(test, nodes.Name):
        return test.name == "TYPE_CHECKING"
    if isinstance(test, nodes.Attribute):
        return test.attrname == "TYPE_CHECKING"
    return False


@beartype
def register(linter: PyLinter) -> None:
    # Register the checker with the linter.
    linter.register_checker(PyiUnderscoreChecker(linter))
