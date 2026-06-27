"""Stub for :mod:`python_setup_lint.runner._autofix`.

T4 — conflict-tolerant autofix helpers.
"""


import re
from collections.abc import Callable
from pathlib import Path

from .types import LintResult, RunnerConfig, ToolSpec

_AUTOFIX_ENV_VAR: str = ...
_E999_RULE: str = ...
_E999_LINE_RE: re.Pattern[str] = ...

def _git_changed_files(cwd: Path, *, staged: bool) -> set[str]: ...
def _ruff_parseability_errors(
    cwd: Path, paths: list[str], run_cmd: Callable[..., LintResult]
) -> set[str]: ...
def _apply_autofix_conflict_aware(
    spec: ToolSpec,
    *,
    config: RunnerConfig,
    paths_to_check: list[str],
    run_cmd: Callable[..., LintResult],
) -> LintResult: ...
def _autofix_target_paths(
    spec: ToolSpec, *, config: RunnerConfig, path: str | None
) -> list[str]: ...