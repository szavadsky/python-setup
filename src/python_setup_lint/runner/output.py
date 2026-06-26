"""Statistics aggregation, output formatting, and subprocess execution.

``_aggregate_statistics`` pulls each tool's parser via the strategy
registry (default-aware) and folds counts across results.  Display helpers
print either a flat table, a grouped breakdown (by tool/rule/file), or
machine-readable JSON.  ``_run_cmd`` shells out via
:func:`subprocess.run`; ``_print_result`` renders one tool's result block.

Tests monkey-patch ``python_setup_lint.runner.output._run_cmd`` to inject
synthetic results — :func:`python_setup_lint.runner.cli.run_lint` resolves
the callable through the :mod:`python_setup_lint.runner.output` module at
call time so the patch is honoured.
"""

from __future__ import annotations

import logging
import subprocess
from typing import TYPE_CHECKING
import time

from .dispatch import STRATEGIES
from .parsers import _STATISTICS_PARSERS
from .types import LintResult, ViolationCount

if TYPE_CHECKING:
    from pathlib import Path


__all__ = [
    "_aggregate_statistics",
    "_print_result",
    "_print_statistics_grouped",
    "_print_statistics_table",
    "_run_cmd",
    "_sort_counts",
]

logger = logging.getLogger(__name__)


def _aggregate_statistics(results: list[LintResult]) -> list[ViolationCount]:
    counts: list[ViolationCount] = []
    for result in results:
        # Default-aware dispatch: prefer the strategy registered for this
        # tool name; fall back to the module-level parser table.  The
        # fallback keeps older tool-name consumers (which may not yet have
        # a strategy entry) working without behaviour drift.  Both paths
        # swallow parser exceptions, matching the legacy behaviour.
        try:
            strategy = STRATEGIES.get(result.tool_name)
            if strategy is not None:
                violations = strategy.parse_statistics(result.stdout, result.stderr)
            else:
                parser = _STATISTICS_PARSERS.get(result.tool_name)
                if parser is None:
                    continue
                violations = parser(result.stdout, result.stderr)
        except Exception as e:
            logger.warning("stats parser %s failed: %s", result.tool_name, e)
            continue
        for rule, count in violations:
            counts.append(
                ViolationCount(
                    tool=result.tool_name,
                    rule=rule,
                    count=count,
                )
            )
    counts.sort()
    return counts


def _print_statistics_table(counts: list[ViolationCount]) -> None:
    if not counts:
        print("\nNo violations found.")
        return
    print(f"\n{'=' * 60}")
    print("VIOLATION STATISTICS")
    print(f"{'=' * 60}")
    print(f"{'Tool':<20} {'Rule':<30} {'Count':>6}")
    print("-" * 60)
    for v in counts:
        print(f"{v.tool:<20} {v.rule:<30} {v.count:>6}")


def _sort_counts(
    counts: list[ViolationCount],
    *,
    sort_by_rule: bool = False,
) -> list[ViolationCount]:
    if sort_by_rule:
        return sorted(counts, key=lambda v: (v.rule, v.tool, -v.count))
    return sorted(counts)


def _print_grouped_by_tool(
    counts: list[ViolationCount],
    *,
    sort_by_rule: bool = False,
) -> None:
    sorted_counts = _sort_counts(counts, sort_by_rule=sort_by_rule)
    by_tool: dict[str, list[ViolationCount]] = {}
    for v in sorted_counts:
        by_tool.setdefault(v.tool, []).append(v)

    print(f"\n{'=' * 60}")
    print("VIOLATION STATISTICS (grouped by tool)")
    print(f"{'=' * 60}")
    total = 0
    for tool_name, entries in by_tool.items():
        print(f"\n  [{tool_name}]")
        for v in entries:
            print(f"    {v.rule:<30} {v.count:>6}")
            total += v.count
        print(f"    {'\u2500' * 38}")
        print(f"    {'Subtotal':<30} {sum(e.count for e in entries):>6}")
    print(f"\n{'\u2500' * 60}")
    print(f"{'Total':<30} {total:>6}")


def _print_grouped_by_rule(
    counts: list[ViolationCount],
    *,
    sort_by_rule: bool = False,
) -> None:
    sorted_counts = _sort_counts(counts, sort_by_rule=sort_by_rule)
    by_rule: dict[str, list[ViolationCount]] = {}
    for v in sorted_counts:
        by_rule.setdefault(v.rule, []).append(v)

    print(f"\n{'=' * 60}")
    print("VIOLATION STATISTICS (grouped by rule)")
    print(f"{'=' * 60}")
    total = 0
    for rule, entries in by_rule.items():
        print(f"\n  [{rule}]")
        for v in entries:
            print(f"    {v.tool:<20} {v.count:>6}")
            total += v.count
        print(f"    {'\u2500' * 28}")
        print(f"    {'Subtotal':<20} {sum(e.count for e in entries):>6}")
    print(f"\n{'\u2500' * 60}")
    print(f"{'Total':<30} {total:>6}")


def _print_statistics_grouped(
    counts: list[ViolationCount],
    *,
    group: str = "tool",
    sort_by_rule: bool = False,
) -> None:
    if not counts:
        print("\nNo violations found.")
        return

    if group in ("tool", "file"):
        _print_grouped_by_tool(counts, sort_by_rule=sort_by_rule)
    elif group == "rule":
        _print_grouped_by_rule(counts, sort_by_rule=sort_by_rule)


# ── Subprocess runner ──────────────────────────────────────────────


def _run_cmd(cmd: list[str], *, cwd: Path, label: str) -> LintResult:
    start = time.monotonic()
    proc = subprocess.run(  # noqa: S603  # commands are constructed from internal ToolSpec, not user input
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    elapsed = time.monotonic() - start
    return LintResult(
        tool_name=label,
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        elapsed=elapsed,
    )


def _print_result(result: LintResult) -> None:
    status = "PASSED" if result.exit_code == 0 else f"FAILED (exit={result.exit_code})"
    print(f"\n{'=' * 60}")
    print(f"[{result.tool_name}] {status} [{result.elapsed:.1f}s]")
    print(f"{'=' * 60}")
    if result.stderr:
        print(result.stderr, end="")
    if result.stdout:
        print(result.stdout, end="")
