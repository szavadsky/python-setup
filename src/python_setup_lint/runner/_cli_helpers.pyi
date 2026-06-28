"""Stub for :mod:`python_setup_lint.runner._cli_helpers`.

CLI helper functions for the lint pipeline.
"""

from .types import LintResult, ToolSpec

def _print_tool_notes(spec: ToolSpec, *, fix: bool, path: str | None, exclude: str | None) -> None: ...
def _handle_baseline(
    results: list[LintResult],
    baseline: str,
    *,
    overwrite_baseline: bool,
    overall_rc: int,
) -> int: ...
