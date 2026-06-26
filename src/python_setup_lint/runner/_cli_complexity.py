"""Helper functions extracted from cli.py to reduce file size and complexity.

These functions handle config overrides, tool selection, config argument parsing,
config status display, and runner config construction — all used by the CLI
entry point in :mod:`python_setup_lint.runner.cli`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ._config import (
    _CONFIG_KEY_ALIASES,
    _SUPPORTED_CONFIG_KEYS,
    _default_config_paths,
    _infer_package_name,
    _print_config_status,
)
from .cmd_build import (
    _compose_pyright_config,
    _compose_ruff_config,
)
from .dispatch import LINT_TOOLS
from .extra_tools import ExtraToolsConfigError
from .types import RunnerConfig, ToolSpec


def _apply_config_overrides(config: RunnerConfig) -> RunnerConfig:
    if config.ruff_project_overrides:
        shared_ruff = config.config_paths.get("ruff check")
        if shared_ruff is not None:
            composed = _compose_ruff_config(config.cwd, shared_ruff)
            if composed != shared_ruff:
                config.config_paths["ruff check"] = composed
    if config.pyright_project_override is not None:
        config.config_paths["pyright check"] = config.pyright_project_override
    elif (
        config.config_paths is not None
        and config.config_paths.get("pyright check") is not None
    ):
        paths = config.config_paths
        shared_pyright = paths["pyright check"]
        composed_pyright = _compose_pyright_config(config.cwd, shared_pyright)
        if composed_pyright != shared_pyright:
            paths["pyright check"] = composed_pyright
    return config


def _select_tools(config: RunnerConfig) -> list[ToolSpec]:
    selected: list[ToolSpec] = []
    if config.tools_override is not None:
        lint_tools_by_name = {t.name: t for t in LINT_TOOLS}
        for raw_name in config.tools_override:
            name = raw_name.strip()
            spec = lint_tools_by_name.get(name)
            if spec is None:
                raise ExtraToolsConfigError(
                    "<RunnerConfig.tools_override>",
                    f"unknown tool name: {name!r}; known: {sorted(lint_tools_by_name)}",
                )
            selected.append(spec)
    else:
        selected = list(LINT_TOOLS)
    return selected


def _parse_config_args(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    base_config: RunnerConfig | None = None,
) -> dict[str, Path]:
    config_paths: dict[str, Path] = (
        dict(base_config.config_paths) if base_config is not None else {}
    )
    for raw in args.config:
        if "=" not in raw:
            parser.error(f"--config must be TOOL=PATH, got: {raw!r}")
        tool_id, path_str = raw.split("=", 1)
        if tool_id not in _SUPPORTED_CONFIG_KEYS:
            parser.error(
                f"--config: unknown tool id {tool_id!r}; "
                f"supported (canonical labels + short aliases): "
                f"{sorted(_SUPPORTED_CONFIG_KEYS)}"
            )
        canonical = _CONFIG_KEY_ALIASES.get(tool_id) or tool_id
        config_paths[canonical] = Path(path_str)
    return config_paths


def _handle_config_status(
    args: argparse.Namespace,
    config: RunnerConfig | None,
    cwd: Path,
    config_paths: dict[str, Path],
) -> int | None:
    if not args.config_status:
        return None
    cli_overridden: set[str] = set()
    for raw in args.config:
        if "=" not in raw:
            continue
        tool_id = raw.split("=", 1)[0]
        canonical = _CONFIG_KEY_ALIASES.get(tool_id) or tool_id
        cli_overridden.add(canonical)
    caller_config_paths: dict[str, Path] = (
        dict(config.config_paths) if config is not None else {}
    )
    shipped_paths = _default_config_paths(cwd)
    ruff_composed = (
        config is not None and config.ruff_project_overrides
    ) and "ruff check" in shipped_paths
    _print_config_status(
        config_paths=config_paths,
        cli_overridden=frozenset(cli_overridden),
        caller_config_paths=caller_config_paths,
        shipped_paths=shipped_paths,
        cwd=cwd,
        ruff_composed=ruff_composed,
    )
    return 0


def _build_runner_config(
    args: argparse.Namespace,
    *,
    base_config: RunnerConfig | None,
    cwd: Path,
    config_paths: dict[str, Path],
    cli_tools_override: list[str] | None,
) -> RunnerConfig:
    tools_override: list[str] | None = (
        cli_tools_override
        if cli_tools_override is not None
        else (base_config.tools_override if base_config is not None else None)
    )
    package_name = (
        args.package_name
        if args.package_name is not None
        else (base_config.package_name if base_config is not None else None)
    )
    default_py_dirs = (
        args.default_py_dirs.split(",")
        if args.default_py_dirs
        else (base_config.default_py_dirs if base_config is not None else None)
    )

    # ── T1b — self-discovery fallback ──────────────────────────
    if package_name is None:
        package_name = _infer_package_name(cwd)

    if not args.config and (base_config is None or not base_config.config_paths):
        discovered = _default_config_paths(cwd)
        for k, v in discovered.items():
            if k not in config_paths:
                config_paths[k] = v

    return RunnerConfig(
        cwd=cwd,
        package_name=package_name,
        default_py_dirs=default_py_dirs,
        tools_override=tools_override,
        config_paths=config_paths,
        secrets_baseline=base_config.secrets_baseline
        if base_config is not None
        else ".secrets.baseline",
        ruff_project_overrides=base_config.ruff_project_overrides
        if base_config is not None
        else False,
        pyright_project_override=base_config.pyright_project_override
        if base_config is not None
        else None,
    )
