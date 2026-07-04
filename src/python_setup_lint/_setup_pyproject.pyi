"""Pyproject.toml read/write helpers for python-setup install.

Extracted from setup.py for module-size compliance (G5 §2).
"""

from pathlib import Path

_PACKAGE_NAME: str

def _read_pyproject_toml(project_dir: Path, /) -> dict[str, object] | None:
    """Read pyproject.toml from *project_dir* and return parsed dict, or None."""

def _write_pyproject_toml(project_dir: Path, data: dict[str, object], /) -> None:
    """Write *data* as TOML to pyproject.toml in *project_dir* atomically."""

def _pylint_main_section(data: dict[str, object], /) -> dict[str, object] | None:
    """Return the [tool.pylint.main] sub-dict from *data*, or None."""

def _get_pylint_load_plugins(data: dict[str, object], /) -> list[str]:
    """Return the load-plugins list from [tool.pylint.main], or [].

    Returns:
        The list of plugin module names, or an empty list if not configured.
    """

def _ensure_pylint_main_section(data: dict[str, object], /) -> dict[str, object] | None:
    """Ensure [tool.pylint.main] exists in *data*, creating if needed.

    Returns:
        The [tool.pylint.main] dict, or None if the structure is invalid.
    """

def _set_pylint_load_plugins(data: dict[str, object], plugins: list[str], /) -> None:
    """Set load-plugins in [tool.pylint.main] to *plugins*."""

def _get_dev_deps(data: dict[str, object], /) -> list[str]:
    """Return the dev dependency list from [dependency-groups.dev], or [].

    Returns:
        The list of dev dependency strings, or an empty list if not configured.
    """

def _has_python_setup_dep(dev_deps: list[str], /) -> bool:
    """Check if *dev_deps* contains the python-setup package."""
