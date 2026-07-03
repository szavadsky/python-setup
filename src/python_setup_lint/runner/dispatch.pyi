"""Stub for :mod:`python_setup_lint.runner.dispatch`.

Six built-ins override ``build_command`` for tool-specific command shapes
(``mypy.stubtest``, ``pyright verify types``, ``detect-secrets``, ``pylint``);
the rest inherit the default delegation to
:mod:`python_setup_lint.runner.cmd_build`.
"""

from collections.abc import Callable

from .types import RunnerConfig, ToolSpec

TOOLS: list[ToolSpec]
"""All 13 tool specifications in execution order (built-ins)."""

TOOLS_BY_NAME: dict[str, ToolSpec]
"""Tool specs keyed by name for fast lookup (built-ins only)."""

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

class LintTool:
    """Per-tool strategy for command construction + statistics.

    Subclasses override :meth:`build_command` /
    :meth:`statistics_flags` / :meth:`parse_statistics` to specialise
    per-tool behaviour.  The default implementations delegate to the
    module-level helpers (:func:`python_setup_lint.runner.cmd_build._build_command`,
    :func:`python_setup_lint.runner.cmd_build._build_statistics_flags`,
    :data:`python_setup_lint.runner.parsers._STATISTICS_PARSERS`) so
    built-in behaviour stays verbatim.

    Config-agnostic: the ``package_name is None`` skip for
    ``mypy.stubtest`` / ``pyright verify types`` stays in
    :func:`python_setup_lint.runner.cli.run_lint`, not here.
    """

    spec: ToolSpec

    def __init__(self, spec: ToolSpec) -> None: ...
    @property
    def name(self) -> str: ...
    def build_command(
        self,
        *,
        config: RunnerConfig,
        _fix: bool = False,
        _path: str | None = None,
        _exclude: str | None = None,
    ) -> list[str]: ...
    def statistics_flags(self) -> list[str]: ...
    def parse_statistics(self, stdout: str, stderr: str) -> list[tuple[str, int]]: ...


class GenericLintTool(LintTool):
    """Minimal strategy for extras registered via :func:`register_lint_tool`.

    Carries three optional declarative fields supplied at registration
    (``statistics_flag``, ``parser``, ``config_flag``).  Unset fields
    fall back to the generic module-level lookups.  Built-ins keep their
    own strategies; extras land here.
    """

    def __init__(
        self,
        spec: ToolSpec,
        *,
        statistics_flag: list[str] | None = None,
        parser: Callable[..., list[tuple[str, int]]] | None = None,
        config_flag: list[str] | None = None,
    ) -> None: ...


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
