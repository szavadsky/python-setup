"""Stub for :mod:`python_setup_lint.runner.cli`.

Lint pipeline orchestration (``run_lint``) + CLI entry point (``main``).
Includes the T8 fail-fast CLI ``--config`` key set + aliases.
"""

from .types import RunnerConfig

_CONFIG_KEY_ALIASES: dict[str, str]
"""Short alias → canonical ``--config TOOL=PATH`` label (``ruff`` → ``ruff check``)."""

_SUPPORTED_CONFIG_KEYS: frozenset[str]
"""Closed ``--config`` key set — canonical labels + short aliases.  Unknown
ids exit non-zero via ``argparse`` ``parser.error`` (T8 fail-fast)."""

def run_lint(
    *,
    config: RunnerConfig | None = None,
    path: str | None = None,
    fix: bool = False,
    baseline: str | None = None,
    exclude: str | None = None,
    no_fail_fast: bool = False,
    statistics: bool = False,
    statistics_format: str = "table",
    overwrite_baseline: bool = False,
    group: str = "none",
    sort_by_rule: bool = False,
) -> int:
    """Run the full lint pipeline.

    Returns 0 if all tools pass, non-zero on any failure.

    Args:
        config: Project-level :class:`RunnerConfig`.  Defaults to
            ``RunnerConfig(cwd=Path.cwd())`` when ``None``.
        path: Scope to a specific file or directory.
        fix: Apply autofixes (ruff, rumdl, ty).
        baseline: Path to a baseline JSON file. Created on first run,
            compared on subsequent runs.
        exclude: Exclude a file or directory pattern from supported tools.
        no_fail_fast: Run all tools even if some fail, then report
            aggregate exit code.
        statistics: Collect and display per-rule violation counts.
        statistics_format: ``\"table\"`` (default) or ``\"json\"``.
        overwrite_baseline: Force overwrite of existing baseline file
            (used with ``--baseline``).
        group: Group statistics output (``\"none\"``, ``\"tool\"``, ``\"rule\"``, ``\"file\"``).
        sort_by_rule: Sort by rule name instead of count.

    Raises:
        python_setup_lint.runner.extra_tools.ExtraToolsConfigError: on an
            unknown ``tools_override`` name (T8 fail-fast) or a malformed
            pyproject extra-tools entry.
    """

def main(argv: list[str] | None = None, *, config: RunnerConfig | None = None) -> int:
    """CLI entry point for ``uv run lint``.

    When *config* is provided, CLI flags still override the pre-built
    configuration (cwd, package-name, default-py-dirs, tools, config-paths
    can all be set on the command line).  This lets thin wrappers
    (``consultant_mcp._lint_scripts:main``) construct a default
    configuration while still exposing the full CLI surface.
    """
