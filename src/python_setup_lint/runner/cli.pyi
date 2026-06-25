"""Stub for :mod:`python_setup_lint.runner.cli`.

Lint pipeline orchestration (``run_lint``) + CLI entry point (``main``).
Includes the T8 fail-fast CLI ``--config`` key set + aliases.

T4 — conflict-tolerant autofix surface:

* :data:`_AUTOFIX_ENV_VAR` — env-var name (``PYTHON_SETUP_LINT_NO_AUTOFIX``)
  honoured by :func:`run_lint` to disable autofix for a single run.
* :func:`_git_changed_files` — staged/unstaged path probe via
  ``git diff --name-only``.  Tolerates non-git cwd (returns empty).
* :func:`_ruff_parseability_errors` — single ``ruff check --no-fix`` invocation
  that returns the set of files with ``E999`` syntax errors.  The label
  ``"python-setup:autofix-canary"`` distinguishes canary calls from a
  tool's own ruff pass in dict-mode fakes.
* :func:`_autofix_target_paths` — mirrors the ``paths`` slot of
  :func:`python_setup_lint.runner.cmd_build._build_command` for the three
  ``supports_fix`` tools (ruff, rumdl, ty).  Empty list when no path and
  no ``default_paths``.
* :func:`_apply_autofix_conflict_aware` — runs a ``supports_fix`` tool with
  ``fix=True``, skips staged+unstaged files, E999-reverts files via the
  in-memory byte snapshot.  Returns the tool's fix-pass
  :class:`python_setup_lint.runner.types.LintResult`.
"""

import re
from collections.abc import Callable
from pathlib import Path

from .types import LintResult, RunnerConfig, ToolSpec

_CONFIG_KEY_ALIASES: dict[str, str]
"""Short alias → canonical ``--config TOOL=PATH`` label (``ruff`` → ``ruff check``)."""

_SUPPORTED_CONFIG_KEYS: frozenset[str]
"""Closed ``--config`` key set — canonical labels + short aliases.  Unknown
ids exit non-zero via ``argparse`` ``parser.error`` (T8 fail-fast)."""

_AUTOFIX_ENV_VAR: str
"""Env-var name consulted at the top of :func:`run_lint` to disable autofix.

``PYTHON_SETUP_LINT_NO_AUTOFIX=1`` flips ``fix=False`` internally before the
tool loop runs; a single stderr line confirms the override.  The CLI
``--fix`` arg still parses unchanged.
"""

_E999_RULE: str
"""Ruff rule code (``E999``) for syntax errors — the parseability-canary signal."""

_E999_LINE_RE: re.Pattern[str]
"""Compiled regex matching ``path:line:col: E999[ message]`` ruff canary lines.

Tolerant of Windows drive-letter colons in the path group (greedy ``.+?``
absorbs ``C:\\\\foo\\\\bar.py`` whole and only splits the trailing
``:INT:INT: E999`` shape).  Used by :func:`_ruff_parseability_errors` so
non-E999 issues and unparseable lines are skipped cleanly — no garbage
short-path lands in the result set.
"""

def _git_changed_files(cwd: Path, *, staged: bool) -> set[str]:
    """Return repo-relative paths reported by ``git diff --name-only``.

    Args:
        cwd: Working directory the lint run is rooted at.
        staged: ``True`` → ``--cached`` (index vs HEAD); ``False`` → worktree
            vs index.

    Returns:
        Set of repo-relative paths; empty set on any git failure (non-git
        cwd, uninitialised repo, ``git`` missing, non-zero exit, 30s
        timeout).  Callers treat an empty set uniformly as "no files
        conflict" so autofix applies unconditionally in a non-git project.
    """

def _ruff_parseability_errors(
    cwd: Path, paths: list[str], run_cmd: Callable[..., LintResult]
) -> set[str]:
    """Return paths in *paths* that ruff reports ``E999`` syntax errors on.

    Single ``ruff check --no-fix`` invocation dispatched through *run_cmd*
    with the label ``"python-setup:autofix-canary"``.  Used by
    :func:`_apply_autofix_conflict_aware` after each ``supports_fix`` tool's
    fix pass to detect files the tool broke parseability on.

    Args:
        cwd: Working directory; ruff invoked here so paths stay repo-relative.
        paths: Repo-relative paths to include in the canary.  Empty list
            short-circuits to an empty set — no ruff invocation.
        run_cmd: Callable matching ``_run_cmd(cmd, *, cwd, label) -> LintResult``.

    Returns:
        Set of paths (relative to *cwd*) with ``E999`` in the canary's
        stdout.  Empty set when no ``E999`` line is found, or when ruff is
        unavailable (``FileNotFoundError`` swallowed).
    """

def _autofix_target_paths(
    spec: ToolSpec, *, config: RunnerConfig, path: str | None
) -> list[str]:
    """Return repo-relative paths the tool's fix pass would touch.

    Mirrors :func:`python_setup_lint.runner.cmd_build._build_command`'s path
    slot for the three ``supports_fix`` tools (ruff, rumdl, ty).  Returns an
    empty list when the spec has no ``default_paths`` and no explicit
    ``--path`` was passed — the autofix helper treats an empty list as "no
    files to skip-check or revert", so the tool still runs but no in-memory
    snapshot can be restored.

    Args:
        spec: The tool to enumerate paths for.
        config: :class:`RunnerConfig` — ``config.cwd`` is the glob root.
        path: CLI ``--path`` override, or ``None`` to use ``spec.default_paths``.

    Returns:
        Glob-expanded repo-relative paths; empty list when no path and no
        ``default_paths``.
    """

def _apply_autofix_conflict_aware(
    spec: ToolSpec,
    *,
    config: RunnerConfig,
    paths_to_check: list[str],
    run_cmd: Callable[..., LintResult],
) -> LintResult:
    """Run *spec* with ``fix=True`` after staged+unstaged skip + E999-canary revert.

    Side effects:
    * Runs the tool's fix pass (via *run_cmd*, label = ``spec.name``).
    * Skips files in *paths_to_check* that appear in BOTH the staged and
      unstaged ``git diff`` sets — prints one stderr line per skipped file.
    * Restores any file the post-fix ruff canary reports ``E999`` on — the
      pre-fix byte snapshot captured in-memory is written back, and one
      stderr line per reverted file is printed.

    Args:
        spec: ``ToolSpec`` with ``supports_fix=True``.
        config: :class:`RunnerConfig` — ``config.cwd`` is the git root and
            the cwd the tool is invoked in.
        paths_to_check: Repo-relative files to skip-check + snapshot.
            Computed by :func:`run_lint` via :func:`_autofix_target_paths`.
        run_cmd: Callable matching ``_run_cmd(cmd, *, cwd, label) -> LintResult``.
            Used for BOTH the fix tool (label ``spec.name``) and the canary
            (label ``"python-setup:autofix-canary"``).

    Returns:
        The :class:`LintResult` of the fix pass; reverts happen AFTER
        the result is captured (the result's ``exit_code`` reflects the
        fix pass, the revert only restores on-disk bytes).
    """

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

    Returns 0 if all tools pass, non-zero on any failure.

    Args:
        config: Project-level :class:`RunnerConfig`.  Defaults to
            ``RunnerConfig(cwd=Path.cwd())`` when ``None``.
        path: Scope to a specific file or directory.
        fix: Apply autofixes (ruff, rumdl, ty).
        baseline: Path to a baseline JSON file. Created on first run,
            compared on subsequent runs.
        exclude: Exclude a file or directory pattern from supported tools.
        no_fail_fast: Run all tools even if some fail, then report
            aggregate exit code.
        statistics: Collect and display per-rule violation counts.
        statistics_format: ``\"table\"`` (default) or ``\"json\"``.
        overwrite_baseline: Force overwrite of existing baseline file
            (used with ``--baseline``).
        group: Group statistics output (``\"none\"``, ``\"tool\"``, ``\"rule\"``, ``\"file\"``).
        sort_by_rule: Sort by rule name instead of count.

    Raises:
        python_setup_lint.runner.extra_tools.ExtraToolsConfigError: on an
            unknown ``tools_override`` name (T8 fail-fast) or a malformed
            pyproject extra-tools entry.
    """

def main(argv: list[str] | None = None, *, config: RunnerConfig | None = None) -> int:
    """CLI entry point for ``uv run lint``.

    When *config* is provided, CLI flags still override the pre-built
    configuration (cwd, package-name, default-py-dirs, tools, config-paths
    can all be set on the command line).  This lets thin wrappers
    (``consultant_mcp._lint_scripts:main``) construct a default
    configuration while still exposing the full CLI surface.
    """
