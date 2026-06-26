"""Stub for :mod:`python_setup_lint.runner._autofix`.

T4 — conflict-tolerant autofix helpers.
"""


import re
from collections.abc import Callable
from pathlib import Path

from .types import LintResult, RunnerConfig, ToolSpec


    cwd: Path, paths: list[str], run_cmd: Callable[..., LintResult]
) -> set[str]: ...
    spec: ToolSpec,
    *,
    config: RunnerConfig,
    paths_to_check: list[str],
    run_cmd: Callable[..., LintResult],
) -> LintResult: ...
    spec: ToolSpec, *, config: RunnerConfig, path: str | None
) -> list[str]: ...
