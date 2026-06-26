"""CLI helper functions for the lint pipeline.

Extracted from cli.py to keep module under 500 lines.
"""

from __future__ import annotations

import json
from pathlib import Path

from .types import LintResult, ToolSpec


def _print_tool_notes(spec: ToolSpec, *, fix: bool, path: str | None, exclude: str | None) -> None:

    import sys

    if fix and not spec.supports_fix:
        print(
            f"  [{spec.name}] --fix: N/A (tool does not support autofix)",
            file=sys.stderr,
        )
    if path is not None and not spec.supports_path:
        print(
            f"  [{spec.name}] --path: N/A (tool does not support path scoping)",
            file=sys.stderr,
        )
    if exclude is not None and not spec.supports_exclude:
        print(
            f"  [{spec.name}] --exclude: N/A (tool does not support exclude)",
            file=sys.stderr,
        )


def _handle_baseline(
    results: list[LintResult],
    baseline: str,
    *,
    overwrite_baseline: bool,
    overall_rc: int,
) -> int:

    from python_setup_lint import runner as _pkg

    base_path = Path(baseline)
    if base_path.exists() and not overwrite_baseline:
        new_issues = _pkg._diff_baseline(results, base_path)
        if new_issues:
            print(f"\n{'=' * 60}")
            print("[baseline] New violations detected:")
            for issue in new_issues:
                print(f"  \u2022 {issue}")
            if overall_rc == 0:
                overall_rc = 1
        else:
            print(f"\n{'=' * 60}")
            print("[baseline] No new violations — output matches baseline")
            overall_rc = 0
    else:
        action = "Overwriting" if base_path.exists() else "Creating"
        print(f"\n{'=' * 60}")
        print(f"[baseline] {action} baseline \u2192 {baseline}")
        base_data = _pkg._capture_baseline(results)
        base_path.parent.mkdir(parents=True, exist_ok=True)
        with open(base_path, "w") as f:
            json.dump(base_data, f, indent=2, sort_keys=True)
        print(f"[baseline] Baseline saved ({len(base_data)} tool entries)")
        overall_rc = 0
    return overall_rc
