"""T2 — drift-resistant baseline diff tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from python_setup_lint.runner import Record
from python_setup_lint.runner._record_types import _compare_records_key
from python_setup_lint.runner.baseline import (
    _compare_sorted,  # private import for white-box testing
)
from python_setup_lint.testing import make_lint_result
from tests.runner._factories import diff_baseline_with

pytestmark = pytest.mark.no_external_api


def _sorted(records: list[Record]) -> list[Record]:  # pylint: disable=trivial-wrapper  # thin sorted wrapper; readability alias for sort key
    return sorted(records, key=_compare_records_key)


# ── Surface unit: _compare_sorted pure-fn ────────────────────────


class TestCompareSorted:
    @pytest.mark.parametrize(
        ("current", "saved", "exp_additions", "exp_removals"),
        [
            pytest.param(
                [Record("a.py", 1, 1, "E1", "m"), Record("b.py", 2, 1, "E2", "m")],
                [Record("a.py", 1, 1, "E1", "m"), Record("b.py", 2, 1, "E2", "m")],
                0,
                0,
                id="identical_returns_empty",
            ),
            pytest.param(
                [Record("a.py", 1, 1, "E1", "m"), Record("b.py", 2, 1, "E2", "m")],
                [Record("a.py", 1, 1, "E1", "m")],
                1,
                0,
                id="pure_addition",
            ),
            pytest.param(
                [Record("a.py", 1, 1, "E1", "m")],
                [Record("a.py", 1, 1, "E1", "m"), Record("b.py", 2, 1, "E2", "m")],
                0,
                1,
                id="pure_removal",
            ),
            pytest.param(
                [
                    Record("a.py", 1, 1, "E1", "m"),
                    Record("a.py", 1, 1, "E1", "m"),
                    Record("a.py", 1, 1, "E1", "m"),
                ],
                [Record("a.py", 1, 1, "E1", "m")],
                2,
                0,
                id="multiset_count_increase_flagged_as_addition",
            ),
            pytest.param(
                [Record("a.py", 1, 1, "E1", "m")],
                [
                    Record("a.py", 1, 1, "E1", "m"),
                    Record("a.py", 1, 1, "E1", "m"),
                    Record("a.py", 1, 1, "E1", "m"),
                ],
                0,
                2,
                id="multiset_count_decrease_recorded_as_removal",
            ),
            pytest.param(
                [Record("a.py", 1, 1, "E1", "new msg")],
                [Record("a.py", 1, 1, "E1", "old msg")],
                1,
                1,
                id="msg_change_on_same_key_flagged_as_addition",
            ),
            pytest.param(
                [Record("a.py", 1, 1, "E1", "m"), Record("b.py", 2, 1, "E2", "m")],
                [Record("b.py", 2, 1, "E2", "m"), Record("a.py", 1, 1, "E1", "m")],
                0,
                0,
                id="order_tolerant_two_equal_blocks_reordered",
            ),
            pytest.param(
                [
                    Record("a.py", 1, 1, "A", "m"),
                    Record("b.py", 2, 1, "B", "m"),
                    Record("c.py", 3, 1, "C", "m"),
                    Record("d.py", 4, 1, "D", "m"),
                    Record("e.py", 5, 1, "E", "m"),
                ],
                [
                    Record("a.py", 1, 1, "A", "m"),
                    Record("b.py", 2, 1, "B", "m"),
                    Record("c.py", 3, 1, "C", "m"),
                ],
                2,
                0,
                id="block_insertion_plus_later_reorder_no_spurious_diff",
            ),
        ],
    )
    def test_compare_sorted_given_current_and_saved_then_expected_additions_and_removals(
        self,
        current: list[Record],
        saved: list[Record],
        exp_additions: int,
        exp_removals: int,
    ) -> None:
        added, removed = _compare_sorted(_sorted(current), _sorted(saved))
        assert len(added) == exp_additions
        assert len(removed) == exp_removals

    def test_compare_sorted_given_none_position_records_then_sort_below_real(self) -> None:
        recs = _sorted(
            [
                Record("z.py", 9, 9, "Z", "m"),
                Record(None, None, None, "R0801:x<->y", "dup"),
                Record("a.py", 1, 1, "A", "m"),
            ]
        )
        assert recs[0].rule.startswith("R0801")
        assert recs[1].file == "a.py"
        assert recs[2].file == "z.py"


# ── Downstream integration: drift-resistant diff semantics ────────


class TestDriftResistantDiff:
    @pytest.mark.parametrize(
        ("saved", "current_stdout", "expect_violation", "check_reloaded", "exit_code"),
        [
            pytest.param(
                [
                    {"tool": "pylint", "file": "a.py", "line": 1, "col": 1, "rule": "unused-import", "msg": "x"},
                ],
                "a.py:1:1: W0611: x (unused-import)\nb.py:2:2: C0114: y (missing-module-docstring)\n",
                True,
                lambda r: {"tool": "pylint", "file": "a.py", "line": 1, "col": 1, "rule": "unused-import", "msg": "x"} in r,
                0,
                id="pure_insertion_no_spurious_diff",
            ),
            pytest.param(
                [
                    {"tool": "pylint", "file": "a.py", "line": 1, "col": 1, "rule": "unused-import", "msg": "x"},
                    {"tool": "pylint", "file": "b.py", "line": 2, "col": 2, "rule": "missing-module-docstring", "msg": "y"},
                ],
                "a.py:1:1: W0611: x (unused-import)\n",
                False,
                lambda r: (
                    r
                    == [
                        {"tool": "pylint", "file": "a.py", "line": 1, "col": 1, "rule": "unused-import", "msg": "x"},
                    ]
                ),
                0,
                id="pure_deletion_shrinkage_silently_recorded",
            ),
            pytest.param(
                [
                    {"tool": "pylint", "file": "a.py", "line": 1, "col": 1, "rule": "unused-import", "msg": "x"},
                    {"tool": "pylint", "file": "b.py", "line": 2, "col": 2, "rule": "missing-module-docstring", "msg": "y"},
                ],
                "b.py:2:2: C0114: y (missing-module-docstring)\na.py:1:1: W0611: x (unused-import)\n",
                False,
                lambda r: (
                    {tuple(sorted(d.items())) for d in r}
                    == {
                        tuple(sorted(d.items()))
                        for d in [
                            {"tool": "pylint", "file": "a.py", "line": 1, "col": 1, "rule": "unused-import", "msg": "x"},
                            {
                                "tool": "pylint",
                                "file": "b.py",
                                "line": 2,
                                "col": 2,
                                "rule": "missing-module-docstring",
                                "msg": "y",
                            },
                        ]
                    }
                ),
                0,
                id="reorder_only_no_spurious_diff",
            ),
            pytest.param(
                [
                    {"tool": "mypy", "file": "a.py", "line": 1, "col": None, "rule": "arg-type", "msg": "m"},
                ],
                "a.py:1: error: m [arg-type]\na.py:1: error: m [arg-type]\n",
                True,
                None,
                0,
                id="count_change_on_duplicate_line_detected",
            ),
            pytest.param(
                [
                    {
                        "tool": "pylint",
                        "file": None,
                        "line": None,
                        "col": None,
                        "rule": "R0801:src/a.py:1-5<->src/b.py:10-15",
                        "msg": "Similar lines (R0801)",
                    },
                ],
                "Similar lines in 2 files\n==src/b.py:[10:15]\n==src/a.py:[1:5]\n",
                False,
                None,
                0,
                id="r0801_reorder_no_spurious_diff",
            ),
            pytest.param(
                [],
                "",
                True,
                None,
                -11,
                id="crash_recorded",
            ),
        ],
    )
    def test_diff_baseline_given_drift_resistant_then_expected_violations(
        self,
        tmp_path: Path,
        saved: list[dict[str, Any]],
        current_stdout: str,
        expect_violation: bool,
        check_reloaded: Any,
        exit_code: int,
    ) -> None:
        tool_name = saved[0]["tool"] if saved else "mypy"
        current = [make_lint_result(tool_name=tool_name, stdout=current_stdout, exit_code=exit_code)]
        violations, reloaded = diff_baseline_with(tmp_path, saved, current)
        if expect_violation:
            if saved:
                assert any(saved[0]["tool"] in v for v in violations)
            else:
                assert violations
        else:
            assert violations == []
        if check_reloaded:
            assert check_reloaded(reloaded)
