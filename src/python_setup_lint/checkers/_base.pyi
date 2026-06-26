"""Shared utilities for pylint checkers.

Consolidates duplicate code across checker modules:
- ``_matches_path`` — glob/directory path matching.
- ``_is_under_source_root`` — source-root containment check.
- ``_get_file_path`` — resolve a node's file path.
"""


from pathlib import Path

from astroid import nodes

def _matches_path(str_path: str, patterns: list[str]) -> bool:
    """Check if *str_path* matches any of the *patterns*.

    Patterns containing ``/`` or ``\\`` are treated as directory prefix
    matches; other patterns are treated as :func:`fnmatch.fnmatch` globs
    against the full path and the basename.
    """


def _is_under_source_root(path: Path, source_roots: list[Path]) -> bool:
    """Check if *path* is under any of the *source_roots*."""


def _get_file_path(node: nodes.FunctionDef | nodes.AsyncFunctionDef) -> Path | None:
    """Resolve the file path for an AST node's module."""
