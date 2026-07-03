
from __future__ import annotations

from pathlib import Path

from .types import LintResult, ToolSpec  # TYPE_CHECKING-only import; not available at runtime


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
    cwd: Path | None = None,
) -> int:

    from .baseline import _capture_baseline, _diff_baseline, _write_baseline_if_modified

    base_path = Path(baseline)
    if base_path.exists() and not overwrite_baseline:
        new_issues = _diff_baseline(results, base_path, cwd=cwd)
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
        base_data = _capture_baseline(results, cwd=cwd)
        err = _write_baseline_if_modified(base_data, base_path, baseline_modified=True)
        if err:
            print(f"[baseline] {'; '.join(err)}")
            return 1
        print(f"[baseline] Baseline saved ({len(base_data)} violation records)")
        overall_rc = 0
    return overall_rc
