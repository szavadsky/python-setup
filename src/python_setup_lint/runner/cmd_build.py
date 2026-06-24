"""Path discovery, glob expansion, config-flag mapping, and command construction.

These helpers are pure string/path transforms — no subprocess.  Strategies
in :mod:`python_setup_lint.runner.dispatch` delegate here for the
tool-agnostic command shape; tool-specific strategies override
``build_command`` for the three tools whose command shape cannot be expressed
declaratively (``mypy.stubtest``, ``pyright verify types``, ``detect-secrets``,
``pylint``).
"""

from __future__ import annotations

import tempfile
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

from .types import RunnerConfig, ToolSpec

__all__ = [
    "_build_command",
    "_build_statistics_flags",
    "_compose_ruff_config",
    "_config_flag_for",
    "_expand_globs",
    "_find_py_files",
    "_resolve_pylintrc",
]


# Module-level memo for parsed ``pyproject.toml`` used by
# :func:`_compose_ruff_config`, keyed by ``(resolved_path, mtime_ns)``.
# An edit to the file mid-session triggers a fresh parse because the mtime
# changes.  Ported from consultant.mcp ``_lint_scripts._PYPROJECT_CACHE`` —
# kept module-private, not re-exported via ``runner/__init__``.
_PYPROJECT_CACHE: dict[tuple[Path, int], dict] = {}


def _build_statistics_flags(spec: ToolSpec) -> list[str]:
    """Build extra CLI flags for statistics output mode.

    Each tool uses a different flag or format to emit machine-readable
    violation data.  Returns an empty list when the tool already emits
    parseable output by default.
    """
    flags: dict[str, list[str]] = {
        "ruff check": ["--statistics"],
        "rumdl check": ["--statistics"],
        "pylint": ["--output-format=json2"],
        "pyright check": ["--outputjson"],
        "mypy": ["--no-error-summary"],
        "ty check": ["--output-format", "concise"],
        "tach check": ["--output", "json"],
        "yamllint": ["-f", "parsable"],
    }
    return flags.get(spec.name, [])


def _find_py_files(dirs: Sequence[str], *, cwd: Path) -> list[str]:
    """Find all .py files under *dirs* sorted uniquely (relative to cwd)."""
    files: set[Path] = set()
    for d in dirs:
        p = cwd / d
        if p.is_dir():
            files.update(p.rglob("*.py"))
        elif p.is_file() and p.suffix == ".py":
            files.add(p)
    return sorted(str(f.relative_to(cwd)) for f in files)


def _expand_globs(paths: Sequence[str], *, cwd: Path) -> list[str]:
    """Expand shell glob patterns (*, ?) in *paths* relative to cwd."""
    cwd = Path(cwd)
    result: list[str] = []
    for p in paths:
        if "*" in p or "?" in p:
            expanded = sorted(str(f.relative_to(cwd)) for f in cwd.glob(p))
            result.extend(expanded)
        else:
            result.append(p)
    return result


def _config_flag_for(spec_name: str, config_path: Path | None) -> list[str]:
    """Build CLI flag that tells a tool to use *config_path*.

    Returns an empty list when no config path is provided or the tool does not
    support external configuration files.
    """
    if config_path is None:
        return []
    flags: dict[str, list[str]] = {
        "ruff check": ["--config", str(config_path)],
        "mypy": ["--config-file", str(config_path)],
        "pylint": ["--rcfile", str(config_path)],
        "pyright check": ["--project", str(config_path)],
        "pyright verify types": ["--project", str(config_path)],
        "rumdl check": ["--config", str(config_path)],
        "ty check": ["--config-file", str(config_path)],
        "yamllint": ["--config-file", str(config_path)],
    }
    return flags.get(spec_name, [])


def _resolve_pylintrc(config_paths: dict[str, Path], cwd: Path) -> Path | None:
    """Return the pylint rcfile path, or ``None`` if none found.

    Checks ``config_paths`` for an explicit ``"pylint"`` entry first.
    Falls back to auto-discovery: ``config/.pylintrc`` (shipped config
    dir), then ``.pylintrc`` (project root).
    """
    explicit = config_paths.get("pylint")
    if explicit is not None:
        return explicit
    for candidate in (cwd / "config" / ".pylintrc", cwd / ".pylintrc"):
        if candidate.is_file():
            return candidate
    return None


def _load_pyproject_toml(path: Path) -> dict:
    """Load and cache ``pyproject.toml``, keyed by path + mtime.

    Memoised so repeated calls within the same process avoid re-parsing
    the file when it has not changed on disk.  Cache key is
    ``(resolved_path, mtime_ns)`` — an edit to the file mid-session
    triggers a fresh parse.  Returns an empty dict when the path is
    unreadable (caller treats as no-override).

    Raises:
        SystemExit: when the pyproject is malformed (T8 fail-fast on
            malformed configuration rather than silent fallback).
    """
    resolved = path.resolve()
    try:
        mtime = resolved.stat().st_mtime_ns
    except OSError:
        return {}
    key = (resolved, mtime)
    cached = _PYPROJECT_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        with open(resolved, "rb") as f:  # noqa: SIM115
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise SystemExit(
            f"python_setup_lint.runner.cmd_build: pyproject.toml at {resolved} is malformed or unreadable: {exc}"
        ) from exc
    _PYPROJECT_CACHE[key] = data
    return data


def _compose_ruff_config(cwd: Path, shared_config: Path) -> Path:
    """Build an effective ruff config that ``extend``s *shared_config*.

    ``ruff check --config <shared>`` does not merge project-specific
    settings from ``pyproject.toml``.  This helper writes a temporary
    ``ruff.toml`` that extends the shared config + copies the project's
    ``[tool.ruff.lint.flake8-tidy-imports].banned-api`` and
    ``[tool.ruff.lint.per-file-ignores]`` stanzas so the runner can pass
    it to ruff via ``--config``.

    No-override fast path: when the project ``pyproject.toml`` has neither
    a ``banned-api`` table nor a ``per-file-ignores`` table (or is
    missing/unreadable), returns *shared_config* unchanged — no temp file
    written.

    Temp file location: ``tempfile.gettempdir() /
    "python_setup_lint_ruff_{cwd_name}" / "ruff.toml"`` — written once
    per run.  Ported verbatim from consultant.mcp
    ``_ruff_config_with_project_overrides`` (battle-tested).

    Args:
        cwd: Project root — ``cwd / "pyproject.toml"`` is the override
            source.
        shared_config: Shared ruff config path (the ``extend`` target).

    Returns:
        Path to the composed temp ``ruff.toml``, or *shared_config*
        unchanged when no overrides apply.
    """
    project_banned_api: dict[str, dict[str, str]] = {}
    project_per_file: dict[str, list[str]] = {}
    pyproject = cwd / "pyproject.toml"
    if pyproject.is_file():
        data = _load_pyproject_toml(pyproject)
        lint_cfg = data.get("tool", {}).get("ruff", {}).get("lint", {})
        raw_banned_api = lint_cfg.get("flake8-tidy-imports", {}).get("banned-api", {})
        if isinstance(raw_banned_api, dict):
            project_banned_api = {
                key: {"msg": str(value.get("msg", ""))} if isinstance(value, dict) else {"msg": str(value)}
                for key, value in raw_banned_api.items()
            }
        raw_per_file = lint_cfg.get("per-file-ignores", {})
        if isinstance(raw_per_file, dict):
            project_per_file = {
                key: [str(v) for v in value] if isinstance(value, list) else [str(value)] for key, value in raw_per_file.items()
            }

    # No-override fast path — return shared config unchanged.
    if not project_banned_api and not project_per_file:
        return shared_config

    lines: list[str] = [f'extend = "{shared_config}"', ""]
    if project_banned_api:
        lines.append("[lint.flake8-tidy-imports]")
        for api, info in project_banned_api.items():
            safe_api = api.replace('"', '\\"')
            msg = info.get("msg", "")
            lines.append(f'banned-api."{safe_api}" = {{ msg = "{msg}" }}')
        lines.append("")
    if project_per_file:
        lines.append("[lint.per-file-ignores]")
        for pattern, codes in project_per_file.items():
            safe_pattern = pattern.replace('"', '\\"')
            lines.append(f'"{safe_pattern}" = {codes}')
        lines.append("")

    out_dir = Path(tempfile.gettempdir()) / f"python_setup_lint_ruff_{cwd.name}"
    out_dir.mkdir(parents=True, exist_ok=True)
    effective = out_dir / "ruff.toml"
    effective.write_text("\n".join(lines), encoding="utf-8")
    return effective


def _build_command(
    spec: ToolSpec,
    *,
    config: RunnerConfig,
    fix: bool = False,
    path: str | None = None,
    exclude: str | None = None,
    config_flag_override: list[str] | None = None,
) -> list[str]:
    """Build the full command list for a tool spec given runtime flags."""
    cmd = list(spec.command)
    config_paths = config.config_paths or {}

    # ── Shared config files ───────────────────────────────────
    if config_flag_override is not None:
        extra_cfg = config_paths.get(spec.name)
        if extra_cfg is not None:
            cmd.extend([*config_flag_override, str(extra_cfg)])
    else:
        cmd.extend(_config_flag_for(spec.name, config_paths.get(spec.name)))

    # ── Fix flags (data-driven via ToolSpec.fix_flags) ────────
    if fix and spec.supports_fix:
        cmd.extend(spec.fix_flags)

    # ── Path scoping ───────────────────────────────────────────
    paths: list[str] = []
    if path is not None and spec.supports_path:
        paths = [path]
    elif spec.default_paths:
        paths = list(spec.default_paths)

    # Expand globs (e.g. config/*.yaml)
    paths = _expand_globs(paths, cwd=config.cwd)

    if paths:
        cmd.extend(paths)

    # ── Exclude flags (data-driven via ToolSpec.exclude_flag) ─
    if exclude is not None and spec.supports_exclude:
        cmd.extend([spec.exclude_flag, exclude])

    return cmd
