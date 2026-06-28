"""Core data types for the lint pipeline.

Pure data containers — no subprocess, no disk, no dispatch logic.  Kept in
a dedicated module so the rest of the pipeline can depend on a stable
contract without pulling in ``argparse`` / ``subprocess`` transitively.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["LintResult", "RunnerConfig", "ToolSpec", "ViolationCount"]


class ToolSpec(NamedTuple):
    """Specification for a single lint tool.

    Attributes:
        name: Human-readable label for the tool.
        command: Base command list (no paths, no flag overrides).
        supports_fix: Whether the tool accepts ``--fix``.
        supports_path: Whether the tool accepts a positional path.
        supports_exclude: Whether the tool accepts ``--exclude`` / ``-e``.
        default_paths: Paths to use when no ``--path`` is given.
        fix_flags: Extra CLI flags to append when ``--fix`` is active.
        exclude_flag: CLI flag name for exclusion (default ``--exclude``).
    """

    name: str
    command: list[str]
    supports_fix: bool = False
    supports_path: bool = False
    supports_exclude: bool = False
    default_paths: list[str] = []
    fix_flags: tuple[str, ...] = ("--fix",)
    exclude_flag: str = "--exclude"


@dataclass
class LintResult:
    """Result of running a single lint tool."""

    tool_name: str
    exit_code: int
    stdout: str
    stderr: str
    elapsed: float


@dataclass
class ViolationCount:
    """Aggregated violation count for a single rule in a single tool."""

    tool: str
    rule: str
    count: int

    def __lt__(self, other: ViolationCount) -> bool:
        return (-self.count, self.tool, self.rule) < (
            -other.count,
            other.tool,
            other.rule,
        )


@dataclass
class RunnerConfig:
    """Project-level configuration for the lint runner.

    Attributes:
        cwd: Working directory — all path resolution is relative to this.
        package_name: Package name passed to ``mypy.stubtest`` and
            ``pyright verifytypes``.  ``None`` skips those tools.
        default_py_dirs: Default directories for pylint ``_find_py_files``
            discovery when no ``--path`` is given.
        tools_override: Optional list of tool names to run.  ``None``
            runs all 11 default tools.  Tool names map to internal
            :class:`ToolSpec` entries via ``TOOLS_BY_NAME`` (built-ins) and
            the live :data:`python_setup_lint.runner.dispatch.LINT_TOOLS`
            registry (built-ins + extras).  Unknown names raise
            :class:`python_setup_lint.runner.extra_tools.ExtraToolsConfigError`
            (T8 fail-fast) rather than silently running a subset — a typo in
            a tool name is treated as malformed configuration.
        secrets_baseline: Path (relative to ``cwd``) to the
            detect-secrets baseline file.
        config_paths: Optional mapping of tool identifiers to config file
            paths.  Canonical keys are the built-in :class:`ToolSpec`
            labels: ``ruff check``, ``mypy``, ``pylint``,
            ``pyright check``, ``rumdl check``, ``ty check`` (matching the
            names used in :func:`python_setup_lint.runner.cmd_build._config_flag_for`
            and the strategy subclasses).  The CLI ``--config TOOL=PATH``
            flag additionally accepts short aliases (``ruff``, ``pyright``,
            ``rumdl``, ``ty``, plus the canonical labels) which it normalises
            to the canonical label — unrecognised keys are rejected with a
            non-zero ``SystemExit`` and a message naming the offending key
            (T8 fail-fast).

            * ``ruff check``: ``--config <path>``
            * ``mypy``: ``--config-file <path>``
            * ``pylint``: ``--rcfile <path>``
            * ``pyright check``: ``--project <path>``
            * ``rumdl check``: ``--config <path>``
            * ``ty check``: ``--config <path>``
        ruff_project_overrides: When ``True``, compose a temp
            ``ruff.toml`` that ``extend``s the shared
            ``config_paths["ruff check"]`` config + copies the project
            ``pyproject.toml`` ``[tool.ruff.lint.flake8-tidy-imports].banned-api``
            and ``[tool.ruff.lint.per-file-ignores]`` stanzas
            (consultant.mcp's hand-rolled merge, ported verbatim into
            :func:`python_setup_lint.runner.cmd_build._compose_ruff_config`).
            The composed path replaces ``config_paths["ruff check"]``
            before the ruff command is built.  Defaults to ``False`` so
            python-setup's own run is unchanged.
        pyright_project_override: When set, takes precedence over
            ``config_paths["pyright check"]`` — passed to pyright as
            ``--project <path>``.  Consultant.mcp points this at
            ``cwd / "pyproject.toml"`` so pyright does cwd-relative venv
            discovery (the shipped ``pyrightconfig.json`` declares
            ``venvPath: "."`` resolved relative to the config FILE → wrong
            venv → runner timeout).  Defaults to ``None`` so python-setup's
            own run uses the shipped config unchanged.
    """

    cwd: Path
    package_name: str | None = None
    default_py_dirs: list[str] | None = None
    tools_override: list[str] | None = None
    secrets_baseline: str = ".secrets.baseline"
    config_paths: dict[str, Path] | None = None
    ruff_project_overrides: bool = False
    pyright_project_override: Path | None = None

    def __post_init__(self) -> None:
        if self.default_py_dirs is None:
            self.default_py_dirs = ["src"]
        if self.config_paths is None:
            self.config_paths = {}
