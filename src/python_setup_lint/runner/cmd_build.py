"""Path discovery, glob expansion, config-flag mapping, and command construction.

These helpers are pure string/path transforms — no subprocess.  Strategies
in :mod:`python_setup_lint.runner.dispatch` delegate here for the
tool-agnostic command shape; tool-specific strategies override
``build_command`` for the three tools whose command shape cannot be expressed
declaratively (``mypy.stubtest``, ``pyright verify types``, ``detect-secrets``,
``pylint``).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

from .types import RunnerConfig, ToolSpec

__all__ = [
    "_build_command",
    "_build_statistics_flags",
    "_config_flag_for",
    "_expand_globs",
    "_find_py_files",
]


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
    }
    return flags.get(spec_name, [])


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
