"""Stub for :mod:`python_setup_lint.runner.output`.

Statistics aggregation, table/grouped/JSON display, subprocess execution,
and per-tool result printing.
"""

from pathlib import Path

from .types import LintResult, ViolationCount

def _aggregate_statistics(results: list[LintResult]) -> list[ViolationCount]:
    """Aggregate violation counts per tool per rule from all tool results.

    Returns a list sorted by count descending, then tool, then rule.  Only
    tools with a registered parser (via
    :data:`python_setup_lint.runner.dispatch.STRATEGIES` or
    :data:`python_setup_lint.runner.parsers._STATISTICS_PARSERS`) are
    included; parser exceptions are swallowed with a warning.
    """

def _print_statistics_table(counts: list[ViolationCount]) -> None:
    """Print violation counts as an aligned human-readable table.

    Prints ``"No violations found."`` when *counts* is empty.
    """

def _sort_counts(
    counts: list[ViolationCount],
    *,
    sort_by_rule: bool = False,
) -> list[ViolationCount]:
    """Return *counts* in the requested sort order.

    Default sort (``sort_by_rule=False``): count descending, then tool,
    then rule.  ``sort_by_rule=True``: rule ascending, then tool, then
    count descending.
    """

def _print_statistics_grouped(
    counts: list[ViolationCount],
    *,
    group: str = "tool",
    sort_by_rule: bool = False,
) -> None:
    """Print violation counts grouped by *group* key.

    * ``"tool"`` — section per tool.
    * ``"rule"`` — section per rule, showing per-tool counts.
    * ``"file"`` — same layout as ``"tool"`` (no per-file data in statistics).
    """

def _run_cmd(cmd: list[str], *, cwd: Path, label: str) -> LintResult:
    """Run a single command via :func:`subprocess.run` and return its result.

    600-second timeout; ``check=False`` so a non-zero exit is returned in
    :attr:`LintResult.exit_code` rather than raised.  Tests inject
    synthetic results by monkey-patching ``python_setup_lint.runner._run_cmd``
    (re-exported from this module via the runner package ``__init__``);
    :func:`python_setup_lint.runner.cli.run_lint` resolves the callable
    through the package namespace at call time so the patch is honoured.
    """

def _print_result(result: LintResult) -> None:
    """Print a formatted result block (status + stderr + stdout) to stdout."""
