"""Stub for :mod:`python_setup_lint.runner.baseline`.

Violations-only baseline: flat records sorted by (tool, file, line, col).
"""

from pathlib import Path

from .types import LintResult

def peek_fallback_tools() -> frozenset[str]:
    """Package-export shim, deleted with ``runner/__init__``'s re-export."""

def _capture_baseline(results: list[LintResult], *, cwd: Path | None = None) -> list[dict[str, object]]:
    """All violations as a flat list sorted by (tool, file, line, col, rule).

    Args:
        results: List of lint results to capture.
        cwd: If provided, absolute ``file`` paths are relativized against
            this directory.

    Returns:
        A list of dicts with keys (tool, file, line, col, rule, msg).
    """

def _diff_baseline(current: list[LintResult], baseline_path: Path, *, cwd: Path | None = None) -> list[str]:
    """Compare current results against on-disk baseline of flat violation records.

    Crash records (``rule == "__CRASH__"``) are always flagged and never
    baseline-absorbable.

    Args:
        current: Current lint results.
        baseline_path: Path to the on-disk baseline file.
        cwd: If provided, absolute ``file`` paths in *current* are relativized
            against this directory before comparison.

    Returns:
        A list of violation strings. Empty when current output fully
        matches baseline.
    """

def _write_baseline_if_modified(
    violations: list[dict[str, object]],
    baseline_path: Path,
    baseline_modified: bool,
) -> list[str] | None:
    """Atomically write baseline via temp file if modified.

    Returns:
        ``None`` on success, or a list containing one error string on failure.
    """
