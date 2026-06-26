"""Stub for :mod:`python_setup_lint.runner._config`.

T1b — self-discovery helpers + CLI config-key aliases.
"""


from pathlib import Path


    name: str,
    config_path: Path | None,
    *,
    cli_overridden: frozenset[str],
    caller_config_paths: dict[str, Path],
    shipped_paths: dict[str, Path],
    version: str,
    ruff_composed: bool,
) -> str | None: ...
    *,
    config_paths: dict[str, Path],
    cli_overridden: frozenset[str],
    caller_config_paths: dict[str, Path],
    shipped_paths: dict[str, Path],
    cwd: Path,
    ruff_composed: bool,
) -> None: ...
