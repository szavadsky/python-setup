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
    "_compose_pyright_config",
    "_compose_ruff_config",
    "_config_flag_for",
    "_expand_globs",
    "_find_py_files",
    "_find_pyi_files",
    "_resolve_pylintrc",
]


# Module-level memo for parsed ``pyproject.toml`` used by
# :func:`_compose_ruff_config`, keyed by ``(resolved_path, mtime_ns)``.
# An edit to the file mid-session triggers a fresh parse because the mtime
# changes.  Ported from consultant.mcp ``_lint_scripts._PYPROJECT_CACHE`` —
# kept module-private, not re-exported via ``runner/__init__``.
_PYPROJECT_CACHE: dict[tuple[Path, int], dict] = {}


def _build_statistics_flags(spec: ToolSpec) -> list[str]:
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
    files: set[Path] = set()
    for d in dirs:
        p = cwd / d
        if p.is_dir():
            files.update(p.rglob("*.py"))
        elif p.is_file() and p.suffix == ".py":
            files.add(p)
    return sorted(str(f.relative_to(cwd)) for f in files)


def _find_pyi_files(dirs: Sequence[str], *, cwd: Path) -> list[str]:
    files: set[Path] = set()
    for d in dirs:
        resolved = (cwd / d).resolve()
        if resolved.is_dir():
            files.update(resolved.rglob("*.pyi"))
        elif resolved.is_file():
            files.add(resolved)
    return sorted(str(f.relative_to(cwd)) for f in files)


def _expand_globs(paths: Sequence[str], *, cwd: Path) -> list[str]:
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


def _build_config_flags(
    spec: ToolSpec,
    config: RunnerConfig,
    *,
    config_flag_override: list[str] | None = None,
) -> list[str]:
    # Resolve config flags for *spec* from *config* or an explicit override.
    config_paths = config.config_paths or {}
    if config_flag_override is not None:
        extra_cfg = config_paths.get(spec.name)
        if extra_cfg is not None:
            return [*config_flag_override, str(extra_cfg)]
        return []
    return _config_flag_for(spec.name, config_paths.get(spec.name))


def _resolve_pylintrc(config_paths: dict[str, Path], cwd: Path) -> Path | None:
    explicit = config_paths.get("pylint")
    if explicit is not None:
        return explicit
    for candidate in (cwd / "config" / ".pylintrc", cwd / ".pylintrc"):
        if candidate.is_file():
            return candidate
    return None


def _load_pyproject_toml(path: Path) -> dict[str, object]:
    resolved = path.resolve()
    try:
        mtime = resolved.stat().st_mtime_ns
    except OSError:  # pylint: disable=W9740  # best-effort stat fallback; logging would noise unavoidable IO degrade
        return {}
    key = (resolved, mtime)
    cached = _PYPROJECT_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        with open(resolved, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise SystemExit(
            f"python_setup_lint.runner.cmd_build: pyproject.toml at {resolved} is malformed or unreadable: {exc}"
        ) from exc
    _PYPROJECT_CACHE[key] = data
    return data


def _compose_ruff_config(cwd: Path, shared_config: Path) -> Path:
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

    lines: list[str] = [
        "# Generated by python-setup — do not edit. Changes in pyproject.toml [tool.ruff.lint] are picked up automatically.",
        f'extend = "{shared_config}"',
        "",
    ]
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


def _compose_pyright_config(cwd: Path, shared_config: Path) -> Path:
    try:
        raw = shared_config.read_text(encoding="utf-8")
    except OSError:  # pylint: disable=W9740  # best-effort config read fallback
        return shared_config
    # Fast path: shipped config already in cwd → relative paths resolve correctly.
    if shared_config.resolve().parent == cwd.resolve():
        return shared_config
    # Pyright resolves exclude/venvPath/extraPaths relative to the config FILE's dir.
    # Absolute paths in exclude are silently rejected; specifying exclude disables
    # auto-excludes (**/__pycache__, **/.*). So: write the composed config INTO cwd
    # (gitignored) with relative paths unchanged — pyright resolves them against cwd.
    composed = cwd / ".pyrightconfig-composed.json"
    try:
        composed.write_text(raw, encoding="utf-8")
    except OSError:  # pylint: disable=W9740  # read-only cwd or permission error; fall back to shared config
        return shared_config
    return composed


def _build_fix_flags(spec: ToolSpec, *, fix: bool) -> list[str]:
    # Return fix flags if *fix* is requested and the tool supports it.
    if fix and spec.supports_fix:
        return list(spec.fix_flags)
    return []


def _build_path_and_exclude_args(
    spec: ToolSpec,
    *,
    config: RunnerConfig,
    path: str | None = None,
    exclude: str | None = None,
) -> list[str]:
    # Resolve path scoping and exclude flags for *spec*.
    result: list[str] = []

    # ── Path scoping ───────────────────────────────────────────
    paths: list[str] = []
    if path is not None and spec.supports_path:
        paths = [path]
    elif spec.default_paths:
        paths = list(spec.default_paths)

    # Expand globs (e.g. config/*.yaml)
    paths = _expand_globs(paths, cwd=config.cwd)

    if paths:
        result.extend(paths)

    # ── Exclude flags (data-driven via ToolSpec.exclude_flag) ─
    if exclude is not None and spec.supports_exclude:
        result.extend([spec.exclude_flag, exclude])

    return result


def _build_command(
    spec: ToolSpec,
    *,
    config: RunnerConfig,
    fix: bool = False,
    path: str | None = None,
    exclude: str | None = None,
    config_flag_override: list[str] | None = None,
) -> list[str]:
    cmd = list(spec.command)
    cmd.extend(_build_config_flags(spec, config, config_flag_override=config_flag_override))
    cmd.extend(_build_fix_flags(spec, fix=fix))
    cmd.extend(_build_path_and_exclude_args(spec, config=config, path=path, exclude=exclude))
    return cmd
