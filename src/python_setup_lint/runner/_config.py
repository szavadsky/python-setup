"""T1b — self-discovery helpers + CLI config-key aliases.

Pure helpers that resolve shipped config paths and infer package_name
from pyproject.toml.  Both are callable from tests without invoking
``main`` or ``run_lint``.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

# Shipped config files that live under ``python_setup_lint/config/``.
# Each key is the canonical tool label used in ``_config_flag_for``.
_SHIPPED_CONFIG_FILES: dict[str, str] = {
    "ruff check": "ruff.toml",
    "mypy": "mypy.ini",
    "pylint": ".pylintrc",
    "pyright check": "pyrightconfig.json",
    "rumdl check": "rumdl.toml",
    "ty check": "ty.toml",
    "yamllint": ".yamllint",
}


def _default_config_paths(cwd: Path) -> dict[str, Path]:
    import python_setup_lint

    candidates: list[Path] = []
    pkg_file = python_setup_lint.__file__
    if pkg_file is not None:
        installed = Path(pkg_file).resolve().parent / "config"
        if installed.is_dir():
            candidates.append(installed)
    # Fallback: source-tree config/ (editable install / development).
    source = cwd / "config"
    if source.is_dir() and source not in candidates:
        candidates.append(source)
    if not candidates:
        return {}
    result: dict[str, Path] = {}
    for tool_label, filename in _SHIPPED_CONFIG_FILES.items():
        for config_dir in candidates:
            candidate = config_dir / filename
            if candidate.is_file():
                result[tool_label] = candidate
                break
    return result


def _infer_package_name(cwd: Path) -> str | None:
    pyproject = cwd / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    try:
        packages: list[str] = data["tool"]["hatch"]["build"]["targets"]["wheel"][
            "packages"
        ]  # type: ignore[index]
    except (KeyError, TypeError):
        return None
    if not packages:
        return None
    raw = packages[0]
    if raw.startswith("src/"):
        return raw[len("src/") :]
    return raw


# CLI config-key aliases (T8 fail-fast)
# Canonical ``--config TOOL=PATH`` labels + short aliases (``ruff`` →
# ``ruff check``).  Unknown ids exit non-zero via argparse ``parser.error``
# — no silent drop where a typo produced an entry :func:`_config_flag_for`
# never read.
_CONFIG_KEY_ALIASES: dict[str, str] = {
    "ruff": "ruff check",
    "pyright": "pyright check",
    "rumdl": "rumdl check",
    "ty": "ty check",
    "mypy": "mypy",
    "pylint": "pylint",
}
_SUPPORTED_CONFIG_KEYS: frozenset[str] = frozenset(
    set(_CONFIG_KEY_ALIASES) | set(_CONFIG_KEY_ALIASES.values())
)


def _config_origin(
    name: str,
    config_path: Path | None,
    *,
    cli_overridden: frozenset[str],
    caller_config_paths: dict[str, Path],
    shipped_paths: dict[str, Path],
    version: str,
    ruff_composed: bool,
) -> str | None:
    if config_path is None:
        return None
    if name in cli_overridden:
        return "overridden via --config"
    if name in caller_config_paths:
        return "overridden (RunnerConfig)"
    if name in shipped_paths and config_path.resolve() == shipped_paths[name].resolve():
        return f"shipped, from python-setup v{version}"
    if ruff_composed and name == "ruff check":
        return "generated (composed)"
    return "auto-discovered"


def _print_config_status(
    *,
    config_paths: dict[str, Path],
    cli_overridden: frozenset[str],
    caller_config_paths: dict[str, Path],
    shipped_paths: dict[str, Path],
    cwd: Path,
    ruff_composed: bool,
) -> None:
    import importlib.metadata

    try:
        version = importlib.metadata.version("python-setup")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"

    from .cmd_build import _resolve_pylintrc
    from .dispatch import LINT_TOOLS

    for spec in LINT_TOOLS:
        name = spec.name
        config_path = config_paths.get(name)

        if config_path is None:
            if name == "pylint":
                rcfile = _resolve_pylintrc(config_paths, cwd)
                if rcfile is not None:
                    print(f"  {name:<20} {rcfile}  (auto-discovered, project-local)")
                else:
                    print(f"  {name:<20}  (not configured)")
            else:
                print(f"  {name:<20}  (not configured)")
            continue

        origin = _config_origin(
            name, config_path,
            cli_overridden=cli_overridden,
            caller_config_paths=caller_config_paths,
            shipped_paths=shipped_paths,
            version=version,
            ruff_composed=ruff_composed,
        )
        if origin is not None:
            print(f"  {name:<20} {config_path}  ({origin})")
