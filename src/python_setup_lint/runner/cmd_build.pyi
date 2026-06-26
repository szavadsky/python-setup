"""Stub for :mod:`python_setup_lint.runner.cmd_build`.

Path discovery, glob expansion, config-flag mapping, per-tool command
construction, and statistics-mode flag selection.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

from .types import RunnerConfig, ToolSpec

    """Find all .py files under *dirs*, sorted uniquely relative to *cwd*."""

    """Expand shell glob patterns (*, ?) in *paths* relative to *cwd*."""

    """Build the CLI flag telling a tool to use *config_path*.

    Returns ``[]`` when *config_path* is ``None`` or the tool has no
    external-config flag (e.g. ``tach check``, ``yamllint``).
    """

    spec: ToolSpec, config: RunnerConfig, *, config_flag_override: list[str] | None = None
) -> list[str]:
    """Build config flags for a tool spec. Returns empty list if no config found."""

    """Build extra CLI flags for a tool's statistics-mode invocation.

    Returns ``[]`` when the tool already emits parseable output by default.
    """

    """Return the pylint rcfile path, or ``None`` if none found.

    Checks ``config_paths`` for an explicit ``"pylint"`` entry first.
    Falls back to auto-discovery: ``config/.pylintrc`` (shipped config
    dir), then ``.pylintrc`` (project root).
    """

    """Load and cache ``pyproject.toml``, keyed by ``(resolved_path, mtime_ns)``.

    Memoised so repeated calls within the same process avoid re-parsing the
    file when it has not changed on disk.  Returns an empty dict when the
    path is unreadable (caller treats as no-override).  Raises ``SystemExit``
    when the pyproject is malformed (T8 fail-fast on malformed config rather
    than silent fallback).
    """

    """Build an effective ruff config that ``extend``s *shared_config*.

    Writes a temporary ``ruff.toml`` that extends the shared config + copies
    the project's ``[tool.ruff.lint.flake8-tidy-imports].banned-api`` and
    ``[tool.ruff.lint.per-file-ignores]`` stanzas.  No-override fast path:
    returns *shared_config* unchanged (no temp file) when the project
    ``pyproject.toml`` has neither stanza.  Temp file lands under
    ``tempfile.gettempdir() / "python_setup_lint_ruff_{cwd_name}" / "ruff.toml"``.
    Ported from consultant.mcp ``_ruff_config_with_project_overrides``.
    """

    """Convert a relative path to absolute, or return None if invalid/absolute."""

    exclude_entries: object, abs_cwd: Path
) -> tuple[list[str], bool]:
    """Resolve exclude paths relative to abs_cwd. Returns (resolved, changed)."""

    """Build an effective pyright config with ``venvPath``/``exclude`` rooted at *cwd*.

    ``pyright --project <shared>`` resolves ``venvPath``/``exclude`` against
    the config FILE dir, not ``cwd`` — when the shipped config lives outside
    the project cwd (python-setup ships at ``config/pyrightconfig.json``),
    ``venvPath: "."`` resolves to the config dir → wrong venv → ``.venv``
    tree walked (~17k noise diagnostics).  This helper copies the shipped
    config to ``tempfile.gettempdir() / "python_setup_lint_pyright_{cwd_name}"
    / "pyrightconfig.json"``, rewriting ``venvPath`` + every relative
    ``exclude`` entry to absolute ``cwd``-rooted paths, then returns the tmp
    path.  No-op fast path: returns *shared_config* unchanged when no
    rewriting is needed (already-absolute, absent keys, or unreadable
    config).  The shipped config is never mutated.
    """

    """Return fix flags if fix is requested and the tool supports it."""

    spec: ToolSpec,
    *,
    config: RunnerConfig,
    path: str | None = None,
    exclude: str | None = None,
) -> list[str]:
    """Build path and exclude CLI args for a tool spec."""

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
