"""Pylint checker: structlog usage enforcement.

Reports:
- W9710 — ``use-structlog``: flags ``logging.getLogger`` calls.
- W9711 — ``use-structured-logging``: flags printf-style / f-string logger calls.

Checker logic
-------------
- Walks AST for ``Call`` nodes.
- ``_check_logging_getlogger``: flags ``logging.getLogger(...)`` calls.
- ``_check_logger_method_call``: flags ``.debug/.info/.warning/.error/.critical``
  calls on logger objects that use printf-style positional args or f-string
  messages instead of structured keyword arguments.
- Skips modules outside configured source roots.

W-level only — does not affect build exit codes.
"""

from typing import TYPE_CHECKING

from astroid import nodes
from pylint.checkers import BaseChecker

from python_setup_lint.checkers._base import SourceRootMixin

if TYPE_CHECKING:
    from pylint.lint import PyLinter

class StructlogChecker(BaseChecker, SourceRootMixin):  # type: ignore[misc]  # SourceRootMixin.options conflicts with BaseChecker.options; both define the same pylint options tuple
    """AST visitor that enforces structlog usage over stdlib logging."""

    name: str = "structlog-checker"

    def __init__(self, linter: PyLinter) -> None: ...
    def open(self) -> None: ...
    def visit_module(self, _node: nodes.Module) -> None: ...
    def visit_call(self, node: nodes.Call) -> None: ...

def register(linter: PyLinter) -> None: ...
