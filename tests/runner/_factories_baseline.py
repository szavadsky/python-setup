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


def baseline_entry_for_tool(entries: list[dict[str, Any]], tool: str) -> dict[str, Any]:  # pylint: disable=W9728  # typed alias for find_tool_entry, provides semantic name for callers
    """Return the first baseline entry whose ``tool`` equals *tool* (asserts at least one)."""
    return find_tool_entry(entries, tool)


# ── ``_diff_baseline`` invariant matrix ────────────────────────────

DIFF_BASELINE_CASES: list[Any] = [  # pylint: disable=W9704  # heterogeneous pytest.param tuples with varying dict structures
    _p(
        {
            "tool": "ruff check",
            "exit_code": 0,
            "output": "src/a.py:1: error A\nsrc/b.py:2: error B",
        },
        {"ruff check": "src/a.py:1: error A", "mypy": "src/c.py:3: error C"},
        "no_violations",
        "ruff_shrunk_b_removed",
        id="pure_shrinkage_auto_records",
    ),
    _p(
        {"tool": "ruff check", "exit_code": 0, "output": "src/a.py:1: error A"},
        {"ruff check": "src/a.py:1: error A\nsrc/b.py:2: error B"},
        "output changed",
        "no_post",
        id="pure_addition_flags_regression",
    ),
    _p(
        {
            "tool": "ruff check",
            "exit_code": 0,
            "output": "src/a.py:1: error A\nsrc/b.py:2: error B",
        },
        {"ruff check": "src/a.py:1: error A\nsrc/c.py:3: error C"},
        "output changed",
        "b_removed_c_not_added",
        id="mixed_shrinkage_and_addition",
    ),
    _p(
        {
            "tool": "pylint",
            "exit_code": 0,
            "output": "1 src/a.py:1:1: W0611: unused-import\n1 src/b.py:2:2: C0114: missing-module-docstring",
        },
        {"pylint": "src/a.py:1:1: W0611: unused-import"},
        "no_violations",
        "c0114_removed",
        id="pylint_shrinkage_auto_records",
    ),
    _p(
        {"tool": "ruff check", "exit_code": 0, "output": "ok"},
        {"ruff check": "ok"},
        "no_violations",
        "mypy_removed",
        id="tool_removed_shrinkage_auto_records",
    ),
    _p(
        {
            "tool": "pyright check",
            "exit_code": 0,
            "diagnostics": {"summary": {"errorCount": 2, "warningCount": 0}},
        },
        {"pyright check": {"summary": {"errorCount": 1, "warningCount": 0}}},
        "no_violations",
        "diag_count_1",
        id="diagnostics_shrinkage_auto_records",
    ),
    _p(
        {
            "tool": "pylint",
            "exit_code": 0,
            "output": "1 src/a.py:1:1: W0611: unused-import",
        },
        {
            "pylint": "src/a.py:1:1: W0611: unused-import\nsrc/b.py:2:2: C0114: missing-module-docstring"
        },
        "output changed",
        "no_post",
        id="pylint_addition_flags_regression",
    ),
    _p(
        {
            "tool": "rumdl check",
            "exit_code": 0,
            "output": "src/a.md:1 MD012 (10ms)\nsrc/b.md:3 MD013 (20ms)",
        },
        {"rumdl check": "src/a.md:1 MD012 (5ms)"},
        "no_violations",
        "md013_removed",
        id="rumdl_shrinkage_auto_records_ignoring_timing",
    ),
    _p(
        {"tool": "mypy", "exit_code": 0, "output": "src/a.py:1: error"},
        {"mypy": ""},
        "no_violations",
        "output_emptied",
        id="output_to_empty_shrinkage",
    ),
    _p(
        {
            "tool": "mypy",
            "exit_code": 0,
            "output": "src/a.py:1: error A  \nsrc/b.py:2: error B  ",
        },
        {"mypy": "src/a.py:1: error A\nsrc/b.py:2: error B"},
        "no_violations",
        "no_post",
        id="whitespace_normalization_d6",
    ),
    _p(
        {"tool": "mypy", "exit_code": 0, "output": "src/a.py:1: error A"},
        {"mypy": "src/a.py:1: error A\nsrc/a.py:1: error A\nsrc/a.py:1: error A"},
        "no_violations",
        "no_post",
        id="duplicate_line_count_set_semantics_d7",
    ),
    _p(
        {
            "tool": "ruff check",
            "exit_code": 0,
            "output": "src/a.py:1: error A\nsrc/b.py:2: error B",
        },
        {"ruff check": "src/b.py:2: error B\nsrc/a.py:1: error A"},
        "no_violations",
        "no_post",
        id="ruff_ordering_insensitive",
    ),
    _p(
        {
            "tool": "pyright check",
            "exit_code": 0,
            "diagnostics": {"summary": {"errorCount": 1, "warningCount": 0}},
        },
        {"pyright check": "non-JSON"},
        "diagnostics lost",
        "diag_preserved",
        id="diagnostics_lost_regression_d4",
    ),
    _p(
        {"tool": "ruff check", "exit_code": 0, "output": "src/a.py:1: error A"},
        {"ruff check": "src/a.py:1: error A"},
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
    ruff = baseline_entry_for_tool(reloaded, "ruff check")
    assert "src/b.py:2: error B" not in ruff.get("output", "")


def _b_removed_c_not_added(reloaded: list[dict[str, Any]]) -> None:
    ruff = baseline_entry_for_tool(reloaded, "ruff check")
    assert "src/b.py:2: error B" not in ruff.get("output", "")
    assert "src/c.py:3: error C" not in ruff.get("output", "")


def _c0114_removed(reloaded: list[dict[str, Any]]) -> None:
    assert "C0114" not in baseline_entry_for_tool(reloaded, "pylint").get("output", "")


def _exit_0_recorded(reloaded: list[dict[str, Any]]) -> None:
    assert baseline_entry_for_tool(reloaded, "mypy")["exit_code"] == 0


def _mypy_removed(reloaded: list[dict[str, Any]]) -> None:
    _assert_removed(reloaded, "mypy")
    assert len(reloaded) == 1 and reloaded[0]["tool"] == "ruff check"


def _diag_count_1(reloaded: list[dict[str, Any]]) -> None:
    assert reloaded[0]["diagnostics"]["summary"]["errorCount"] == 1


def _md013_removed(reloaded: list[dict[str, Any]]) -> None:
    assert "MD013" not in baseline_entry_for_tool(reloaded, "rumdl check").get(
        "output", ""
    )


def _output_emptied(reloaded: list[dict[str, Any]]) -> None:
    assert baseline_entry_for_tool(reloaded, "mypy").get("output", "") == ""


def _diag_preserved(reloaded: list[dict[str, Any]]) -> None:
    assert reloaded[0]["diagnostics"] is not None


def _all_mypy_dupes_removed(reloaded: list[dict[str, Any]]) -> None:
    _assert_removed(reloaded, "mypy")
    assert len(_entries_for_tool(reloaded, "ruff check")) == 1


DIFF_BASELINE_POST_ASSERTS: dict[str, Callable[..., None]] = {
    "ruff_shrunk_b_removed": _ruff_shrunk_b_removed,
    "b_removed_c_not_added": _b_removed_c_not_added,
    "c0114_removed": _c0114_removed,
    "exit_0_recorded": _exit_0_recorded,
    "mypy_removed": _mypy_removed,
    "diag_count_1": _diag_count_1,
    "md013_removed": _md013_removed,
    "output_emptied": _output_emptied,
    "diag_preserved": _diag_preserved,
    "all_mypy_dupes_removed": _all_mypy_dupes_removed,
    "no_post": _no_op,
}


def build_current_results(
    saved_baseline: dict[str, Any] | list[dict[str, Any]], current_map: dict[str, Any]
) -> list[LintResult]:
    """Construct ``LintResult`` list from a matrix row's compact ``current_map``."""
    from python_setup_lint.testing import make_lint_result

    saved_entries = (
        [saved_baseline] if isinstance(saved_baseline, dict) else saved_baseline
    )
    current: list[LintResult] = []
    for entry in saved_entries:
        tool = entry["tool"]
        if tool not in current_map:
            continue
        value = current_map[tool]
        if isinstance(value, (dict, list)):
            current.append(make_lint_result(tool_name=tool, stdout=json.dumps(value)))
        else:
            current.append(make_lint_result(tool_name=tool, stdout=str(value)))
    return current


def diff_violation_kind(violations: list[str], want: str) -> None:
    """Assert *want* substring is in any violation (case-insensitive)."""
    lowered = [v.lower() for v in violations]
    assert any(want in v for v in lowered), (
        f"Expected {want!r} in violations; got {violations!r}"
    )


def _make_result(tool_name: str, exit_code: int = 0, stdout: str = "") -> LintResult:
    """Lazy make_lint_result wrapper (avoids eager import of testing module)."""
    from python_setup_lint.testing import make_lint_result

    return make_lint_result(tool_name=tool_name, exit_code=exit_code, stdout=stdout)


# ── _diff_baseline edge-case tables ────────────────────────────────

DIFF_EDGE_CASES: list[Any] = [  # pylint: disable=W9704  # heterogeneous pytest.param tuples with varying dict structures
    _p(
        {
            "tool": "pyright check",
            "exit_code": 0,
            "diagnostics": {
                "summary": {"errorCount": 1, "timeInSec": 10.0, "filesAnalyzed": 100}
            },
        },
        {
            "pyright check": {
                "summary": {"errorCount": 1, "timeInSec": 15.0, "filesAnalyzed": 100}
            }
        },
        "no_violations",
        id="pyright_ignores_time_in_sec",
    ),
    _p(
        {
            "tool": "pyright check",
            "exit_code": 0,
            "diagnostics": {"summary": {"errorCount": 1}},
        },
        {"pyright check": {"summary": {"errorCount": 1}}},
        "no_violations",
        id="diagnostics_used_when_present",
    ),
    _p(
        {"tool": "test", "exit_code": 0, "output": "ok"},
        {"test": "ok"},
        "no_violations",
        id="identical",
    ),
]

DIFF_EDGE_INVARIANTS: list[Any] = [  # pylint: disable=W9704  # heterogeneous pytest.param tuples with varying dict structures
    _p(
        {"tool": "test", "exit_code": 0, "output": "ok"},
        [_make_result("test", exit_code=1, stdout="ok")],
        "exit code",
        id="exit_code_changed_flags_regression",
    ),
    _p(
        {"tool": "mypy", "exit_code": 1, "output": "some error"},
        [_make_result("mypy", exit_code=0, stdout="")],
        "no_violations",
        id="exit_code_shrinkage_auto_records",
    ),
    _p(
        {"tool": "tool_a", "exit_code": 0, "output": ""},
        [_make_result("tool_a"), _make_result("tool_b")],
        "no baseline entry",
        id="new_tool_flags_regression",
    ),
]

DIFF_BASELINE_PATH_ERRORS: list[Any] = [  # pylint: disable=W9704  # heterogeneous pytest.param tuples with varying dict structures
    _p("missing", None, "not found", id="no_baseline_file"),
    _p("invalid", "not valid json", "Cannot read", id="invalid_json"),
    _p("empty", "[]", None, id="empty_baseline_no_current"),
]
