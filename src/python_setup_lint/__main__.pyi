"""Stub for :mod:`python_setup_lint.__main__`.

Package entry point: delegates to runner CLI.
"""

from python_setup_lint.runner.types import RunnerConfig

def main(argv: list[str] | None = None, *, config: RunnerConfig | None = None) -> int:
    """CLI entry point for ``python -m python_setup_lint``."""
