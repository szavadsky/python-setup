"""Stub for :mod:`python_setup_lint.runner.baseline`.

Baseline capture + diff with silent shrinkage auto-record (T0 / D9).
Additions ONLY are flagged as regressions; removals rewrite the baseline
in-place.
"""

from pathlib import Path
from typing import Any

from .types import LintResult

def _capture_baseline(results: list[LintResult]) -> list[dict[str, Any]]:
    """Capture structured baseline data from tool results.

    Each entry contains the tool name, exit code, and one of:
    - ``output`` (raw stdout) for non-JSON tools
    - ``diagnostics`` (parsed JSON) for pyright and rumdl check.

    Ruff output is line-sorted for stability across runs; rumdl success
    timing ``(Nms)`` is collapsed to ``(XXXms)``.

    Args:
        results: :class:`LintResult` list from one ``run_lint`` invocation.
    """

def _diff_baseline(current: list[LintResult], baseline_path: Path) -> list[str]:
    """Compare current results against saved baseline.

    Returns empty list when current output fully matches baseline.  Each
    returned string describes a specific regression (additions only).
    Removals (shrinkage) are silently auto-recorded by rewriting the
    baseline in-place; if the write fails the function returns a single
    ``"Cannot write baseline: ..."`` message.

    .. note::

        Set-diff on output lines collapses duplicate counts; a count
        increase on the SAME signature is not flagged.  Pylint uses
        ``_pylint_inventory`` to fold counts before set-diff, so pylint
        count changes are detected.

    Args:
        current: :class:`LintResult` list from current run.
        baseline_path: Path to a JSON file previously written by
            :func:`_capture_baseline`.
    """
