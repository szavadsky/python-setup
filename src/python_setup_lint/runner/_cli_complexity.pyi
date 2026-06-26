"""Stub for :mod:`python_setup_lint.runner._cli_complexity`.

Helper functions extracted from cli.py to reduce file size and complexity.
"""

import argparse
from pathlib import Path

from .types import RunnerConfig, ToolSpec

    """Apply ruff compose + pyright project overrides to config paths."""


    """Resolve which tools to run based on config override."""


    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    base_config: RunnerConfig | None = None,
) -> dict[str, Path]:
    """Parse --config TOOL=PATH arguments into a config_paths dict."""


    args: argparse.Namespace,
    config: RunnerConfig | None,
    cwd: Path,
    config_paths: dict[str, Path],
) -> int | None:
    """Print per-tool config origin and return 0 if --config-status, else None."""


    args: argparse.Namespace,
    *,
    base_config: RunnerConfig | None,
    cwd: Path,
    config_paths: dict[str, Path],
    cli_tools_override: list[str] | None,
) -> RunnerConfig:
    """Construct RunnerConfig from CLI args merged with caller-supplied base."""
