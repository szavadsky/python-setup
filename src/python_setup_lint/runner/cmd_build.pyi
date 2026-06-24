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

def _resolve_pylintrc(config_paths: dict[str, Path], cwd: Path) -> Path | None:
    """Return the pylint rcfile path, or ``None`` if none found.

    Checks ``config_paths`` for an explicit ``"pylint"`` entry first.
    Falls back to auto-discovery: ``config/.pylintrc`` (shipped config
    dir), then ``.pylintrc`` (project root).
    """

def _load_pyproject_toml(path: Path) -> dict:
    """Load and cache ``pyproject.toml``, keyed by ``(resolved_path, mtime_ns)``.

    Memoised so repeated calls within the same process avoid re-parsing the
    file when it has not changed on disk.  Returns an empty dict when the
    path is unreadable (caller treats as no-override).  Raises ``SystemExit``
    when the pyproject is malformed (T8 fail-fast on malformed config rather
    than silent fallback).
    """

def _compose_ruff_config(cwd: Path, shared_config: Path) -> Path:
    """Build an effective ruff config that ``extend``s *shared_config*.

    Writes a temporary ``ruff.toml`` that extends the shared config + copies
    the project's ``[tool.ruff.lint.flake8-tidy-imports].banned-api`` and
    ``[tool.ruff.lint.per-file-ignores]`` stanzas.  No-override fast path:
    returns *shared_config* unchanged (no temp file) when the project
    ``pyproject.toml`` has neither stanza.  Temp file lands under
    ``tempfile.gettempdir() / "python_setup_lint_ruff_{cwd_name}" / "ruff.toml"``.
    Ported from consultant.mcp ``_ruff_config_with_project_overrides``.
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
