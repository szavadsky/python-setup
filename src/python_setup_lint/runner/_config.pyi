"""Stub for :mod:`python_setup_lint.runner._config`.

T1b — self-discovery helpers + CLI config-key aliases.
"""

from pathlib import Path

_SHIPPED_CONFIG_FILES: dict[str, str] = ...
_CONFIG_KEY_ALIASES: dict[str, str] = ...
_SUPPORTED_CONFIG_KEYS: frozenset[str] = ...

def _default_config_paths(cwd: Path) -> dict[str, Path]: ...
def _infer_package_name(cwd: Path) -> str | None: ...
def _config_origin(
    name: str,
    config_path: Path | None,
    *,
    cli_overridden: frozenset[str],
    caller_config_paths: dict[str, Path],
    shipped_paths: dict[str, Path],
    version: str,
    ruff_composed: bool,
) -> str | None: ...
def _print_config_status(
    *,
    config_paths: dict[str, Path],
    cli_overridden: frozenset[str],
    caller_config_paths: dict[str, Path],
    shipped_paths: dict[str, Path],
    cwd: Path,
    ruff_composed: bool,
) -> None: ...
