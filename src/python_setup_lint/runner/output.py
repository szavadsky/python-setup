from __future__ import annotations

import subprocess
import time
from typing import TYPE_CHECKING

import structlog

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

logger = structlog.get_logger(__name__)


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
        except Exception as e:  # parser may fail for any reason; log and continue
            logger.warning("stats parser failed", tool=result.tool_name, exc_info=e)
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


def _run_cmd(
    cmd: list[str],
    *,
    cwd: Path,
    label: str,
    timeout: int = 120,
    memory_limit_mb: int = 2048,
) -> LintResult:
    start = time.monotonic()
    # Inject .venv/bin into PATH so tools installed in the project venv
    # are found even when the parent shell's PATH doesn't include it.
    env = None
    venv_bin = cwd / ".venv" / "bin"
    if venv_bin.is_dir():
        env = {
            **__import__("os").environ,
            "PATH": f"{venv_bin}:{__import__('os').environ.get('PATH', '')}",
        }
    # Memory guard: RLIMIT_AS prevents a single tool from OOMing the system.
    preexec_fn = None
    if memory_limit_mb > 0:
        limit_bytes = memory_limit_mb * 1024 * 1024

        def _set_rlimit() -> None:
            try:
                import resource  # pylint: disable=import-outside-toplevel  # only imported when memory limit is active

                resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
            except ImportError, OSError:  # pylint: disable=W9001,W9740  # non-POSIX or rlimit unavailable; rely on timeout alone
                pass  # non-POSIX or rlimit unavailable; rely on timeout alone

        preexec_fn = _set_rlimit
    try:
        proc = subprocess.run(  # noqa: S603  # cmd is constructed internally from ToolSpec; cwd is lint scope
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout if timeout > 0 else None,
            check=False,
            env=env,
            preexec_fn=preexec_fn,
        )
        elapsed = time.monotonic() - start
        return LintResult(
            tool_name=label,
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            elapsed=elapsed,
        )
    except FileNotFoundError:  # pylint: disable=W9740  # best-effort subprocess fallback; logging would noise unavoidable tool-not-found degrade
        elapsed = time.monotonic() - start
        return LintResult(
            tool_name=label,
            exit_code=127,
            stdout="",
            stderr=f"Tool not found: {cmd[0]}",
            elapsed=elapsed,
        )
    except subprocess.TimeoutExpired:  # pylint: disable=W9740  # timeout: tool exceeded limit; return timeout result so runner continues
        elapsed = time.monotonic() - start
        return LintResult(
            tool_name=label,
            exit_code=124,
            stdout="",
            stderr=f"Command timed out: {cmd}",
            elapsed=elapsed,
        )


def _summarize_pyright_verify_types(stdout: str) -> str | None:
    """Return a concise summary of pyright verify-types output, or None if not parseable.

    Returns:
        A one-line summary string, or None if the output cannot be parsed.
    """
    import json

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:  # pylint: disable=W9740  # best-effort JSON parse fallback; logging would noise unavoidable parse degrade
        return None
    if not isinstance(data, dict):
        return None
    tc = data.get("typeCompleteness")
    if not isinstance(tc, dict):
        return None
    score = tc.get("completenessScore")
    parts = []
    if score is not None:
        parts.append(f"completenessScore={score}")
    return "  pyright verify types: " + ", ".join(parts) if parts else "  pyright verify types: all complete"


def _print_result(result: LintResult) -> None:
    crash = " [CRASH]" if result.exit_code < 0 else ""
    status = "PASSED" if result.exit_code == 0 else f"FAILED (exit={result.exit_code}){crash}"
    print(f"\n{'=' * 60}")
    print(f"[{result.tool_name}] {status} [{result.elapsed:.1f}s]")
    print(f"{'=' * 60}")
    if result.stderr:
        print(result.stderr, end="")
    if result.stdout:
        # For pyright verify types, print a filtered summary instead of the full JSON blob
        if result.tool_name == "pyright verify types":
            summary = _summarize_pyright_verify_types(result.stdout)
            if summary is not None:
                print(summary)
            else:
                print(result.stdout, end="")
        else:
            print(result.stdout, end="")
