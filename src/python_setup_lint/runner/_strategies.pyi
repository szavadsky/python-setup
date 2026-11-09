"""Stub for :mod:`python_setup_lint.runner._strategies`.

Per-tool strategy classes split out of :mod:`python_setup_lint.runner.dispatch`
(T-milestone M3) so every runner module stays within the 500-line budget.
``dispatch`` owns the ``ToolSpec`` registry and re-exports these classes;
this module is the single source for strategy behaviour.  Private subclasses
are declared because ``dispatch`` imports them for its runtime re-export
surface.
"""

from collections.abc import Callable

from .types import RunnerConfig, ToolSpec

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
    def build_format_command(
        self,
        *,
        config: RunnerConfig,
        _path: str | None = None,
        _exclude: str | None = None,
    ) -> list[str]:
        """Mutating command used only by the ``--fix`` phase-1a format pass."""
    def statistics_flags(self) -> list[str]: ...
    def parse_statistics(self, stdout: str, stderr: str) -> list[tuple[str, int]]: ...

class _StubtestLintTool(LintTool):
    def build_command(
        self,
        *,
        config: RunnerConfig,
        _fix: bool = False,
        _path: str | None = None,
        _exclude: str | None = None,
    ) -> list[str]: ...

class _VerifyTypesLintTool(LintTool):
    def build_command(
        self,
        *,
        config: RunnerConfig,
        _fix: bool = False,
        _path: str | None = None,
        _exclude: str | None = None,
    ) -> list[str]: ...

class _DetectSecretsLintTool(LintTool):
    def build_command(
        self,
        *,
        config: RunnerConfig,
        _fix: bool = False,
        _path: str | None = None,
        _exclude: str | None = None,
    ) -> list[str]: ...

class _PylintLintTool(LintTool):
    def build_command(
        self,
        *,
        config: RunnerConfig,
        _fix: bool = False,
        _path: str | None = None,
        _exclude: str | None = None,
    ) -> list[str]: ...

class _PylintPyiLintTool(LintTool):
    def build_command(
        self,
        *,
        config: RunnerConfig,
        _fix: bool = False,
        _path: str | None = None,
        _exclude: str | None = None,
    ) -> list[str]: ...

class _PylintTestsLintTool(LintTool):
    def build_command(
        self,
        *,
        config: RunnerConfig,
        _fix: bool = False,
        _path: str | None = None,
        _exclude: str | None = None,
    ) -> list[str]: ...

class _RuffFormatLintTool(LintTool):
    def build_command(
        self,
        *,
        config: RunnerConfig,
        _fix: bool = False,
        _path: str | None = None,
        _exclude: str | None = None,
    ) -> list[str]: ...
    def build_format_command(
        self,
        *,
        config: RunnerConfig,
        _path: str | None = None,
        _exclude: str | None = None,
    ) -> list[str]: ...

_STRATEGY_CLASSES: dict[str, type[LintTool]]

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
