"""Lint pipeline orchestration + CLI entry point.

``run_lint`` iterates the live tool registry, resolves a strategy per tool,
builds the command, runs it via :func:`python_setup_lint.runner.output._run_cmd`,
and aggregates results into either per-tool output, a statistics table/grouping,
or a baseline diff.  ``main`` is the console-script entry point used by
``uv run lint`` and the ``python_setup_lint.runner:main`` entry in
``pyproject.toml``.

Monkeypatch contract: tests inject synthetic results by patching
``python_setup_lint.runner._run_cmd`` (string form or via
``monkeypatch.setattr(_runner_module, "_run_cmd", fake)``).  Both patterns
target the package-level re-export of :func:`output._run_cmd` in
:mod:`python_setup_lint.runner`'s ``__init__``; ``run_lint`` resolves the
callable through the package namespace at call time so the patch is honoured
without a test-fixture rewrite.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .dispatch import LINT_TOOLS, _strategy_for
from .extra_tools import (
    _EXTRA_TOOLS_REGISTERED_PATHS,
    ExtraToolsConfigError,
    _load_extra_tools,
    _register_extra_tools,
)
from .types import LintResult, RunnerConfig, ToolSpec

# ── CLI config-key aliases (T8 fail-fast) ───────────────────────────
# Canonical ``--config TOOL=PATH`` labels + short aliases (``ruff`` →
# ``ruff check``).  Unknown ids exit non-zero via argparse ``parser.error``
# — no silent drop where a typo produced an entry :func:`_config_flag_for`
# never read.
_CONFIG_KEY_ALIASES: dict[str, str] = {
    "ruff": "ruff check",
    "pyright": "pyright check",
    "rumdl": "rumdl check",
    "ty": "ty check",
    "mypy": "mypy",
    "pylint": "pylint",
}
_SUPPORTED_CONFIG_KEYS: frozenset[str] = frozenset(set(_CONFIG_KEY_ALIASES) | set(_CONFIG_KEY_ALIASES.values()))

__all__ = ["_CONFIG_KEY_ALIASES", "_SUPPORTED_CONFIG_KEYS", "main", "run_lint"]


def run_lint(
    *,
    config: RunnerConfig | None = None,
    path: str | None = None,
    fix: bool = False,
    baseline: str | None = None,
    exclude: str | None = None,
    no_fail_fast: bool = False,
    statistics: bool = False,
    statistics_format: str = "table",
    overwrite_baseline: bool = False,
    group: str = "none",
    sort_by_rule: bool = False,
) -> int:
    """Run the full lint pipeline.

    Returns 0 if all tools pass, non-zero on any failure.  See the runner
    package ``__init__`` docstring for the CLI surface.
    """
    if config is None:
        config = RunnerConfig(cwd=Path.cwd())

    # ── Extras merge (T11 v1) ─────────────────────────────────────
    # Load + validate ``[[tool.python-setup-lint.extra-tools]]`` from the
    # project's ``pyproject.toml`` and register each entry as a live
    # :class:`ToolSpec` via :func:`register_lint_tool`.  Idempotent per
    # ``tool.name`` so a re-invocation in the same process is a no-op.
    # ``ExtraToolsConfigError`` is NOT caught here — it propagates uncaught
    # to the caller (T8 R4: per-entry validation errors surface as a
    # traceback + non-zero exit, not silent fallback).
    extras = _load_extra_tools(config.cwd)
    cwd_resolved = config.cwd.resolve()
    if extras and cwd_resolved not in _EXTRA_TOOLS_REGISTERED_PATHS:
        _register_extra_tools(extras)
        _EXTRA_TOOLS_REGISTERED_PATHS.add(cwd_resolved)

    # Resolve which tools to run.  ``tools_override=None`` → iterate the
    # live registry (:data:`LINT_TOOLS`); with a list, each name MUST resolve
    # against the live registry — an unknown name raises
    # :class:`ExtraToolsConfigError` (T8 fail-fast, location
    # ``<RunnerConfig.tools_override>``) rather than silently running a subset.
    selected: list[ToolSpec] = []
    if config.tools_override is not None:
        lint_tools_by_name = {t.name: t for t in LINT_TOOLS}
        for raw_name in config.tools_override:
            name = raw_name.strip()
            spec = lint_tools_by_name.get(name)
            if spec is None:
                raise ExtraToolsConfigError(
                    "<RunnerConfig.tools_override>",
                    f"unknown tool name: {name!r}; known: {sorted(lint_tools_by_name)}",
                )
            selected.append(spec)
    else:
        selected = list(LINT_TOOLS)

    results: list[LintResult] = []
    overall_rc = 0
    cwd = config.cwd

    # Resolve the subprocess + display helpers through the package namespace
    # at call time so tests that monkey-patch ``python_setup_lint.runner._run_cmd``
    # (string or ``setattr(_runner_module, "_run_cmd", ...)``) take effect.
    # Both patch forms target the re-export in
    # :mod:`python_setup_lint.runner`'s ``__init__``; an early ``from .output
    # import _run_cmd`` would bind the unpatched callable and miss the patch.
    from python_setup_lint import runner as _pkg

    for spec in selected:
        # Skip tools that require package_name when none configured.
        # Per DESIGN-0 D14: this skip stays in run_lint (NOT inside
        # strategies) so strategies stay config-agnostic.
        if spec.name in ("mypy.stubtest", "pyright verify types") and config.package_name is None:
            print(f"  [{spec.name}] SKIPPED: --package-name not set", file=sys.stderr)
            continue

        # Report unsupported flags before running — use stderr so --statistics --format json is not polluted
        if fix and not spec.supports_fix:
            print(
                f"  [{spec.name}] --fix: N/A (tool does not support autofix)",
                file=sys.stderr,
            )
        if path is not None and not spec.supports_path:
            print(
                f"  [{spec.name}] --path: N/A (tool does not support path scoping)",
                file=sys.stderr,
            )
        if exclude is not None and not spec.supports_exclude:
            print(
                f"  [{spec.name}] --exclude: N/A (tool does not support exclude)",
                file=sys.stderr,
            )

        # Default-aware dispatch — unknown names synthesise a GenericLintTool.
        strategy = _strategy_for(spec.name, spec)
        cmd = strategy.build_command(config=config, fix=fix, path=path, exclude=exclude)
        if statistics:
            cmd.extend(strategy.statistics_flags())
        result = _pkg._run_cmd(cmd, cwd=cwd, label=spec.name)
        results.append(result)
        if not statistics:
            _pkg._print_result(result)

        if result.exit_code != 0:
            overall_rc = result.exit_code
            if not no_fail_fast:
                break

    # ── Statistics output ──────────────────────────────────────
    if statistics:
        vcounts = _pkg._aggregate_statistics(results)
        if statistics_format == "json":
            print(
                json.dumps(
                    [{"tool": v.tool, "rule": v.rule, "count": v.count} for v in vcounts],
                    indent=2,
                )
            )
        elif group != "none":
            _pkg._print_statistics_grouped(vcounts, group=group, sort_by_rule=sort_by_rule)
        else:
            if sort_by_rule:
                vcounts = _pkg._sort_counts(vcounts, sort_by_rule=True)
            _pkg._print_statistics_table(vcounts)

    # ── Baseline handling ──────────────────────────────────────
    if baseline is not None:
        base_path = Path(baseline)
        if base_path.exists() and not overwrite_baseline:
            new_issues = _pkg._diff_baseline(results, base_path)
            if new_issues:
                print(f"\n{'=' * 60}")
                print("[baseline] New violations detected:")
                for issue in new_issues:
                    print(f"  \u2022 {issue}")
                if overall_rc == 0:
                    overall_rc = 1
            else:
                print(f"\n{'=' * 60}")
                print("[baseline] No new violations — output matches baseline")
                overall_rc = 0
        else:
            action = "Overwriting" if base_path.exists() else "Creating"
            print(f"\n{'=' * 60}")
            print(f"[baseline] {action} baseline \u2192 {baseline}")
            base_data = _pkg._capture_baseline(results)
            base_path.parent.mkdir(parents=True, exist_ok=True)
            with open(base_path, "w") as f:
                json.dump(base_data, f, indent=2, sort_keys=True)
            print(f"[baseline] Baseline saved ({len(base_data)} tool entries)")
            overall_rc = 0

    return overall_rc


def main(argv: list[str] | None = None, *, config: RunnerConfig | None = None) -> int:
    """CLI entry point for ``uv run lint``.

    When *config* is provided, CLI flags still override the pre-built
    configuration (cwd, package-name, default-py-dirs, tools, config-paths
    can all be set on the command line).  This lets thin wrappers construct a
    default configuration while still exposing the full CLI surface.
    """
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
        "--no-fail-fast",
        action="store_true",
        help="Run all tools, accumulate failures",
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
        help="Comma-separated tool names to run (default: all 11 tools)",
    )
    parser.add_argument(
        "--default-py-dirs",
        metavar="DIRS",
        default="src,scripts,tests",
        help="Default dirs for pylint file discovery (default: src,scripts,tests)",
    )
    parser.add_argument(
        "--config",
        metavar="TOOL=PATH",
        action="append",
        default=[],
        help="Override config file for a tool (ruff, mypy, pylint, pyright, rumdl, ty). May be given multiple times.",
    )
    args = parser.parse_args(argv)

    # Start from caller-supplied defaults, allow CLI overrides.
    cwd = Path(args.cwd) if args.cwd else (config.cwd if config is not None else Path.cwd())
    cli_tools_override = args.tools.split(",") if args.tools else None
    base_tools_override = (
        cli_tools_override if cli_tools_override is not None else (config.tools_override if config is not None else None)
    )
    tools_override: list[str] | None = base_tools_override
    package_name = args.package_name if args.package_name is not None else (config.package_name if config is not None else None)
    default_py_dirs = (
        args.default_py_dirs.split(",") if args.default_py_dirs else (config.default_py_dirs if config is not None else None)
    )
    config_paths: dict[str, Path] = dict(config.config_paths) if config is not None else {}
    for raw in args.config:
        if "=" not in raw:
            parser.error(f"--config must be TOOL=PATH, got: {raw!r}")
        tool_id, path_str = raw.split("=", 1)
        # T8 fail-fast: validate tool_id against the closed config-key set.
        # Previously a typo silently produced an entry :func:`_config_flag_for`
        # never read; now exits ``SystemExit(2)`` naming the offending key.
        if tool_id not in _SUPPORTED_CONFIG_KEYS:
            parser.error(
                f"--config: unknown tool id {tool_id!r}; "
                f"supported (canonical labels + short aliases): "
                f"{sorted(_SUPPORTED_CONFIG_KEYS)}"
            )
        # Normalise short alias → canonical label.  ``args.config`` is
        # ``Namespace[Any]`` so ``tool_id`` is ``Any``; ``or tool_id`` coalesces
        # the widened ``dict.get(Any, Any) -> str | None`` to ``str``.
        canonical = _CONFIG_KEY_ALIASES.get(tool_id) or tool_id
        config_paths[canonical] = Path(path_str)

    # T8 fail-fast: ``--tools`` syntax (empty pieces, blank list) exits
    # ``SystemExit(2)`` here.  Unknown-but-non-empty names are deferred to
    # ``run_lint`` — the valid-name set is open (extras come from pyproject).
    if cli_tools_override is not None:
        if not cli_tools_override:
            parser.error("--tools: empty tool list")
        for raw_name in cli_tools_override:
            if not raw_name.strip():
                parser.error(f"--tools: empty name in {args.tools!r}")

    merged_config = RunnerConfig(
        cwd=cwd,
        package_name=package_name,
        default_py_dirs=default_py_dirs,
        tools_override=tools_override,
        config_paths=config_paths,
        secrets_baseline=config.secrets_baseline if config is not None else ".secrets.baseline",
    )

    return run_lint(
        config=merged_config,
        path=args.path,
        fix=args.fix,
        baseline=args.baseline,
        exclude=args.exclude,
        no_fail_fast=args.no_fail_fast,
        overwrite_baseline=args.overwrite_baseline,
        statistics=args.statistics,
        statistics_format=args.format,
        group=args.group,
        sort_by_rule=args.sort_by_rule,
    )


if __name__ == "__main__":
    sys.exit(main())
