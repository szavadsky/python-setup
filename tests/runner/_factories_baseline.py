"""Baseline-diff test data for python-setup runner tests.

Moved from ``_factories.py`` to keep each file under 500 lines (pylint C0302).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from python_setup_lint.runner.types import LintResult

_p = pytest.param


def find_tool_entry(entries: list[dict[str, Any]], tool: str) -> dict[str, Any]:
    """Return the FIRST baseline entry whose ``tool`` field equals *tool* (asserts at least one)."""
    matches = [e for e in entries if e.get("tool") == tool]
    assert matches, f"No baseline entry for tool {tool!r} in {entries!r}"
    return matches[0]


def baseline_entry_for_tool(entries: list[dict[str, Any]], tool: str) -> dict[str, Any]:
    """Return the first baseline entry whose ``tool`` equals *tool* (asserts at least one)."""
    return find_tool_entry(entries, tool)


# ── ``_diff_baseline`` invariant matrix ────────────────────────────

DIFF_BASELINE_CASES: list[object] = [
    # 1. Saved has 2 ruff entries (a, b), current has 1 ruff entry (a) -> auto-shrink removes b
    _p(
        [
            {"tool": "ruff check", "file": "src/a.py", "line": 1, "col": 1,
             "rule": "E001", "msg": "error A"},
            {"tool": "ruff check", "file": "src/b.py", "line": 2, "col": 2,
             "rule": "E002", "msg": "error B"},
        ],
        {"ruff check": "src/a.py:1:1: E001 error A"},
        "no_violations",
        "ruff_shrunk_b_removed",
        id="pure_shrinkage_auto_records",
    ),
    # 2. Saved has 1 ruff entry (a), current has 2 (a, b) -> b flagged as addition
    _p(
        [{"tool": "ruff check", "file": "src/a.py", "line": 1, "col": 1,
          "rule": "E001", "msg": "error A"}],
        {"ruff check": "src/a.py:1:1: E001 error A\nsrc/b.py:2:2: E002 error B"},
        "E002",
        "no_post",
        id="pure_addition_flags_regression",
    ),
    # 3. Saved has a, b; current has a, c -> c added (flagged), b removed (shrunk)
    _p(
        [
            {"tool": "ruff check", "file": "src/a.py", "line": 1, "col": 1,
             "rule": "E001", "msg": "error A"},
            {"tool": "ruff check", "file": "src/b.py", "line": 2, "col": 2,
             "rule": "E002", "msg": "error B"},
        ],
        {"ruff check": "src/a.py:1:1: E001 error A\nsrc/c.py:3:3: E003 error C"},
        "E003",
        "b_removed_c_not_added",
        id="mixed_shrinkage_and_addition",
    ),
    # 4. Saved has W0611, C0114; current has W0611 -> C0114 shrunk
    _p(
        [
            {"tool": "pylint", "file": "src/a.py", "line": 1, "col": 1,
             "rule": "unused-import", "msg": "unused-import"},
            {"tool": "pylint", "file": "src/b.py", "line": 2, "col": 2,
             "rule": "missing-module-docstring", "msg": "missing-module-docstring"},
        ],
        {"pylint": "src/a.py:1:1: W0611: unused-import (unused-import)"},
        "no_violations",
        "c0114_removed",
        id="pylint_shrinkage_auto_records",
    ),
    # 5. Saved has mypy and ruff entries; current has only ruff -> mypy removed
    _p(
        [
            {"tool": "ruff check", "file": "src/a.py", "line": 1, "col": 1,
             "rule": "E001", "msg": "error A"},
            {"tool": "mypy", "file": "src/b.py", "line": 2, "col": None,
             "rule": "misc", "msg": "error B"},
        ],
        {"ruff check": "src/a.py:1:1: E001 error A"},
        "no_violations",
        "mypy_removed",
        id="tool_removed_shrinkage_auto_records",
    ),
    # 6. Saved has pylint W0611; current has W0611 + C0114 -> added flagged
    _p(
        [{"tool": "pylint", "file": "src/a.py", "line": 1, "col": 1,
          "rule": "unused-import", "msg": "unused-import"}],
        {"pylint": "src/a.py:1:1: W0611: unused-import (unused-import)\n"
                   "src/b.py:2:2: C0114: missing-module-docstring (missing-module-docstring)"},
        "missing-module-docstring",
        "no_post",
        id="pylint_addition_flags_regression",
    ),
    # 7. Saved has MD012 and MD013; current has only MD012 -> MD013 shrunk
    _p(
        [
            {"tool": "rumdl check", "file": "src/a.md", "line": 1, "col": 1,
             "rule": "MD012", "msg": "No multiple blanks"},
            {"tool": "rumdl check", "file": "src/b.md", "line": 3, "col": 1,
             "rule": "MD013", "msg": "Line too long"},
        ],
        {"rumdl check": "src/a.md:1:1: [MD012] No multiple blanks"},
        "no_violations",
        "md013_removed",
        id="rumdl_shrinkage_auto_records_ignoring_timing",
    ),
    # 8. Saved has mypy record, current has empty stdout -> mypy entry shrunk
    _p(
        [{"tool": "mypy", "file": "src/a.py", "line": 1, "col": None,
          "rule": "some-code", "msg": "error A"}],
        {"mypy": ""},
        "no_violations",
        "no_post",
        id="output_to_empty_shrinkage",
    ),
    # 9. Trailing whitespace normalization: saved has 2 records matching current stdout
    _p(
        [
            {"tool": "mypy", "file": "src/a.py", "line": 1, "col": None,
             "rule": "some-code", "msg": "error A"},
            {"tool": "mypy", "file": "src/b.py", "line": 2, "col": None,
             "rule": "some-code", "msg": "error B"},
        ],
        {"mypy": "src/a.py:1: error: error A  [some-code]\n"
                 "src/b.py:2: error: error B  [some-code]"},
        "no_violations",
        "no_post",
        id="whitespace_normalization_d6",
    ),
    # 10. Ordering insensitive: saved has a, b; current has b, a -> no violations
    _p(
        [
            {"tool": "ruff check", "file": "src/a.py", "line": 1, "col": 1,
             "rule": "E001", "msg": "error A"},
            {"tool": "ruff check", "file": "src/b.py", "line": 2, "col": 2,
             "rule": "E002", "msg": "error B"},
        ],
        {"ruff check": "src/b.py:2:2: E002 error B\nsrc/a.py:1:1: E001 error A"},
        "no_violations",
        "no_post",
        id="ruff_ordering_insensitive",
    ),
    # 11. Saved has mypy and ruff; current has only ruff -> all mypy removed, 1 ruff remains
    _p(
        [
            {"tool": "mypy", "file": "src/a.py", "line": 1, "col": None,
             "rule": "some-code", "msg": "error A"},
            {"tool": "ruff check", "file": "src/a.py", "line": 1, "col": 1,
             "rule": "E001", "msg": "error A"},
        ],
        {"ruff check": "src/a.py:1:1: E001 error A"},
        "no_violations",
        "all_mypy_dupes_removed",
        id="duplicate_tool_in_baseline_d3",
    ),
]


# Per-row post-diff baseline assertion dispatch table.
def _entries_for_tool(entries: list[dict[str, Any]], tool: str) -> list[dict[str, Any]]:
    return [e for e in entries if e["tool"] == tool]


def _assert_removed(entries: list[dict[str, Any]], tool: str) -> None:
    assert not _entries_for_tool(entries, tool), (
        f"{tool!r} should be removed from {entries!r}"
    )


def _no_op(_reloaded: list[dict[str, Any]]) -> None: ...


def _ruff_shrunk_b_removed(reloaded: list[dict[str, Any]]) -> None:
    """Assert no ruff record with file=src/b.py in the baseline."""
    ruff = _entries_for_tool(reloaded, "ruff check")
    assert not any(r.get("file") == "src/b.py" for r in ruff), (
        f"src/b.py should be removed from ruff records: {ruff!r}"
    )


def _b_removed_c_not_added(reloaded: list[dict[str, Any]]) -> None:
    """Assert no ruff record with file src/b.py or src/c.py."""
    ruff = _entries_for_tool(reloaded, "ruff check")
    assert not any(r.get("file") in ("src/b.py", "src/c.py") for r in ruff), (
        f"src/b.py and src/c.py should be absent: {ruff!r}"
    )


def _c0114_removed(reloaded: list[dict[str, Any]]) -> None:
    """Assert no pylint record with rule=missing-module-docstring."""
    pylint = _entries_for_tool(reloaded, "pylint")
    assert not any(r.get("rule") == "missing-module-docstring" for r in pylint), (
        f"missing-module-docstring should be removed: {pylint!r}"
    )


def _mypy_removed(reloaded: list[dict[str, Any]]) -> None:
    _assert_removed(reloaded, "mypy")
    assert len(reloaded) == 1 and reloaded[0]["tool"] == "ruff check"


def _md013_removed(reloaded: list[dict[str, Any]]) -> None:
    """Assert no rumdl record with rule=MD013."""
    rumdl = _entries_for_tool(reloaded, "rumdl check")
    assert not any(r.get("rule") == "MD013" for r in rumdl), (
        f"MD013 should be removed: {rumdl!r}"
    )


def _all_mypy_dupes_removed(reloaded: list[dict[str, Any]]) -> None:
    _assert_removed(reloaded, "mypy")
    assert len(_entries_for_tool(reloaded, "ruff check")) == 1


DIFF_BASELINE_POST_ASSERTS: dict[str, Callable[..., None]] = {
    "ruff_shrunk_b_removed": _ruff_shrunk_b_removed,
    "b_removed_c_not_added": _b_removed_c_not_added,
    "c0114_removed": _c0114_removed,
    "mypy_removed": _mypy_removed,
    "md013_removed": _md013_removed,
    "all_mypy_dupes_removed": _all_mypy_dupes_removed,
    "no_post": _no_op,
}


def build_current_results(
    saved_baseline: dict[str, Any] | list[dict[str, Any]], current_map: dict[str, Any]
) -> list[LintResult]:
    """Construct ``LintResult`` list from a matrix row's compact ``current_map``."""
    from python_setup_lint.testing import make_lint_result

    saved_list = (
        [saved_baseline] if isinstance(saved_baseline, dict) else saved_baseline
    )
    seen: dict[str, object] = {}
    for entry in saved_list:
        tool = entry["tool"]
        if tool in current_map and tool not in seen:
            seen[tool] = current_map[tool]
    current: list[LintResult] = []
    for tool, value in seen.items():
        if isinstance(value, (dict, list)):
            current.append(make_lint_result(tool_name=tool, stdout=json.dumps(value)))
        else:
            current.append(make_lint_result(tool_name=tool, stdout=str(value)))
    return current


def diff_violation_kind(violations: list[str], want: str) -> None:
    """Assert *want* substring is in any violation (case-insensitive)."""
    lowered = [v.lower() for v in violations]
    assert any(want.lower() in v for v in lowered), (
        f"Expected {want!r} in violations; got {violations!r}"
    )


def _make_result(tool_name: str, exit_code: int = 0, stdout: str = "") -> LintResult:
    """Lazy make_lint_result wrapper (avoids eager import of testing module)."""
    from python_setup_lint.testing import make_lint_result

    return make_lint_result(tool_name=tool_name, exit_code=exit_code, stdout=stdout)


# ── _diff_baseline edge-case tables ────────────────────────────────

DIFF_EDGE_CASES: list[object] = [
    # Saved and current produce identical records -> no violations
    _p(
        [{"tool": "ruff check", "file": "src/a.py", "line": 1, "col": 1,
          "rule": "E001", "msg": "error A"}],
        {"ruff check": "src/a.py:1:1: E001 error A"},
        "no_violations",
        id="identical",
    ),
]

DIFF_EDGE_INVARIANTS: list[object] = [
    # Current has records for a tool not in saved baseline -> flagged
    _p(
        [{"tool": "ruff check", "file": "src/a.py", "line": 1, "col": 1,
          "rule": "E001", "msg": "error A"}],
        [
            _make_result("ruff check", stdout="src/a.py:1:1: E001 error A"),
            _make_result("mypy", stdout="src/b.py:1: error: error B [some-code]"),
        ],
        "error B",
        id="new_tool_flags_regression",
    ),
]

DIFF_BASELINE_PATH_ERRORS: list[object] = [
    _p("missing", None, "not found", id="no_baseline_file"),
    _p("invalid", "not valid json", "Cannot read", id="invalid_json"),
    _p("empty", "[]", None, id="empty_baseline_no_current"),
]
