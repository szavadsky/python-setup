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

def normalize_suppressed_codes(raw: str) -> str:  # pylint: disable=generic-return-requires-returns  # the one-line doc states the return
    """Reduce a suppression comment to its technical reason; ``""`` when none."""

def check_if_meaningful(
    text: str,
    *,
    rule: str | None = None,
    code_context: str | None = None,
    comment: str | None = None,
    backend: DecisionBackend | None = None,
) -> bool:
    """Check if a suppression justification is meaningful.

    The heuristic gate runs first; a backend may only veto, never resurrect.

    Heuristic: non-empty, non-boilerplate, not equal to the rule symbol.
    Uses *comment* as the primary text if provided; falls back to *text*.
    *rule* and *code_context* are the backend query when one is configured.

    Args:
        text: The raw justification text.
        rule: The lint rule identifier being suppressed.
        code_context: Surrounding source code lines.
        comment: The justification comment text (preferred over *text*).
        backend: A decision backend; ``None`` resolves the registered backend.

    Returns:
        True if the justification is meaningful, False otherwise.
    """
