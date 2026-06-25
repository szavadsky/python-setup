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

T4 — autofix is courtesy, never blocks:
* ``--fix`` runs autofix across all ``supports_fix=True`` tools, then runs the
  per-file E999-canary (``ruff check --no-fix``); a parseability break introduced
  by a prior tool's fix triggers an in-memory byte-snapshot revert with a stderr
  log line.
* Files with BOTH staged AND unstaged changes skip autofix entirely (stderr
  log line each) — applying an autofix to such a file would conflict with the
  staged blob (pre-commit owns staging, the runner never ``git add``s).
* ``PYTHON_SETUP_LINT_NO_AUTOFIX=1`` env-var forces ``fix=False`` internally so
  callers can opt out of autofix without arg plumbing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import beartype

from .cmd_build import (
    _compose_pyright_config,
    _compose_ruff_config,
    _expand_globs,
    _find_py_files,
    _resolve_pylintrc,
)
from .dispatch import LINT_TOOLS, _strategy_for
from .extra_tools import (
    _EXTRA_TOOLS_REGISTERED_PATHS,
    ExtraToolsConfigError,
    _load_extra_tools,
    _register_extra_tools,
)
from .types import LintResult, RunnerConfig, ToolSpec

# ── T1b — self-discovery helpers ──────────────────────────────────
# Pure helpers that resolve shipped config paths and infer package_name
# from pyproject.toml.  Both are callable from tests without invoking
# ``main`` or ``run_lint``.

# Shipped config files that live under ``python_setup_lint/config/``.
# Each key is the canonical tool label used in ``_config_flag_for``.
_SHIPPED_CONFIG_FILES: dict[str, str] = {
    "ruff check": "ruff.toml",
    "mypy": "mypy.ini",
    "pylint": ".pylintrc",
    "pyright check": "pyrightconfig.json",
    "rumdl check": "rumdl.toml",
    "ty check": "ty.toml",
    "yamllint": ".yamllint",
}


def _default_config_paths(cwd: Path) -> dict[str, Path]:
    import python_setup_lint

    candidates: list[Path] = []
    pkg_file = python_setup_lint.__file__
    if pkg_file is not None:
        installed = Path(pkg_file).resolve().parent / "config"
        if installed.is_dir():
            candidates.append(installed)
    # Fallback: source-tree config/ (editable install / development).
    source = cwd / "config"
    if source.is_dir() and source not in candidates:
        candidates.append(source)
    if not candidates:
        return {}
    result: dict[str, Path] = {}
    for tool_label, filename in _SHIPPED_CONFIG_FILES.items():
        for config_dir in candidates:
            candidate = config_dir / filename
            if candidate.is_file():
                result[tool_label] = candidate
                break
    return result


def _infer_package_name(cwd: Path) -> str | None:
    pyproject = cwd / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
    except OSError, tomllib.TOMLDecodeError:
        return None
    try:
        packages: list[str] = data["tool"]["hatch"]["build"]["targets"]["wheel"][
            "packages"
        ]  # type: ignore[index]
    except KeyError, TypeError:
        return None
    if not packages:
        return None
    raw = packages[0]
    if raw.startswith("src/"):
        return raw[len("src/") :]
    return raw


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
_SUPPORTED_CONFIG_KEYS: frozenset[str] = frozenset(
    set(_CONFIG_KEY_ALIASES) | set(_CONFIG_KEY_ALIASES.values())
)

__all__ = [
    "_CONFIG_KEY_ALIASES",
    "_SUPPORTED_CONFIG_KEYS",
    "_apply_autofix_conflict_aware",
    "_autofix_target_paths",
    "_git_changed_files",
    "_ruff_parseability_errors",
    "main",
    "run_lint",
]


# ── T4 — conflict-tolerant autofix helpers ──────────────────────
#
# Autofix is courtesy, never blocks:
#   * env-var opt-out: ``PYTHON_SETUP_LINT_NO_AUTOFIX=1`` forces ``fix=False``
#     inside :func:`run_lint` so the route is honoured without touching CLI
#     plumbing.
#   * staged+unstaged skip: ``git diff --name-only --cached`` (staged) and
#     ``git diff --name-only`` (unstaged) snapshot once per run.  A file in
#     BOTH sets skips autofix entirely — applying a fix there would conflict
#     with the pre-commit-owned staged blob.
#   * E999-canary revert: after each ``supports_fix`` tool's fix pass, a single
#     ``ruff check --no-fix`` parseability canary runs over the files the tool
#     would have touched; a returned ``E999`` (syntax error) is treated as the
#     tool's fix breaking parseability, and the file is reverted from the
#     in-memory byte snapshot captured BEFORE the fix pass (avoids
#     ``git checkout`` for untracked files — tracked-file restoration is the
#     memory-lost fallback, never reached in tests).
#
# All helpers take explicit ``Path`` arguments (no module-level globals) so
# tests can drive each branch with synthetic ``tmp_path`` git state + a
# monkey-patched ``_run_cmd``.  The runners NEVER ``git add`` — pre-commit
# owns staging.

_AUTOFIX_ENV_VAR: str = "PYTHON_SETUP_LINT_NO_AUTOFIX"
_E999_RULE: str = "E999"
_E999_LINE_RE: re.Pattern[str] = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+):(?P<col>\d+):\s*" + _E999_RULE + r"\b"
)


def _git_changed_files(cwd: Path, *, staged: bool) -> set[str]:
    cmd = (
        ["git", "diff", "--name-only", "--cached"]
        if staged
        else ["git", "diff", "--name-only"]
    )
    try:
        proc = subprocess.run(  # noqa: S603  # argv is constructed internally; cwd is lint scope
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except FileNotFoundError, subprocess.TimeoutExpired:
        return set()
    if proc.returncode != 0:
        return set()
    return {line for line in proc.stdout.splitlines() if line.strip()}


@beartype.beartype
def _ruff_parseability_errors(cwd: Path, paths: list[str], run_cmd: object) -> set[str]:
    if not paths:
        return set()
    cmd = ["ruff", "check", "--no-fix", *paths]
    try:
        result = run_cmd(cmd, cwd=cwd, label="python-setup:autofix-canary")
    except FileNotFoundError:
        return set()
    e999: set[str] = set()
    for line in result.stdout.splitlines():
        m = _E999_LINE_RE.match(line)
        if m is not None:
            e999.add(m.group("path"))
    return e999


@beartype.beartype
def _apply_autofix_conflict_aware(
    spec: ToolSpec,
    *,
    config: RunnerConfig,
    paths_to_check: list[str],
    run_cmd: object,
) -> LintResult:
    staged_set = _git_changed_files(config.cwd, staged=True)
    unstaged_set = _git_changed_files(config.cwd, staged=False)
    # Skip files that would conflict with the staged blob if autofixed.
    conflict_files = staged_set & unstaged_set & set(paths_to_check)
    safe_to_fix = [p for p in paths_to_check if p not in conflict_files]
    for p in sorted(conflict_files):
        print(
            f"  [{spec.name}] autofix skipped for {p}: staged+unstaged conflict",
            file=sys.stderr,
        )

    # Snapshot bytes BEFORE the fix pass — used by the E999-canary revert.
    # Tolerant: a path in ``paths_to_check`` may not exist on disk (e.g. a
    # glob the strategy resolved to no files); skip missing files silently
    # — the snapshot dict simply omits them, so the canary cannot revert
    # them either.
    snapshot: dict[Path, bytes] = {}
    for rel in safe_to_fix:
        candidate = config.cwd / rel
        try:
            snapshot[candidate] = candidate.read_bytes()
        except FileNotFoundError, IsADirectoryError:
            continue

    strategy = _strategy_for(spec.name, spec)
    cmd = strategy.build_command(config=config, fix=True)
    result = run_cmd(cmd, cwd=config.cwd, label=spec.name)

    # E999 canary — revert any file the fix tool broke parseability on.
    # Only files captured in the snapshot are revertible (avoids ``git
    # checkout`` for untracked — the envelope's memory-first contract).
    canary_targets = [str(p.relative_to(config.cwd)) for p in snapshot]
    e999_files = _ruff_parseability_errors(config.cwd, canary_targets, run_cmd)
    for rel in sorted(e999_files):
        target = config.cwd / rel
        prior_bytes = snapshot.get(target)
        if prior_bytes is not None:
            target.write_bytes(prior_bytes)
            print(
                f"  [{spec.name}] autofix reverted {rel}: E999 after fix",
                file=sys.stderr,
            )
    return result


def _autofix_target_paths(
    spec: ToolSpec, *, config: RunnerConfig, path: str | None
) -> list[str]:
    if path is not None and spec.supports_path:
        paths = [path]
    elif spec.default_paths:
        paths = list(spec.default_paths)
    else:
        return []
    # Two-stage: expand shell globs (``config/*.py``), then walk any
    # remaining directory entries into individual file paths so the
    # conflict-skip + snapshot operate on actual files.
    paths = _expand_globs(paths, cwd=config.cwd)
    return _find_py_files(paths, cwd=config.cwd)


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
    if config is None:
        config = RunnerConfig(cwd=Path.cwd())

    # ── T7 — ruff compose + pyright project override ──────────────
    # Apply the two declarative ``RunnerConfig`` override fields before any
    # tool runs so they mutate ``config.config_paths`` exactly once.
    if config.ruff_project_overrides:
        shared_ruff = config.config_paths.get("ruff check")
        if shared_ruff is not None:
            composed = _compose_ruff_config(config.cwd, shared_ruff)
            if composed != shared_ruff:
                config.config_paths["ruff check"] = composed
    if config.pyright_project_override is not None:
        config.config_paths["pyright check"] = config.pyright_project_override
    elif (
        config.config_paths is not None
        and config.config_paths.get("pyright check") is not None
    ):
        paths = config.config_paths
        shared_pyright = paths["pyright check"]
        composed_pyright = _compose_pyright_config(config.cwd, shared_pyright)
        if composed_pyright != shared_pyright:
            paths["pyright check"] = composed_pyright

    # ── T4 — env-var autofix opt-out ─────────────────────────────
    if fix and os.environ.get(_AUTOFIX_ENV_VAR) == "1":
        print(
            f"[autofix] {_AUTOFIX_ENV_VAR}=1 set — disabling autofix for this run",
            file=sys.stderr,
        )
        fix = False

    # ── Extras merge (T11 v1) ─────────────────────────────────────
    extras = _load_extra_tools(config.cwd)
    cwd_resolved = config.cwd.resolve()
    if extras and cwd_resolved not in _EXTRA_TOOLS_REGISTERED_PATHS:
        _register_extra_tools(extras)
        _EXTRA_TOOLS_REGISTERED_PATHS.add(cwd_resolved)

    # Resolve which tools to run.
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

    from python_setup_lint import runner as _pkg

    for spec in selected:
        if (
            spec.name in ("mypy.stubtest", "pyright verify types")
            and config.package_name is None
        ):
            print(f"  [{spec.name}] SKIPPED: --package-name not set", file=sys.stderr)
            continue

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

        strategy = _strategy_for(spec.name, spec)
        if fix and spec.supports_fix and not statistics:
            file_targets = _autofix_target_paths(spec, config=config, path=path)
            result = _apply_autofix_conflict_aware(
                spec,
                config=config,
                paths_to_check=file_targets,
                run_cmd=_pkg._run_cmd,
            )
        else:
            cmd = strategy.build_command(
                config=config, fix=fix, path=path, exclude=exclude
            )
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
                    [
                        {"tool": v.tool, "rule": v.rule, "count": v.count}
                        for v in vcounts
                    ],
                    indent=2,
                )
            )
        elif group != "none":
            _pkg._print_statistics_grouped(
                vcounts, group=group, sort_by_rule=sort_by_rule
            )
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


def _print_config_status(
    *,
    config_paths: dict[str, Path],
    cli_overridden: frozenset[str],
    caller_config_paths: dict[str, Path],
    shipped_paths: dict[str, Path],
    cwd: Path,
    ruff_composed: bool,
) -> None:
    import importlib.metadata

    try:
        version = importlib.metadata.version("python-setup")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"

    from .dispatch import LINT_TOOLS

    for spec in LINT_TOOLS:
        name = spec.name
        config_path = config_paths.get(name)

        if config_path is None:
            if name == "pylint":
                rcfile = _resolve_pylintrc(config_paths, cwd)
                if rcfile is not None:
                    print(f"  {name:<20} {rcfile}  (auto-discovered, project-local)")
                else:
                    print(f"  {name:<20}  (not configured)")
            else:
                print(f"  {name:<20}  (not configured)")
            continue

        if name in cli_overridden:
            origin = "overridden via --config"
        elif name in caller_config_paths:
            origin = "overridden (RunnerConfig)"
        elif (
            name in shipped_paths
            and config_path.resolve() == shipped_paths[name].resolve()
        ):
            origin = f"shipped, from python-setup v{version}"
        elif ruff_composed and name == "ruff check":
            origin = "generated (composed)"
        else:
            origin = "auto-discovered"

        print(f"  {name:<20} {config_path}  ({origin})")


def main(argv: list[str] | None = None, *, config: RunnerConfig | None = None) -> int:
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
    parser.add_argument(
        "--config-status",
        action="store_true",
        help="Print per-tool config origin and exit (do not run tools)",
    )
    args = parser.parse_args(argv)

    # Start from caller-supplied defaults, allow CLI overrides.
    cwd = (
        Path(args.cwd)
        if args.cwd
        else (config.cwd if config is not None else Path.cwd())
    )
    cli_tools_override = args.tools.split(",") if args.tools else None
    base_tools_override = (
        cli_tools_override
        if cli_tools_override is not None
        else (config.tools_override if config is not None else None)
    )
    tools_override: list[str] | None = base_tools_override
    package_name = (
        args.package_name
        if args.package_name is not None
        else (config.package_name if config is not None else None)
    )
    default_py_dirs = (
        args.default_py_dirs.split(",")
        if args.default_py_dirs
        else (config.default_py_dirs if config is not None else None)
    )
    config_paths: dict[str, Path] = (
        dict(config.config_paths) if config is not None else {}
    )
    for raw in args.config:
        if "=" not in raw:
            parser.error(f"--config must be TOOL=PATH, got: {raw!r}")
        tool_id, path_str = raw.split("=", 1)
        if tool_id not in _SUPPORTED_CONFIG_KEYS:
            parser.error(
                f"--config: unknown tool id {tool_id!r}; "
                f"supported (canonical labels + short aliases): "
                f"{sorted(_SUPPORTED_CONFIG_KEYS)}"
            )
        canonical = _CONFIG_KEY_ALIASES.get(tool_id) or tool_id
        config_paths[canonical] = Path(path_str)

    if cli_tools_override is not None:
        if not cli_tools_override:
            parser.error("--tools: empty tool list")
        for raw_name in cli_tools_override:
            if not raw_name.strip():
                parser.error(f"--tools: empty name in {args.tools!r}")

    # ── T1b — self-discovery fallback ──────────────────────────
    if package_name is None:
        package_name = _infer_package_name(cwd)

    if not args.config and (config is None or not config.config_paths):
        discovered = _default_config_paths(cwd)
        for k, v in discovered.items():
            if k not in config_paths:
                config_paths[k] = v

    # ── T6-F4 — --config-status early return ─────────────────────
    if args.config_status:
        cli_overridden: set[str] = set()
        for raw in args.config:
            if "=" not in raw:
                continue
            tool_id = raw.split("=", 1)[0]
            canonical = _CONFIG_KEY_ALIASES.get(tool_id) or tool_id
            cli_overridden.add(canonical)
        caller_config_paths: dict[str, Path] = (
            dict(config.config_paths) if config is not None else {}
        )
        shipped_paths = _default_config_paths(cwd)
        ruff_composed = (
            config is not None and config.ruff_project_overrides
        ) and "ruff check" in shipped_paths
        _print_config_status(
            config_paths=config_paths,
            cli_overridden=frozenset(cli_overridden),
            caller_config_paths=caller_config_paths,
            shipped_paths=shipped_paths,
            cwd=cwd,
            ruff_composed=ruff_composed,
        )
        return 0

    merged_config = RunnerConfig(
        cwd=cwd,
        package_name=package_name,
        default_py_dirs=default_py_dirs,
        tools_override=tools_override,
        config_paths=config_paths,
        secrets_baseline=config.secrets_baseline
        if config is not None
        else ".secrets.baseline",
        ruff_project_overrides=config.ruff_project_overrides
        if config is not None
        else False,
        pyright_project_override=config.pyright_project_override
        if config is not None
        else None,
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
