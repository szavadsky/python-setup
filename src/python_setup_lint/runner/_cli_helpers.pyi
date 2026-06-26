"""Stub for :mod:`python_setup_lint.runner._cli_helpers`.

CLI helper functions for the lint pipeline.
"""

from .types import LintResult, ToolSpec

    results: list[LintResult],
    baseline: str,
    *,
    overwrite_baseline: bool,
    overall_rc: int,
) -> int: ...
