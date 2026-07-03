# Violations-only baseline: flat records sorted by (tool, file, line, col).
from __future__ import annotations

import contextlib
import json
import os
import shutil
import tempfile
from typing import TYPE_CHECKING

import beartype

from ._record_types import Record
from .parsers import _RECORD_PARSERS
from .types import LintResult

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["_capture_baseline", "_diff_baseline"]


# ── Backward-compat exports (legacy stubs for external consumers) ──


_FALLBACK_TOOLS: set[str] = set()


@beartype.beartype
def peek_fallback_tools() -> frozenset[str]:
    return frozenset()


def _compare_sorted(
    a: list[Record], b: list[Record]
) -> tuple[list[Record], list[Record]]:
    """Re-export of :func:`_baseline_helpers._compare_sorted` for backwards compat.

    The new violations-only baseline uses a direct violation-list diff instead,
    but test code imported this from baseline before the refactor.

    Returns:
        A tuple ``(added, removed)`` of :class:`Record` lists.
    """
    from ._baseline_helpers import _compare_sorted as _cs

    return _cs(a, b)


# ── Core helpers ──────────────────────────────────────────────────


def _violation_sort_key(v: dict) -> tuple:
    """Sort key: (tool, file, line, col, rule).

    Returns:
        A tuple suitable for use as ``sorted()`` key.
    """
    tool = v.get("tool", "")
    file_k: tuple = (v["file"],) if v.get("file") is not None else ("",)
    line_k: tuple = (v["line"],) if v.get("line") is not None else (-1,)
    col_k: tuple = (v["col"],) if v.get("col") is not None else (-1,)
    rule = v.get("rule", "")
    return (tool, file_k, line_k, col_k, rule)


def _violation_tuple(v: dict) -> tuple:
    """Stable tuple for equality + multiset comparison.

    Returns:
        A ``tuple`` of (tool, file, line, col, rule, msg).
    """
    return (
        v.get("tool", ""),
        v.get("file") or "",
        v.get("line") or -1,
        v.get("col") or -1,
        v.get("rule", ""),
        v.get("msg", ""),
    )


def _compare_violation_lists(
    current: list[dict], saved: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Two-pointer diff on sorted flat violation lists.

    Args:
        current: Sorted list of current violation dicts.
        saved: Sorted list of saved violation dicts.

    Returns:
        A tuple ``(added, removed)`` where *added* are violations in
        *current* but not *saved*, and *removed* are violations in
        *saved* but not *current*.
    """
    added: list[dict] = []
    removed: list[dict] = []
    i = j = 0
    ci, sj = len(current), len(saved)
    while i < ci and j < sj:
        ca = _violation_tuple(current[i])
        sb = _violation_tuple(saved[j])
        if ca == sb:
            i += 1
            j += 1
        elif ca < sb:
            added.append(current[i])
            i += 1
        else:
            removed.append(saved[j])
            j += 1
    if i < ci:
        added.extend(current[i:])
    if j < sj:
        removed.extend(saved[j:])
    return added, removed


def _capture_one(r: LintResult) -> list[dict]:
    """Capture violations from one LintResult as flat records.

    Negative exit codes (signals) produce a __CRASH__ record that is
    never baseline-absorbable. Positive exit codes with a record parser
    produce parsed violations.

    Returns:
        A list of violation dicts with keys (tool, file, line, col, rule, msg).
        Empty list means no violations.
    """

    if r.exit_code < 0:
        return [{
            "tool": r.tool_name,
            "file": None,
            "line": None,
            "col": None,
            "rule": "__CRASH__",
            "msg": f"exit code {r.exit_code}",
        }]
    violations: list[dict] = []
    parser = _RECORD_PARSERS.get(r.tool_name)
    if parser is not None:
        violations.extend({
            "tool": r.tool_name,
            "file": rec.file,
            "line": rec.line,
            "col": rec.col,
            "rule": rec.rule,
            "msg": rec.msg,
        } for rec in parser(r.stdout or ""))
    return violations


def _capture_baseline(results: list[LintResult]) -> list[dict[str, object]]:
    """All violations as a flat list sorted by (tool, file, line, col, rule).

    Returns:
        A list of dicts with keys (tool, file, line, col, rule, msg).
    """

    all_violations: list[dict] = []
    for r in results:
        all_violations.extend(_capture_one(r))
    all_violations.sort(key=_violation_sort_key)
    return all_violations


def _write_baseline_if_modified(
    violations: list[dict[str, object]],
    baseline_path: Path,
    baseline_modified: bool,
) -> list[str] | None:
    """Atomically write baseline via temp file if modified.

    Returns:
        ``None`` on success, or a list containing one error string on failure.
    """

    if not baseline_modified:
        return None
    try:
        parent = baseline_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        tmp_path = tempfile.NamedTemporaryFile(dir=tempfile.gettempdir(), prefix="psl_baseline_", suffix=".json", delete=False).name  # noqa: SIM115  # pylint: disable=consider-using-with  # intentional: need delete=False + manual cleanup in finally
        try:
            with open(tmp_path, "w") as f:
                json.dump(violations, f, indent=2, sort_keys=True)
            shutil.move(tmp_path, str(baseline_path))
        finally:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
    except OSError as exc:  # pylint: disable=W9740  # best-effort baseline write fallback; logging would noise unavoidable IO degrade
        return [f"Cannot write baseline: {exc}"]
    return None


def _diff_baseline(  # pylint: disable=too-many-locals  # _diff_baseline needs several locals for the two-pointer diff, crash/add/remove separation; 20 would be cramped
    current: list[LintResult],
    baseline_path: Path,
) -> list[str]:
    """Compare current results against on-disk baseline of flat violation records.

    Returns:
        A list of violation strings. Empty when current output fully
        matches baseline. Each string describes a specific regression
        (additions or crashes). Removals silently update the baseline
        in-place and are not included in the return value.
    """

    if not baseline_path.exists():
        return [f"Baseline file not found: {baseline_path}"]

    try:
        with open(baseline_path) as f:
            saved: list[dict] = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:  # pylint: disable=W9740  # best-effort baseline read fallback; logging would noise unavoidable parse/IO degrade
        return [f"Cannot read baseline: {exc}"]

    current_violations = _capture_baseline(current)

    # Separate crash records — never baseline-absorbable.
    crash_records = [v for v in current_violations if v.get("rule") == "__CRASH__"]
    crashless_current = [v for v in current_violations if v.get("rule") != "__CRASH__"]

    # Strip any crash records from saved (legacy or pre-refactor artifacts).
    crashless_saved = [v for v in saved if v.get("rule") != "__CRASH__"]

    added, removed = _compare_violation_lists(
        sorted(crashless_current, key=_violation_sort_key),
        sorted(crashless_saved, key=_violation_sort_key),
    )

    violations: list[str] = []

    # Crashes are always violations.
    violations.extend(
        f"[{crash['tool']}] CRASH (exit={crash['msg'].replace('exit code ', '')})"
        for crash in crash_records
    )

    # Added = new/different violations.
    for v in added:
        loc = ""
        if v.get("file"):
            line_part = f":{v['line']}" if v.get("line") is not None else ""
            col_part = f":{v['col']}" if v.get("col") is not None else ""
            loc = f" @ {v['file']}{line_part}{col_part}"
        violations.append(f"[{v['tool']}] {v['rule']}: {v['msg']}{loc}")

    # Removed = shrinkage → update baseline silently.
    baseline_modified = bool(removed)
    if baseline_modified:
        removed_tuples = {_violation_tuple(v) for v in removed}
        new_saved = [
            v for v in crashless_saved if _violation_tuple(v) not in removed_tuples
        ]
        write_result = _write_baseline_if_modified(
            new_saved, baseline_path, True,
        )
        if write_result is not None:
            return write_result

    return violations
