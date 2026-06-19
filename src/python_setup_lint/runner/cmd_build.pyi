"""Stub for :mod:`python_setup_lint.runner.cmd_build`.

Path discovery, glob expansion, config-flag mapping, per-tool command
construction, and statistics-mode flag selection.
"""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

from .types import RunnerConfig, ToolSpec

def _find_py_files(dirs: Sequence[str], *, cwd: Path) -> list[str]:
    """Find all .py files under *dirs*, sorted uniquely relative to *cwd*."""

def _expand_globs(paths: Sequence[str], *, cwd: Path) -> list[str]:
    """Expand shell glob patterns (*, ?) in *paths* relative to *cwd*."""

def _config_flag_for(spec_name: str, config_path: Path | None) -> list[str]:
    """Build the CLI flag telling a tool to use *config_path*.

    Returns ``[]`` when *config_path* is ``None`` or the tool has no
    external-config flag (e.g. ``tach check``, ``yamllint``).
    """

def _build_statistics_flags(spec: ToolSpec) -> list[str]:
    """Build extra CLI flags for a tool's statistics-mode invocation.

    Returns ``[]`` when the tool already emits parseable output by default.
    """

def _build_command(
    spec: ToolSpec,
    *,
    config: RunnerConfig,
    fix: bool = False,
    path: str | None = None,
    exclude: str | None = None,
    config_flag_override: list[str] | None = None,
) -> list[str]:
    """Build the full command list for *spec* given runtime flags.

    *config_flag_override* lets :class:`~python_setup_lint.runner.dispatch.GenericLintTool`
    forward a declarative ``config_flag`` for extras (the name→flag dict in
    :func:`_config_flag_for` returns ``[]`` for unknown tool names).
    """
