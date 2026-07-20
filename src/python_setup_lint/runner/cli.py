from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import structlog
from beartype import beartype

from . import output as _output
from ._autofix import (
    _AUTOFIX_ENV_VAR,
    _apply_autofix_conflict_aware,
    _autofix_target_paths,
)
from ._cli_complexity import (
    _apply_config_overrides,
    _build_runner_config,
    _handle_config_status,
    _parse_config_args,
    _select_tools,
)
from ._cli_helpers import _handle_baseline, _print_tool_notes
from .dispatch import (
    _strategy_for,  # type: ignore[attr-defined]  # private symbol removed from .pyi per M3(b); runtime import still works
)
from .extra_tools import (
    _EXTRA_TOOLS_REGISTERED_PATHS,
    _load_extra_tools,
    _register_extra_tools,
)
from .types import LintResult, RunnerConfig, ToolSpec

# Configure structlog at import time to suppress debug/info noise from the runner.
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
)

__all__ = [
    "_apply_autofix_conflict_aware",
    "_autofix_target_paths",
    "main",
    "run_lint",
]


def _run_tool_pipeline(
    selected: list[ToolSpec],
    *,
    config: RunnerConfig,
    fix: bool,
    path: str | None,
    exclude: str | None,
    statistics: bool,
) -> tuple[int, list[LintResult]]:
    results: list[LintResult] = []
    overall_rc = 0
    cwd = config.cwd

    from .output import _print_result, _run_cmd

    # Determinism split (M1): when --fix is active, run a fix-only pass FIRST
    # (fix-capable tools mutate files), then a lint-only pass over ALL tools
    # (fix-capable ones WITHOUT --fix) for violation collection.  This makes
    # every tool — and thus the baseline — observe the same post-fix file
    # state, eliminating the pre-fix-vs-post-fix mismatch that produced
    # non-deterministic baselines.  Without --fix, a single lint pass runs.
    if fix and not statistics:
        # ── Phase 1: fix-only pass (mutates files; results discarded) ──
        for spec in selected:
            if not spec.supports_fix:
                continue
            if spec.name in ("mypy.stubtest", "pyright verify types") and config.package_name is None:
                continue
            _print_tool_notes(spec, fix=True, path=path, exclude=exclude)
            timeouts = config.tool_timeouts or {}
            mem_limits = config.tool_memory_limits or {}
            effective_timeout = timeouts.get(spec.name, spec.timeout)
            effective_mem = mem_limits.get(spec.name, spec.memory_limit_mb)
            file_targets = _autofix_target_paths(spec, config=config, path=path)
            fix_result = _apply_autofix_conflict_aware(
                spec,
                config=config,
                paths_to_check=file_targets,
                run_cmd=__import__("functools").partial(
                    _run_cmd,
                    timeout=effective_timeout,
                    memory_limit_mb=effective_mem,
                ),
            )
            _print_result(fix_result)
        # ── Phase 2: lint-only pass over ALL tools (no autofix) ──
        lint_fix = False
    else:
        lint_fix = fix

    for spec in selected:
        if spec.name in ("mypy.stubtest", "pyright verify types") and config.package_name is None:
            print(f"  [{spec.name}] SKIPPED: --package-name not set", file=sys.stderr)
            continue

        _print_tool_notes(spec, fix=fix, path=path, exclude=exclude)

        timeouts = config.tool_timeouts or {}
        mem_limits = config.tool_memory_limits or {}
        effective_timeout = timeouts.get(spec.name, spec.timeout)
        effective_mem = mem_limits.get(spec.name, spec.memory_limit_mb)

        strategy = _strategy_for(spec.name, spec)
        cmd = strategy.build_command(config=config, _fix=lint_fix, _path=path, _exclude=exclude)
        if statistics:
            cmd.extend(strategy.statistics_flags())
        result = _run_cmd(
            cmd,
            cwd=cwd,
            label=spec.name,
            timeout=effective_timeout,
            memory_limit_mb=effective_mem,
        )
        results.append(result)
        if not statistics:
            _print_result(result)

        if result.exit_code != 0:
            overall_rc = result.exit_code

    return overall_rc, results


def _emit_statistics(
    results: list[LintResult],
    *,
    statistics_format: str,
    group: str,
    sort_by_rule: bool,
) -> None:
    vcounts = _output._aggregate_statistics(results)
    if statistics_format == "json":
        print(
            json.dumps(
                [{"tool": v.tool, "rule": v.rule, "count": v.count} for v in vcounts],
                indent=2,
            )
        )
    elif group != "none":
        _output._print_statistics_grouped(vcounts, group=group, sort_by_rule=sort_by_rule)
    else:
        if sort_by_rule:
            vcounts = _output._sort_counts(vcounts, sort_by_rule=True)
        _output._print_statistics_table(vcounts)


@beartype
def run_lint(
    *,
    config: RunnerConfig | None = None,
    path: str | None = None,
    fix: bool = False,
    baseline: str | None = None,
    exclude: str | None = None,
    statistics: bool = False,
    statistics_format: str = "table",
    overwrite_baseline: bool = False,
    group: str = "none",
    sort_by_rule: bool = False,
) -> int:
    if config is None:
        config = RunnerConfig(cwd=Path.cwd())

    # Apply ruff compose + pyright project overrides.
    config = _apply_config_overrides(config)

    # Env-var autofix opt-out.
    if fix and os.environ.get(_AUTOFIX_ENV_VAR) == "1":
        print(
            f"[autofix] {_AUTOFIX_ENV_VAR}=1 set — disabling autofix for this run",
            file=sys.stderr,
        )
        fix = False

    # Load and register extra tools.
    extras = _load_extra_tools(config.cwd)
    cwd_resolved = config.cwd.resolve()
    if extras and cwd_resolved not in _EXTRA_TOOLS_REGISTERED_PATHS:
        _register_extra_tools(extras)
        _EXTRA_TOOLS_REGISTERED_PATHS.add(cwd_resolved)

    # Resolve which tools to run.
    selected = _select_tools(config)

    overall_rc, results = _run_tool_pipeline(
        selected,
        config=config,
        fix=fix,
        path=path,
        exclude=exclude,
        statistics=statistics,
    )

    if statistics:
        _emit_statistics(
            results,
            statistics_format=statistics_format,
            group=group,
            sort_by_rule=sort_by_rule,
        )

    # Baseline handling.
    if baseline is not None:
        overall_rc = _handle_baseline(
            results,
            baseline,
            overwrite_baseline=overwrite_baseline,
            overall_rc=overall_rc,
            cwd=config.cwd,
        )

    return overall_rc


@beartype
def main(argv: list[str] | None = None, *, config: RunnerConfig | None = None) -> int:
    # Ensure .venv/bin is on PATH so subprocesses find installed tools.
    _venv_bin = Path(__file__).resolve().parent.parent.parent / ".venv" / "bin"
    if _venv_bin.is_dir() and str(_venv_bin) not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{_venv_bin}:{os.environ['PATH']}"

    parser = argparse.ArgumentParser(
        description="Run the python-setup lint pipeline",
    )
    parser.add_argument(
        "--path",
        help="Scope lint to a specific file or directory",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Apply autofixes (ruff, rumdl, ty)",
    )
    parser.add_argument(
        "--baseline",
        metavar="FILE",
        help="Compare against saved baseline (creates if missing)",
    )
    parser.add_argument(
        "--exclude",
        help="Exclude a file or directory pattern",
    )
    parser.add_argument(
        "--overwrite-baseline",
        action="store_true",
        help="Force overwrite of existing baseline file (used with --baseline)",
    )
    parser.add_argument(
        "--statistics",
        action="store_true",
        help="Display per-rule violation counts aggregated across all tools",
    )
    parser.add_argument(
        "--format",
        choices=("table", "json"),
        default="table",
        help="Output format for --statistics (default: table)",
    )
    parser.add_argument(
        "--group",
        choices=("none", "rule", "tool", "file"),
        default="none",
        help="Group statistics output by tool, rule, or file (default: none)",
    )
    parser.add_argument(
        "--sort-by-rule",
        action="store_true",
        help="Sort statistics output by rule name instead of count",
    )
    parser.add_argument(
        "--package-name",
        metavar="PKG",
        help="Package name for mypy.stubtest + pyright verifytypes",
    )
    parser.add_argument(
        "--cwd",
        metavar="DIR",
        default=None,
        help="Working directory (default: current dir)",
    )
    parser.add_argument(
        "--tools",
        metavar="LIST",
        help="Comma-separated tool names to run (default: all 13 tools)",
    )
    parser.add_argument(
        "--default-py-dirs",
        metavar="DIRS",
        default="src",
        help="Default dirs for pylint file discovery (default: src)",
    )
    parser.add_argument(
        "--config",
        metavar="TOOL=PATH",
        action="append",
        default=[],
        help="Override config file for a tool (ruff, mypy, pylint, pyright, rumdl, ty). May be given multiple times.",
    )
    parser.add_argument(
        "--config-status",
        action="store_true",
        help="Print per-tool config origin and exit (do not run tools)",
    )
    args = parser.parse_args(argv)

    # Start from caller-supplied defaults, allow CLI overrides.
    cwd = Path(args.cwd) if args.cwd else (config.cwd if config is not None else Path.cwd())
    cli_tools_override = args.tools.split(",") if args.tools else None

    if cli_tools_override is not None:
        if not cli_tools_override:
            parser.error("--tools: empty tool list")
        for raw_name in cli_tools_override:
            if not raw_name.strip():
                parser.error(f"--tools: empty name in {args.tools!r}")

    config_paths = _parse_config_args(args, parser, base_config=config)

    # ── T6-F4 — --config-status early return ─────────────────────
    status_rc = _handle_config_status(args, config, cwd, config_paths)
    if status_rc is not None:
        return status_rc

    merged_config = _build_runner_config(
        args,
        base_config=config,
        cwd=cwd,
        config_paths=config_paths,
        cli_tools_override=cli_tools_override,
    )

    return run_lint(
        config=merged_config,
        path=args.path,
        fix=args.fix,
        baseline=args.baseline,
        exclude=args.exclude,
        overwrite_baseline=args.overwrite_baseline,
        statistics=args.statistics,
        statistics_format=args.format,
        group=args.group,
        sort_by_rule=args.sort_by_rule,
    )


if __name__ == "__main__":
    sys.exit(main())
