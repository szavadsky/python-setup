"""Stub for :mod:`python_setup_lint.runner.types`.

Core data containers — ``ToolSpec`` (NamedTuple), ``LintResult``,
``ViolationCount``, ``RunnerConfig``.  No side effects on import.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

class ToolSpec(NamedTuple):
    """Specification for a single lint tool.

    Attributes:
        name: Human-readable label for the tool.
        command: Base command list (no paths, no flag overrides).
        supports_fix: Whether the tool accepts ``--fix``.
        supports_path: Whether the tool accepts a positional path.
        supports_exclude: Whether the tool accepts ``--exclude`` / ``-e``.
        default_paths: Paths to use when no ``--path`` is given.
        fix_flags: CLI flag(s) to append when ``--fix`` is active.
        exclude_flag: CLI flag name for exclusion.
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
    """Result of running a single lint tool.

    Attributes:
        tool_name: Label of the tool that produced this result.
        exit_code: Process exit code (0 = success).
        stdout: Captured standard output.
        stderr: Captured standard error.
        elapsed: Wall-clock seconds the tool took to run.
    """

    tool_name: str
    exit_code: int
    stdout: str
    stderr: str
    elapsed: float

class ViolationCount:
    """Aggregated violation count for a single rule in a single tool.

    Attributes:
        tool: Human-readable tool label.
        rule: Rule identifier / error code.
        count: Number of occurrences.
    """

    tool: str
    rule: str
    count: int

    def __lt__(self, other: ViolationCount) -> bool: ...

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
            runs all 11 default tools.  Unknown names raise
            :class:`python_setup_lint.runner.extra_tools.ExtraToolsConfigError`
            (T8 fail-fast) rather than silently running a subset.
        secrets_baseline: Path (relative to ``cwd``) to the
            detect-secrets baseline file.
        config_paths: Optional mapping of tool identifiers to config file
            paths.  Canonical keys are the built-in :class:`ToolSpec`
            labels (``ruff check``, ``mypy``, ``pylint``, ``pyright check``,
            ``rumdl check``, ``ty check``); the CLI ``--config`` flag
            additionally accepts short aliases (``ruff``, ``pyright``,
            ``rumdl``, ``ty``) which it normalises to the canonical label
            (T8 fail-fast rejects unrecognised keys with non-zero
            ``SystemExit``).
        ruff_project_overrides: When ``True``, compose a temp
            ``ruff.toml`` that ``extend``s the shared
            ``config_paths["ruff check"]`` config + copies the project
            ``pyproject.toml`` ``[tool.ruff.lint.flake8-tidy-imports].banned-api``
            and ``[tool.ruff.lint.per-file-ignores]`` stanzas (port of
            consultant.mcp's hand-rolled merge into
            :func:`python_setup_lint.runner.cmd_build._compose_ruff_config`).
            The composed path replaces ``config_paths["ruff check"]``
            before the ruff command is built.  Defaults to ``False`` so
            python-setup's own run is unchanged.
        pyright_project_override: When set, takes precedence over
            ``config_paths["pyright check"]`` — passed to pyright as
            ``--project <path>``.  Consultant.mcp points this at
            ``cwd / "pyproject.toml"`` so pyright does cwd-relative venv
            discovery (shipped ``pyrightconfig.json`` resolves relative to
            the config FILE → wrong venv → runner timeout).  Defaults to
            ``None`` so python-setup's own run uses the shipped config.
    """

    cwd: Path
    package_name: str | None = None
    default_py_dirs: list[str] | None = None
    tools_override: list[str] | None = None
    secrets_baseline: str = ".secrets.baseline"
    config_paths: dict[str, Path] | None = None
    ruff_project_overrides: bool = False
    pyright_project_override: Path | None = None

    def __post_init__(self) -> None: ...
