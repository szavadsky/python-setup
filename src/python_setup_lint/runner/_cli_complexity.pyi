"""Stub for :mod:`python_setup_lint.runner._cli_complexity`.

Helper functions extracted from cli.py to reduce file size and complexity.
"""

import argparse
from pathlib import Path

from .types import RunnerConfig, ToolSpec

def _apply_config_overrides(config: RunnerConfig) -> RunnerConfig:
    """Apply ruff compose + pyright project overrides to config paths."""

def _select_tools(config: RunnerConfig) -> list[ToolSpec]:
    """Resolve which tools to run based on config override."""

def _parse_config_args(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    base_config: RunnerConfig | None = None,
) -> dict[str, Path]:
    """Parse --config TOOL=PATH arguments into a config_paths dict."""

def _handle_config_status(
    args: argparse.Namespace,
    config: RunnerConfig | None,
    cwd: Path,
    config_paths: dict[str, Path],
) -> int | None:
    """Print per-tool config origin and return 0 if --config-status, else None."""

def _build_runner_config(
    args: argparse.Namespace,
    *,
    base_config: RunnerConfig | None,
    cwd: Path,
    config_paths: dict[str, Path],
    cli_tools_override: list[str] | None,
) -> RunnerConfig:
    """Construct RunnerConfig from CLI args merged with caller-supplied base."""
