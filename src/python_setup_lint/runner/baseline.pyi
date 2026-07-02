"""Stub for :mod:`python_setup_lint.runner.baseline`.

Violations-only baseline: flat records sorted by (tool, file, line, col).
"""

from pathlib import Path

from .parsers import Record
from .types import LintResult

_FALLBACK_TOOLS: set[str]
"""Legacy stub: always empty. The new format has no fallback path."""


def peek_fallback_tools() -> frozenset[str]:
    """Legacy stub: returns empty frozenset."""


def _compare_sorted(
    a: list[Record], b: list[Record]
) -> tuple[list[Record], list[Record]]:
    """Re-export of :func:`_baseline_helpers._compare_sorted` for backwards compat.

    Returns:
        A tuple ``(added, removed)``.
    """


def _capture_baseline(results: list[LintResult]) -> list[dict[str, object]]:
    """All violations as a flat list sorted by (tool, file, line, col).

    Returns:
        A list of dicts with keys (tool, file, line, col, rule, msg).
    """


def _diff_baseline(current: list[LintResult], baseline_path: Path) -> list[str]:
    """Compare current results against on-disk baseline of flat violation records.

    Crash records (``rule == "__CRASH__"``) are always flagged and never
    baseline-absorbable.

    Returns:
        A list of violation strings. Empty when current output fully
        matches baseline.
    """
