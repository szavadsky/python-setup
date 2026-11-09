"""Stub for :mod:`python_setup_lint.runner.dispatch`.

Registry surface for the 14 built-in tools: the frozen ``ToolSpec`` table,
registry-derived constant sets, the live ``LINT_TOOLS`` registry, and
``register_lint_tool``.  Strategy classes live in
:mod:`python_setup_lint.runner._strategies` and are re-exported here for
compatibility.
"""

from collections.abc import Callable

from ._strategies import GenericLintTool as GenericLintTool
from ._strategies import LintTool as LintTool
from .types import ToolSpec

TOOLS: list[ToolSpec]
"""All 14 tool specifications in execution order (built-ins)."""

TOOLS_BY_NAME: dict[str, ToolSpec]
"""Tool specs keyed by name for fast lookup (built-ins only)."""

EXPECTED_TOOL_NAMES: frozenset[str]
"""Names of all 14 built-in tools, derived from :data:`TOOLS`."""

FORMATTER_ONLY: frozenset[str]
"""Built-ins that only format (``ruff format``); exempt from parser coverage."""

STATISTICS_PARSER_TOOLS: frozenset[str]
"""Built-ins with a statistics parser in
:data:`python_setup_lint.runner.parsers._STATISTICS_PARSERS`."""

RECORD_PARSER_TOOLS: frozenset[str]
"""Built-ins with a per-violation record parser in
:data:`python_setup_lint.runner.parsers._RECORD_PARSERS`."""

RECORDLESS_TOOLS: frozenset[str]
"""Built-ins without a record parser: ``tach check``, ``mypy.stubtest``,
``pyright verify types``, ``detect-secrets``, and ``ruff format``."""

LINT_TOOLS: list[ToolSpec]
"""Live registry of declared ``ToolSpec`` instances — built-ins plus any
extras registered via :func:`register_lint_tool`.  At import time it
mirrors :data:`TOOLS`.  ``run_lint`` iterates this list when no
``tools_override`` is supplied on the :class:`RunnerConfig`.
"""

STRATEGIES: dict[str, LintTool]
"""Per-tool strategies keyed by tool name.

Built-in names are populated at import time from :data:`TOOLS`.
Extras registered via :func:`register_lint_tool` add entries here.
"""

def register_lint_tool(
    tool: ToolSpec,
    *,
    statistics_flag: list[str] | None = None,
    parser: Callable[..., list[tuple[str, int]]] | None = None,
    config_flag: list[str] | None = None,
) -> None:
    """Append *tool* to :data:`LINT_TOOLS` and register its strategy.

    For names not already in :data:`STRATEGIES`, a
    :class:`GenericLintTool` is synthesised from ``tool`` + the three
    declarative fields and registered under
    ``STRATEGIES[tool.name]``.  Built-in names keep their strategies; the
    matching :data:`LINT_TOOLS` entry is updated.

    Idempotent per ``tool.name`` — a re-call with the same name is an
    update-in-place (no duplicate append).
    """

def _strategy_for(name: str, spec: ToolSpec) -> LintTool:
    """Return a cached or new strategy for *spec*."""
