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

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes
from pylint.checkers import BaseChecker

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class BeartypeCoverageChecker(BaseChecker):
    """AST visitor that inventories @beartype coverage on public functions."""

    name: str = "beartype-coverage"

    def __init__(self, linter: PyLinter) -> None: ...
    def open(self) -> None: ...

    def visit_functiondef(self, node: nodes.FunctionDef) -> None: ...
    def visit_asyncfunctiondef(self, node: nodes.AsyncFunctionDef) -> None: ...


def register(linter: PyLinter) -> None: ...