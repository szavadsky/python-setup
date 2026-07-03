
from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable  # TYPE_CHECKING-only import; not available at runtime
from pathlib import Path  # TYPE_CHECKING-only import; not available at runtime

import beartype

from .cmd_build import _expand_globs, _find_py_files
from .dispatch import (
    _strategy_for,  # type: ignore[attr-defined]  # private symbol removed from .pyi per M3(b); runtime import still works
)
from .types import LintResult, RunnerConfig, ToolSpec  # TYPE_CHECKING-only import; not available at runtime

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
    except FileNotFoundError, subprocess.TimeoutExpired:  # pylint: disable=W9740  # best-effort git subprocess fallback; logging would noise unavoidable tool-not-found/timeout degrade
        return set()
    if proc.returncode != 0:
        return set()
    return {line for line in proc.stdout.splitlines() if line.strip()}


@beartype.beartype
def _ruff_parseability_errors(
    cwd: Path, paths: list[str], run_cmd: Callable[..., LintResult]
) -> set[str]:
    if not paths:
        return set()
    cmd = ["ruff", "check", "--no-fix", *paths]
    try:
        result = run_cmd(cmd, cwd=cwd, label="python-setup:autofix-canary")
    except FileNotFoundError:  # pylint: disable=W9740  # best-effort ruff subprocess fallback; logging would noise unavoidable tool-not-found degrade
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
    run_cmd: Callable[..., LintResult],
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
        except (FileNotFoundError, IsADirectoryError):  # pylint: disable=W9740  # best-effort snapshot read fallback; logging would noise unavoidable file-not-found/dir degrade
            continue

    strategy = _strategy_for(spec.name, spec)
    cmd = strategy.build_command(config=config, _fix=True)
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
