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
    """

    name: str
    command: list[str]
    supports_fix: bool = False
    supports_path: bool = False
    supports_exclude: bool = False
    default_paths: list[str] = []

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
"""All 11 tool specifications in execution order."""

TOOLS_BY_NAME: dict[str, ToolSpec]
"""Tool specs keyed by name for fast lookup."""

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
    """

def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the lint pipeline (``python -m python_setup_lint.runner``)."""

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
    Each string describes a specific regression: exit-code change,
    output change, or missing baseline entry.

    Args:
        current: :class:`LintResult` list from current run.
        baseline_path: Path to a JSON file previously written by
            :func:`_capture_baseline`.
    """