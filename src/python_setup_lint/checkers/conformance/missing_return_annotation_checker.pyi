"""Pylint checker: missing return type annotations on _-prefixed functions.

Reports W9741 for module-private functions (``_``-prefixed, not ``__`` dunders)
that lack a return type annotation.  Public functions are covered by the
beartype checker; this fills the gap for private helpers.

Checker logic
-------------
- Walks AST for ``FunctionDef`` and ``AsyncFunctionDef`` nodes.
- Skips public functions (no ``_`` prefix) — beartype checker covers those.
- Skips ``__`` dunder methods (``__init__``, ``__post_init__``, etc.).
- Skips functions that already have a return annotation.
- Skips modules outside configured source roots.
- Emits ``W9741`` for every remaining _-prefixed function.

W-level only — does not affect build exit codes.
"""

from typing import TYPE_CHECKING

from astroid import nodes
from pylint.checkers import BaseChecker

if TYPE_CHECKING:
    from pylint.lint import PyLinter

class MissingReturnAnnotationChecker(BaseChecker):
    """AST visitor that flags _-prefixed functions missing return annotations."""

    name: str = "missing-return-annotation"

    def __init__(self, linter: PyLinter) -> None: ...
    def open(self) -> None: ...
    def visit_functiondef(self, node: nodes.FunctionDef) -> None: ...
    def visit_asyncfunctiondef(self, node: nodes.AsyncFunctionDef) -> None: ...

def register(linter: PyLinter) -> None: ...
