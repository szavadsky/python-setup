"""Shared utilities for pylint checkers.

Consolidates duplicate code across checker modules:
- ``_matches_path`` — glob/directory path matching.
- ``_is_under_source_root`` — source-root containment check.
- ``_get_file_path`` — resolve a node's file path.
"""

from pathlib import Path
from typing import NamedTuple

from astroid import nodes
from pylint.lint import PyLinter
from pylint.typing import MessageDefinitionTuple

from python_setup_lint.checkers._decision_backend import DecisionBackend

def _msgs(**definitions: MessageDef) -> dict[str, MessageDefinitionTuple]:
    """Build a checker msgs dict with domain-typed keys."""

def _matches_path(str_path: str, patterns: list[str]) -> bool:
    """Check if *str_path* matches any of the *patterns*.

    Patterns containing ``/`` or ``\\`` are treated as directory prefix
    matches; other patterns are treated as :func:`fnmatch.fnmatch` globs
    against the full path and the basename.
    """

def _is_under_source_root(path: Path, source_roots: list[Path]) -> bool:
    """Check if *path* is under any of the *source_roots*."""

def _get_file_path(node: nodes.NodeNG) -> Path | None:
    """Resolve the file path for an AST node's module."""

def _get_except_str(node: nodes.ExceptHandler) -> str:
    """Get the string representation of the except clause."""

class MessageDef(NamedTuple):
    """Named representation for a pylint checker message definition."""

    message: str
    symbol: str
    description: str

class SourceRootMixin:
    """Mixin for checkers that filter by source root directories.

    Provides shared ``options`` (``source-roots``), ``__init__``, and ``open``
    boilerplate that is structurally identical across multiple checkers by
    pylint API design.
    """

    _source_roots: list[Path]

    options: tuple[tuple[str, dict[str, object]], ...]

    def __init__(self, linter: PyLinter) -> None: ...
    def open(self) -> None: ...
    def _skip_if_outside_source_roots(self, node: nodes.NodeNG) -> bool: ...

class FunctionVisitMixin(SourceRootMixin):
    """Mixin for checkers that visit function definitions.

    Adds ``visit_functiondef`` and ``visit_asyncfunctiondef`` dispatching to
    ``self._check_function(node)``.  Subclass MUST define ``_check_function``.
    """

    def visit_functiondef(self, node: nodes.FunctionDef) -> None: ...
    def visit_asyncfunctiondef(self, node: nodes.AsyncFunctionDef) -> None: ...

def normalize_suppressed_codes(raw: str) -> str:
    """Normalize a suppression directive's rule-code list.

    A leading suppression directive (``type:/ty: ignore[...]``, ``noqa: ...``,
    ``pylint: disable=...``) is stripped. A trailing reason that merely echoes
    the directive's code list order-insensitively is rejected (empty string);
    a real reason is returned alone. Bare text without a directive is returned
    unchanged, minus surrounding whitespace.

    Args:
        raw: The comment text, possibly a full suppression directive.

    Returns:
        The technical reason text, or an empty string when there is none.
    """

def check_if_meaningful(
    text: str,
    *,
    rule: str | None = None,
    code_context: str | None = None,
    comment: str | None = None,
    backend: DecisionBackend | None = None,
) -> bool:
    """Check if a suppression justification is meaningful.

    Runs the heuristic hard gate first: non-meaningful text (brush-off,
    boilerplate, code echo) returns ``False`` without contacting a backend.
    When ``PYTHON_SETUP_LINT_SEMANTIC=1`` and a backend is available, the
    backend may veto the accepted text; an unavailable backend (``None``)
    leaves the heuristic verdict in place. The rule code list is normalized
    by :func:`normalize_suppressed_codes`.

    Args:
        text: The raw justification text.
        rule: The lint rule identifier being suppressed.
        code_context: Surrounding source code lines.
        comment: The justification comment text (preferred over *text*).
        backend: A decision backend; when ``None``, the registered backend is
            resolved and a missing backend falls through to the heuristic.

    Returns:
        True if the justification is meaningful, False otherwise.
    """
