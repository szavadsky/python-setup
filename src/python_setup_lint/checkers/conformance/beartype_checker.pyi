"""Pylint checker: @beartype coverage inventory.

Reports W9701 for public functions/methods missing @beartype decorator.
Informational (W-level) only — does not block builds.

Checker logic
-------------
- Walks AST for ``FunctionDef`` and ``AsyncFunctionDef`` nodes.
- Skips ``_``-prefix functions (file-private per CodingRules.md).
- Skips ``__init__`` (constructor beartype anti-pattern).
- Skips ``__`` dunder methods (``__str__``, ``__repr__``, etc.).
- Skips functions already decorated with ``@beartype``, ``@no_type_check``,
  or ``@typing.no_type_check``.
- Skips modules outside configured source roots.
- Emits ``W9701`` for every remaining public function.

W-level only — does not affect build exit codes.
"""

from typing import TYPE_CHECKING

from astroid import nodes
from pylint.checkers import BaseChecker

from python_setup_lint.checkers._base import SourceRootMixin

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class BeartypeCoverageChecker(BaseChecker, SourceRootMixin):  # type: ignore[misc]  # SourceRootMixin.options conflicts with BaseChecker.options; both define the same pylint options tuple
    """AST visitor that inventories @beartype coverage on public functions."""

    name: str = "beartype-coverage"

    def __init__(self, linter: PyLinter) -> None: ...
    def open(self) -> None: ...
    def visit_functiondef(self, node: nodes.FunctionDef) -> None: ...
    def visit_asyncfunctiondef(self, node: nodes.AsyncFunctionDef) -> None: ...


def register(linter: PyLinter) -> None: ...
