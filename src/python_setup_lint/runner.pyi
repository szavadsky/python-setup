"""Python CLI runner for the python-setup lint pipeline.

Replaces ``scripts/lint.sh``.  Runs all 11 lint steps sequentially with
optional path scoping, fix mode, baseline diffing, flexible failure
handling, and statistics aggregation.

CLI
---
::

    python -m python_setup_lint.runner            # all 11 steps, fail-fast
    python -m python_setup_lint.runner --path src/python_setup_lint  # scope
    python -m python_setup_lint.runner --fix       # apply autofixes
    python -m python_setup_lint.runner --baseline lint.baseline  # diff vs stored
    python -m python_setup_lint.runner --no-fail-fast            # run all, report aggregate
    python -m python_setup_lint.runner --exclude tests/          # exclude a path
    python -m python_setup_lint.runner --statistics              # per-rule violation counts
    python -m python_setup_lint.runner --statistics --format json  # machine-readable
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple

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
            runs all 11 default tools.
        secrets_baseline: Path (relative to ``cwd``) to the
            detect-secrets baseline file.
    """

    cwd: Path
    package_name: str | None = None
    default_py_dirs: list[str] | None = None
    tools_override: list[str] | None = None
    secrets_baseline: str = ".secrets.baseline"

TOOLS: list[ToolSpec]
"""All 11 tool specifications in execution order (built-ins)."""

TOOLS_BY_NAME: dict[str, ToolSpec]
"""Tool specs keyed by name for fast lookup (built-ins only)."""

LINT_TOOLS: list[ToolSpec]
"""Live registry of declared ``ToolSpec`` instances — built-ins plus any
extras registered via :func:`register_lint_tool`.  At import time it
mirrors :data:`TOOLS`.  ``run_lint`` iterates this list when no
``tools_override`` is supplied on the :class:`RunnerConfig`.

Use :data:`TOOLS` for the frozen built-in set; use :data:`LINT_TOOLS`
when iterating the live registry including extras.
"""

STRATEGIES: dict[str, LintTool]
"""Per-tool strategies keyed by tool name.

Built-in names are populated at import time from :data:`TOOLS`.
Extras registered via :func:`register_lint_tool` add entries here.
"""

PARSE_STRATEGIES: frozenset[str]
"""Closed enum — valid ``parse_strategy`` values for extra-tool entries."""

class LintTool:
    """Per-tool strategy for command construction + statistics.

    Subclasses override :meth:`build_command` /
    :meth:`statistics_flags` / :meth:`parse_statistics` to specialise
    per-tool behaviour.  The default implementations delegate to the
    module-level helpers (:func:`_build_command`,
    :func:`_build_statistics_flags`, :data:`_STATISTICS_PARSERS`) so
    built-in behaviour stays verbatim.

    Config-agnostic: the ``package_name is None`` skip for
    ``mypy.stubtest`` / ``pyright verify types`` stays in
    :func:`run_lint`, not here.
    """

    spec: ToolSpec

    def __init__(self, spec: ToolSpec) -> None: ...

    @property
    def name(self) -> str: ...

    def build_command(
        self,
        *,
        config: RunnerConfig,
        fix: bool = False,
        path: str | None = None,
        exclude: str | None = None,
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

class _StubtestLintTool(LintTool):
    """Strategy for ``mypy.stubtest`` — builds command from ``package_name`` + optional allowlist."""

class _VerifyTypesLintTool(LintTool):
    """Strategy for ``pyright verify types`` — builds command from ``package_name`` + optional project."""

class _DetectSecretsLintTool(LintTool):
    """Strategy for ``detect-secrets`` — wraps in ``bash -c`` pipeline over git-ls-files."""

class ExtraToolsConfigError(Exception):
    """Raised on a malformed ``[[tool.python-setup-lint.extra-tools]]`` entry."""

    location: str
    reason: str

    def __init__(self, location: str, reason: str) -> None: ...

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
    """

def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the lint pipeline (``python -m python_setup_lint.runner``).

    The runtime also accepts a keyword-only ``config: RunnerConfig | None``
    so thin wrappers can pre-build a configuration. Kept out of the stub
    to preserve baseline-diff semantics; consultant.mcp consumer
    ``_lint_scripts.py`` only imports :class:`RunnerConfig` + :func:`run_lint`
    (not :func:`main`), so the runtime overload is safe at the call sites
    that DO use it (test files). See T4 notes.
    """

# ── Private helpers (docstrings live here per CodingRules.md) ─────

def _capture_baseline(results: list[LintResult]) -> list[dict[str, Any]]:
    """Capture structured baseline data from tool results.

    Each entry contains the tool name, exit code, and one of:
    - ``output`` (raw stdout) for non-JSON tools
    - ``diagnostics`` (parsed JSON) for pyright and rumdl check.

    Args:
        results: :class:`LintResult` list from one ``run_lint`` invocation.
    """

def _diff_baseline(current: list[LintResult], baseline_path: Path) -> list[str]:
    """Compare current results against saved baseline.

    Returns empty list when current output fully matches baseline.
    Each string describes a specific regression (additions only).
    Removals (shrinkage) are silently auto-recorded by rewriting the
    baseline in-place.

    Args:
        current: :class:`LintResult` list from current run.
        baseline_path: Path to a JSON file previously written by
            :func:`_capture_baseline`.
    """

def _sort_counts(
    counts: list[ViolationCount],
    *,
    sort_by_rule: bool = False,
) -> list[ViolationCount]:
    """Return *counts* in the requested sort order: by count (default) or by rule."""

def _print_statistics_grouped(
    counts: list[ViolationCount],
    *,
    group: str = "tool",
    sort_by_rule: bool = False,
) -> None:
    """Print violation counts grouped by *group* key (tool, rule, or file)."""