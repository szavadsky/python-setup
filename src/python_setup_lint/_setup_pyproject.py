from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

from ._setup_precommit import _atomic_write

if TYPE_CHECKING:
    from pathlib import Path


# ── Constants ───────────────────────────────────────────────────────

_PACKAGE_NAME: str = "python-setup"


# ── Pyproject TOML helpers ──────────────────────────────────────────


def _read_pyproject_toml(project_dir: Path, /) -> dict[str, object] | None:
    toml_path = project_dir / "pyproject.toml"
    if not toml_path.is_file():
        return None
    with open(toml_path, "rb") as f:
        return tomllib.load(f)


def _write_pyproject_toml(project_dir: Path, data: dict[str, object], /) -> None:
    import tomli_w

    toml_path = project_dir / "pyproject.toml"
    _atomic_write(toml_path, tomli_w.dumps(data))


def _pylint_main_section(data: dict[str, object], /) -> dict[str, object] | None:
    tool = data.get("tool")
    if not isinstance(tool, dict):
        return None
    pylint = tool.get("pylint")
    if not isinstance(pylint, dict):
        return None
    main = pylint.get("main")
    if not isinstance(main, dict):
        return None
    return main  # type: ignore[return-value]  # pyright: main is dict[Unknown, Unknown] from pyproject.toml parsing, not dict[str, object]  # ty:ignore[invalid-return-type]


def _get_pylint_load_plugins(data: dict[str, object], /) -> list[str]:
    main = _pylint_main_section(data)
    if main is None:
        return []
    plugins = main.get("load-plugins", [])
    if isinstance(plugins, list):
        return [str(p) for p in plugins]
    return []


def _ensure_pylint_main_section(data: dict[str, object], /) -> dict[str, object] | None:
    tool = data.setdefault("tool", {})
    if not isinstance(tool, dict):
        return None
    pylint = tool.setdefault("pylint", {})  # type: ignore[arg-type]  # dict[str, object]; setdefault overloads conflict  # ty:ignore[no-matching-overload]
    if not isinstance(pylint, dict):
        return None
    main = pylint.setdefault("main", {})
    if not isinstance(main, dict):
        return None
    return main


def _set_pylint_load_plugins(data: dict[str, object], plugins: list[str], /) -> None:
    main = _ensure_pylint_main_section(data)
    if main is not None:
        main["load-plugins"] = plugins


def _get_dev_deps(data: dict[str, object], /) -> list[str]:
    dg = data.get("dependency-groups", {})
    if not isinstance(dg, dict):
        return []
    dev = dg.get("dev", [])
    if isinstance(dev, list):
        return [str(d) for d in dev]
    return []


def _has_python_setup_dep(dev_deps: list[str], /) -> bool:
    for dep in dev_deps:
        # PEP 508: package name is everything before first [ < > = ! ~ @
        # Strip extras [...], then version/URL specifiers
        name = dep.split("[")[0]
        for sep in (">=", "<=", "!=", "==", "~=", "@", ">"):
            if sep in name:
                name = name.split(sep)[0]
        name = name.strip()
        if name == _PACKAGE_NAME:
            return True
    return False
