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

from .cmd_build import _compose_ruff_config, _expand_globs, _find_py_files
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
    """Discover shipped config files under the installed ``python_setup_lint/config/``.

    Resolves the shipped config directory via
    ``python_setup_lint.__file__.resolve().parent / "config"`` — the same
    pattern ``consultant_mcp._lint_scripts._config_dir()`` uses.  Falls back
    to ``cwd / "config"`` when the installed config dir is missing (editable
    install / source-tree development).  Returns a mapping of canonical tool
    labels to config file paths for every shipped config that actually exists
    on disk.  Returns an empty dict when neither location has config files.

    Pure helper — no side effects, no ``main`` dependency.
    """
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
    """Infer the package name from ``pyproject.toml`` ``[tool.hatch.build.targets.wheel].packages[0]``.

    Strips the leading ``src/`` prefix from the first packages entry.
    Returns ``None`` when the pyproject is missing, unreadable, malformed,
    or has no hatch packages table — callers (stubtest, verifytypes) skip
    gracefully when ``package_name`` is ``None``.

    Pure helper — no side effects, no ``main`` dependency.
    """
    pyproject = cwd / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    try:
        packages: list[str] = data["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]  # type: ignore[index]
    except (KeyError, TypeError):
        return None
    if not packages:
        return None
    raw = packages[0]
    if raw.startswith("src/"):
        return raw[len("src/"):]
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
"""Honoured by :func:`run_lint` before the tool loop; forces ``fix=False``.

The env-var is consulted at the top of :func:`run_lint` and printed to
stderr once when the override activates (so the user sees autofix was
suppressed).  The CLI ``--fix`` arg still parses unchanged — the override
flips the internal flag post-parse.
"""

_E999_RULE: str = "E999"
"""Ruff's ``E999`` (syntax error) is the parseability-canary signal.

A prior tool's fix breaking parseability surfaces as ``E999`` from the
canary pass.  ``_ruff_parseability_errors`` returns the set of file paths
that emitted ``E999`` so :func:`_apply_autofix_conflict_aware` reverts
exactly those files from their in-memory snapshots.
"""

_E999_LINE_RE: re.Pattern[str] = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+):(?P<col>\d+):\s*" + _E999_RULE + r"\b"
)
"""Ruff E999 line parser — tolerant of Windows drive-letter colons in path.

Matches ``path:line:col: E999[ message]`` where ``path`` is greedy so a
``C:\\foo\\bar.py`` prefix is absorbed whole and only the trailing
``:INT:INT: E999`` shape is split off.  ``\\b`` after the rule code prevents
a hypothetical ``E9990`` rule (none ships today) from matching.
"""


def _git_changed_files(cwd: Path, *, staged: bool) -> set[str]:
    """Return paths that differ between index/worktree and HEAD.

    Args:
        cwd: Working directory the lint run is rooted at.
        staged: ``True`` → ``git diff --name-only --cached`` (index vs HEAD);
            ``False`` → ``git diff --name-only`` (worktree vs index).

    Returns:
        Set of repository-relative paths, one per newline-separated line of
        ``git diff`` output.  Empty set on any git failure (non-git cwd,
        uninitialised repo, ``git`` missing) — treated as
        "nothing staged" so autofix applies unconditionally in a non-git
        project.  Logs nothing on the absent-git path; callers handle the
        empty set uniformly.

    Tolerates ``FileNotFoundError`` when ``git`` is not on ``PATH``
    (per envelope: non-git cwd → treat as all-unstaged).
    """
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


def _ruff_parseability_errors(cwd: Path, paths: list[str], run_cmd) -> set[str]:
    """Return paths in *paths* that ruff reports ``E999`` syntax errors on.

    Single extra ``ruff check --no-fix`` invocation (the canary).  Dispatched
    through *run_cmd* — the same package-namespace-resolution callable
    :func:`run_lint` uses for the tool pass — so a test monkey-patching
    ``python_setup_lint.runner._run_cmd`` controls canary behaviour too.
    The label ``"python-setup:autofix-canary"`` distinguishes the canary call
    from the spec's own ruff pass (same ``"ruff check"`` label would collide
    in dict-mode fakes).

    Args:
        cwd: Working directory the lint run is rooted at; ruff is invoked
            here so the file paths are repo-relative as the lint runner
            produces them.
        paths: Repo-relative paths to include in the canary.  Caller filters
            to files the prior fix tool would have touched.
        run_cmd: Callable matching ``_run_cmd(cmd, *, cwd, label) -> LintResult``.
            The canary is invoked with ``cwd=cwd`` and the canary label so
            a single faked ``_run_cmd`` can return E999-marked output for ONLY
            the canary while letting the spec's own pass return its canned
            result.

    Returns:
        Set of paths (relative to *cwd*) that produced ``E999`` output.
        Empty set when *paths* is empty, when ruff is unavailable
        (``FileNotFoundError`` propagated from run_cmd is swallowed), or
        when no ``E999`` line is found in the canary's stdout.
    """
    if not paths:
        return set()
    cmd = ["ruff", "check", "--no-fix", *paths]
    try:
        result = run_cmd(cmd, cwd=cwd, label="python-setup:autofix-canary")
    except FileNotFoundError:
        return set()
    # ``--no-fix`` may still report non-E999 issues; filter to E999 explicitly
    # so a pre-existing F401 line does NOT trigger a revert of an unrelated
    # tool's fix pass.
    #
    # Ruff emits ``path:line:col: RULE_CODE message``.  The path may itself
    # contain ``:`` on Windows drive-letter prefixes (``C:\\foo\\bar.py:5:1:
    # E999 ...``) — a left-most ``split(":", 1)`` would yield ``C`` (garbage).
    # The regex anchors on the trailing ``:LINE:COL: E999`` shape with a
    # greedy path group, so the drive-letter colon is absorbed into the path
    # and only genuine ``file:line:col: E999`` lines match.  Lines that do
    # not match (no E999 rule, or missing line/col) are skipped cleanly — no
    # garbage short-path lands in the result set.
    e999: set[str] = set()
    for line in result.stdout.splitlines():
        m = _E999_LINE_RE.match(line)
        if m is not None:
            e999.add(m.group("path"))
    return e999


def _apply_autofix_conflict_aware(spec, *, config, paths_to_check, run_cmd):
    """Run *spec* in fix mode with conflict-tolerant skip + E999-canary revert.

    Pre-conditions:
    * *spec* is a :class:`ToolSpec` with ``supports_fix=True``.
    * ``paths_to_check`` is the list of repo-relative files the tool's fix
      pass would touch — used (a) to skip staged+unstaged files (the runner
      never applies a fix there), and (b) to compute the in-memory byte
      snapshot for the E999-canary revert.

    Side effects:
    * Runs the tool (via *run_cmd*) with ``fix=True``.
    * Restores any file in *paths_to_check* that the subsequent ruff canary
      reports ``E999`` on — restoring overwrites the post-fix bytes with
      the pre-fix snapshot captured here.
    * Emits one stderr log line per skipped file (``[<tool>] autofix skipped
      for <file>: staged+unstaged conflict``) and per reverted file
      (``[<tool>] autofix reverted <file>: E999 after fix``).  No sensitive
      data; observability only.

    Args:
        spec: The tool to run with ``fix=True``.
        config: :class:`RunnerConfig` — ``config.cwd`` is the git root for
            the staged/unstaged snapshot and the cwd the tool is invoked in.
        paths_to_check: Repo-relative files to skip-check (staged+unstaged)
            and snapshot for revert.  Filtered before invocation to only
            files that exist on disk; both helpers tolerate absent paths.
            Computed by the caller (:func:`run_lint`) via
            :func:`_autofix_target_paths` so the helper is testable in
            isolation.
        run_cmd: Callable matching ``_run_cmd(cmd, *, cwd, label) -> LintResult``
            (resolved by :func:`run_lint` through the package namespace so
            test monkey-patches take effect).  Accepts the strategy-built
            command; ALSO used by the E999-canary (see
            :func:`_ruff_parseability_errors` — the canary call carries the
            ``"python-setup:autofix-canary"`` label so a dict-mode fake can
            return E999-marked output for ONLY the canary).

    Returns:
        The :class:`LintResult` produced by the tool's fix pass.  Reverts
        happen AFTER the result is returned; callers see the post-fix
        ``exit_code`` regardless of revert (the result line still reflects
        that ruff fixed N things; the revert only undoes the file bytes, not
        the tool's own log).
    """
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


def _autofix_target_paths(spec, *, config, path: str | None) -> list[str]:
    """Return the file paths *spec* would touch on a fix pass.

    Mirrors the path-resolution logic in
    :func:`python_setup_lint.runner.cmd_build._build_command` for the
    common-case shape (the three ``supports_fix`` tools — ruff, rumdl, ty —
    all use the generic ``_build_command``, NOT the four tool-specific
    strategies).  The resolved list is used by
    :func:`_apply_autofix_conflict_aware` to (a) skip staged+unstaged
    files and (b) snapshot bytes for the E999-canary revert.

    The expansion goes one step beyond ``_build_command``: directory paths
    (e.g. ruff's ``default_paths=["src/", "tests/"]``) are recursively
    walked to individual ``.py`` files via :func:`_find_py_files`.  This is
    load-bearing because the conflict-skip + bytes-snapshot operate at the
    file level (``git diff --name-only`` returns files, not dirs; a
    directory's ``read_bytes()`` raises ``IsADirectoryError`` which the
    snapshot loop silently drops).  Without the recursive walk, a fresh
    repo where the user only creates ``src/foo.py`` would never have its F401
    skip-check fire — the conflict-aware autofix would silently pass-through
    the unenumerated directory.

    Returns:
        Repo-relative path strings for the individual files the tool would
        touch.  When the spec has no ``default_paths`` and no explicit
        ``--path`` was passed, returns an empty list — the
        conflict-aware autofix helper treats an empty list as "no files to
        skip-check or snapshot", so the tool still runs (it'll target the
        whole repo per its own defaults), and no files are eligible for
        the in-memory revert.  This is a documented conservative behaviour:
        when we cannot enumerate target files, we cannot conflict-skip OR
        revert, but the tool still applies its fix pass.
    """
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
    """Run the full lint pipeline.

    Returns 0 if all tools pass, non-zero on any failure.  See the runner
    package ``__init__`` docstring for the CLI surface.
    """
    if config is None:
        config = RunnerConfig(cwd=Path.cwd())

    # ── T7 — ruff compose + pyright project override ──────────────
    # Apply the two declarative ``RunnerConfig`` override fields before any
    # tool runs so they mutate ``config.config_paths`` exactly once.
    # ``ruff_project_overrides`` composes a temp ``ruff.toml`` extending the
    # shared ``config_paths["ruff check"]`` (port of cm's
    # ``_ruff_config_with_project_overrides``).  ``pyright_project_override``
    # takes precedence over any ``config_paths["pyright check"]`` entry.
    # Both default off → python-setup's own run unchanged.  CLI ``--config``
    # entries (already merged into ``config.config_paths`` by ``main``)
    # still win for non-override tools; ruff's compose source is whatever
    # path currently occupies the ruff slot (typically the shipped config).
    if config.ruff_project_overrides:
        shared_ruff = config.config_paths.get("ruff check")
        if shared_ruff is not None:
            composed = _compose_ruff_config(config.cwd, shared_ruff)
            if composed != shared_ruff:
                # Mutate in place so downstream strategy dispatch reads the
                # composed path without a config-clone hop.
                config.config_paths["ruff check"] = composed
    if config.pyright_project_override is not None:
        config.config_paths["pyright check"] = config.pyright_project_override

    # ── T4 — env-var autofix opt-out ─────────────────────────────
    # ``PYTHON_SETUP_LINT_NO_AUTOFIX=1`` flips ``fix=False`` BEFORE the tool
    # loop so no tool sees ``fix=True`` and no conflict-aware helper runs.
    # Print to stderr ONCE so the user sees the override took effect — no
    # silent skip.  This does NOT change ``--fix`` arg parsing; the override
    # flips the internal flag post-parse so the CLI surface is unchanged.
    if fix and os.environ.get(_AUTOFIX_ENV_VAR) == "1":
        print(
            f"[autofix] {_AUTOFIX_ENV_VAR}=1 set — disabling autofix for this run",
            file=sys.stderr,
        )
        fix = False

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
        if (
            spec.name in ("mypy.stubtest", "pyright verify types")
            and config.package_name is None
        ):
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
        if fix and spec.supports_fix and not statistics:
            # ── T4 — conflict-tolerant autofix path ────────────
            # ``supports_fix=True`` tools run through the conflict-aware
            # helper: snapshot staged/unstaged sets, skip staged+unstaged
            # files, run the fix pass, then run the E999-canary and revert
            # any file the prior fix broke parseability on.  Returns the
            # ``LintResult`` of the fix pass.
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

    # ── T1b — self-discovery fallback ──────────────────────────
    # When neither CLI ``--package-name`` nor caller config supplies
    # ``package_name``, infer from pyproject.toml hatch packages.
    if package_name is None:
        package_name = _infer_package_name(cwd)

    # When no CLI ``--config`` flags were given AND the caller did not
    # supply ``config_paths``, self-discover shipped config files.
    if not args.config and (config is None or not config.config_paths):
        discovered = _default_config_paths(cwd)
        # CLI ``--config`` entries still win over discovered ones, but
        # since we only enter this branch when ``args.config`` is empty,
        # discovered entries are the sole source.
        for k, v in discovered.items():
            if k not in config_paths:
                config_paths[k] = v

    merged_config = RunnerConfig(
        cwd=cwd,
        package_name=package_name,
        default_py_dirs=default_py_dirs,
        tools_override=tools_override,
        config_paths=config_paths,
        secrets_baseline=config.secrets_baseline
        if config is not None
        else ".secrets.baseline",
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
