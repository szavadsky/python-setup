"""Shared utilities for pylint checkers.

Consolidates duplicate code across checker modules:
- ``MessageDef`` — named representation for checker message definitions.
- ``_matches_path`` — glob/directory path matching.
- ``_is_under_source_root`` — source-root containment check.
- ``_get_file_path`` — resolve a node's file path.
"""

from pathlib import Path
from typing import NamedTuple, NewType

from astroid import nodes


LintRuleId: type[str]


class MessageDef(NamedTuple):
    """Named representation for a pylint checker message definition."""

    message: str
    symbol: str
    description: str


    """Check if *str_path* matches any of the *patterns*.

    Patterns containing ``/`` or ``\\`` are treated as directory prefix
    matches; other patterns are treated as :func:`fnmatch.fnmatch` globs
    against the full path and the basename.
    """


    """Check if *path* is under any of the *source_roots*."""


    """Resolve the file path for an AST node's module."""

def check_if_meaningful(
    text: str,
    *,
    rule: str | None = None,
    code_context: str | None = None,
    comment: str | None = None,
) -> bool:
    """Check if a suppression justification is meaningful.

    Heuristic: non-empty, non-boilerplate, contains a noun not equal to the rule symbol.
    Uses *comment* as the primary text if provided; falls back to *text*.
    *rule* and *code_context* are reserved for future semantic analysis.
    """
