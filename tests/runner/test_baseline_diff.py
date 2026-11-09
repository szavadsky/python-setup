"""Drift-resistant baseline diff tests: _compare_sorted and _diff_baseline semantics."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from python_setup_lint.runner import Record, peek_fallback_tools
from python_setup_lint.runner._record_types import _compare_records_key
from python_setup_lint.runner.baseline import (  # private import for white-box testing
    _compare_sorted,
    _diff_baseline,
)
from python_setup_lint.testing import make_lint_result
from tests.runner._factories import diff_baseline_with

pytestmark = pytest.mark.no_external_api


def _sorted(records: list[Record]) -> list[Record]:  # pylint: disable=trivial-wrapper  # thin sorted wrapper; readability alias for sort key
    return sorted(records, key=_compare_records_key)


# ── Surface unit: _compare_sorted pure-fn (merged survivor class) ──
# Merged from deleted test_baseline_diff_edge.py::TestCompareSortedEdgeCases.
# Survivor: test_compare_sorted_given_current_and_saved_then_expected_additions_and_removals;
# every moved case below keeps its original parametrized id.
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
            # Survivors merged from TestCompareSortedEdgeCases (deleted module).
            pytest.param([], [], 0, 0, id="both_empty"),
            pytest.param(
                [],
                [Record("a.py", 1, 1, "E1", "m")],
                0,
                1,
                id="current_empty_saved_has_records",
            ),
            pytest.param(
                [Record("a.py", 1, 1, "E1", "m")],
                [],
                1,
                0,
                id="current_has_records_saved_empty",
            ),
            pytest.param(
                [Record(None, None, None, "R0801:x<->y", "dup")],
                [Record(None, None, None, "R0801:x<->y", "dup")],
                0,
                0,
                id="none_file_on_both_sides",
            ),
            pytest.param(
                [Record(None, None, None, "R0801:x<->y", "dup"), Record("a.py", 1, 1, "E1", "m")],
                [Record("a.py", 1, 1, "E1", "m")],
                1,
                0,
                id="none_file_added",
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


# ── Performance benchmark: 50k-line baseline ────────────────────


@pytest.mark.slow
class TestPerfBenchmark:
    def test_compare_sorted_given_50k_line_baseline_then_under_200ms(self) -> None:
        records_saved: list[Record] = [
            Record(f"src/file_{f:04d}.py", line, 1, "E001", "m") for f in range(1000) for line in range(1, 51)
        ]
        records_current = [r for r in records_saved if not (r.file == "src/file_0999.py" and r.line and r.line > 5)]
        records_current.extend(Record(f"src/new_{f:04d}.py", 1, 1, "E001", "m") for f in range(5000, 5500))
        records_saved.sort(key=_compare_records_key)
        records_current.sort(key=_compare_records_key)
        t0 = time.perf_counter()
        added, removed = _compare_sorted(records_current, records_saved)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert len(added) == 500
        assert len(removed) == 45
        assert elapsed_ms < 200.0, f"_compare_sorted took {elapsed_ms:.1f}ms (>200ms ceiling)"

    def test_diff_baseline_given_50k_line_baseline_then_end_to_end_under_1s(self, tmp_path: Path) -> None:
        records: list[
            dict[str, Any]
        ] = [  # dict shape: {"tool": str, "file": str, "line": int, "col": int, "rule": str, "msg": str}
            {"tool": "ruff check", "file": f"src/file_{f:04d}.py", "line": line, "col": 1, "rule": "E001", "msg": "m"}
            for f in range(1000)
            for line in range(1, 51)
        ]
        baseline_path = tmp_path / "big.json"
        baseline_path.write_text(json.dumps(records))
        stdout = "\n".join(f"src/file_{f:04d}.py:{line}:1: E001 m" for f in range(1000) for line in range(1, 51))
        current = [make_lint_result(tool_name="ruff check", stdout=stdout)]
        t0 = time.perf_counter()
        violations = _diff_baseline(current, baseline_path)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert violations == []
        assert elapsed_ms < 1000.0, f"_diff_baseline 50k took {elapsed_ms:.1f}ms (>1s ceiling)"


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


# ── Error-path coverage: _diff_baseline failure modes ────────────


class TestDiffBaselineErrors:
    @pytest.mark.parametrize(
        ("saved", "current", "check"),
        [
            pytest.param(
                None,
                [],
                lambda v, _: any("Baseline file not found" in x for x in v),
                id="baseline_file_not_found",
            ),
            pytest.param(
                "{invalid json",
                [],
                lambda v, _: any("Cannot read baseline" in x for x in v),
                id="cannot_read_corrupt_json",
            ),
            pytest.param(
                [],
                [make_lint_result(tool_name="ruff check", stdout="src/a.py:1:3: E501 msg\n")],
                lambda v, _: any("E501: msg @ src/a.py:1:3" in x for x in v),
                id="new_tool_result_no_baseline_entry",
            ),
            pytest.param(
                [{"tool": "pyright check", "file": "src/b.py", "line": 1, "col": 1, "rule": "some-rule", "msg": "the message"}],
                [make_lint_result(tool_name="pyright check", stdout="not json\n")],
                lambda v, r: v == [] and r == [],
                id="diagnostics_lost_when_current_not_json",
            ),
            pytest.param(
                [{"tool": "pyright check", "file": "src/a.py", "line": 1, "col": 1, "rule": "rule", "msg": "msg1"}],
                [
                    make_lint_result(
                        tool_name="pyright check",
                        stdout=json.dumps(
                            {
                                "summary": {"errorCount": 2, "warningCount": 0},
                                "generalDiagnostics": [
                                    {
                                        "file": "src/a.py",
                                        "rule": "rule",
                                        "message": "msg1",
                                        "range": {"start": {"line": 0, "character": 0}},
                                    },
                                    {
                                        "file": "src/b.py",
                                        "rule": "rule",
                                        "message": "msg2",
                                        "range": {"start": {"line": 1, "character": 0}},
                                    },
                                ],
                            }
                        ),
                    )
                ],
                lambda v, _: any("msg2 @ src/b.py:2" in x for x in v),
                id="diagnostics_errors_increase_flagged",
            ),
            pytest.param(
                [
                    {"tool": "pyright check", "file": "src/a.py", "line": 1, "col": 1, "rule": "rule", "msg": "msg1"},
                    {"tool": "pyright check", "file": "src/b.py", "line": 2, "col": 2, "rule": "rule", "msg": "msg2"},
                ],
                [
                    make_lint_result(
                        tool_name="pyright check",
                        stdout=json.dumps(
                            {
                                "summary": {"errorCount": 1, "warningCount": 0},
                                "generalDiagnostics": [
                                    {
                                        "file": "src/a.py",
                                        "rule": "rule",
                                        "message": "msg1",
                                        "range": {"start": {"line": 0, "character": 0}},
                                    },
                                ],
                            }
                        ),
                    )
                ],
                lambda v, r: v == [] and len(r) == 1 and r[0]["file"] == "src/a.py",
                id="diagnostics_errors_decrease_shrinkage",
            ),
            pytest.param(
                [
                    {"tool": "pylint", "file": "src/a.py", "line": 1, "col": 1, "rule": "unused-import", "msg": "x"},
                    {"tool": "ruff check", "file": "src/b.py", "line": 2, "col": 2, "rule": "E001", "msg": "y"},
                ],
                [make_lint_result(tool_name="pylint", stdout="src/a.py:1:1: W0611: x (unused-import)\n")],
                lambda v, r: v == [] and len(r) == 1 and r[0]["tool"] == "pylint",
                id="tool_absent_from_current_removed_from_baseline",
            ),
        ],
    )
    def test_diff_baseline_given_error_paths_then_expected_violations(
        self,
        tmp_path: Path,
        saved: Any,
        current: list[Any],
        check: Any,
    ) -> None:
        baseline_path = tmp_path / "baseline.json"
        if saved is not None:
            baseline_path.write_text(json.dumps(saved) if isinstance(saved, list) else saved)
        violations = _diff_baseline(current, baseline_path)
        try:
            reloaded = json.loads(baseline_path.read_text()) if baseline_path.exists() else None
        except json.JSONDecodeError:  # pylint: disable=silent-except  # test helper; exception expected
            reloaded = None
        assert check(violations, reloaded)


# ── Fallback/frozen-stub and dedup pinning limbs ────────────────


class TestPeekFallbackTools:
    def test_peek_fallback_tools_given_snapshot_then_frozen_copy(self, tmp_path: Path) -> None:
        # peek_fallback_tools() now always returns empty frozenset (WS-6 clean break).
        # Verify diff_baseline_with doesn't crash and the stub returns frozenset().
        saved: list[dict[str, object]] = []
        current = [make_lint_result(tool_name="ruff check", stdout="src/a.py:1:3: E501 msg\n")]
        violations, _ = diff_baseline_with(tmp_path, saved, current)
        assert any("msg @ src/a.py:1:3" in x for x in violations)
        snap = peek_fallback_tools()
        assert isinstance(snap, frozenset)
        assert snap == frozenset()


class TestFlatRecordRoundTrip:
    """Survivor of three overlapping flat-record pylint round-trip cases.

    Survivor: test_flat_record_pylint_given_unchanged_then_round_trips.
    Merged cases (deleted as duplicates): TestMixedSchemaLoad::
    test_mixed_schema_given_legacy_pylint_output_then_upgraded_to_records and
    TestMixedShapeLegacyOutput::test_mixed_shape_legacy_given_parseable_pylint_then_round_trips.
    """

    def test_flat_record_pylint_given_unchanged_then_round_trips(self, tmp_path: Path) -> None:
        saved = [
            {"tool": "pylint", "file": "src/a.py", "line": 1, "col": 1, "rule": "unused-import", "msg": "x"},
            {"tool": "pylint", "file": "src/b.py", "line": 2, "col": 2, "rule": "missing-module-docstring", "msg": "y"},
        ]
        current = [make_lint_result(tool_name="pylint", stdout="src/a.py:1:1: W0611: x (unused-import)\n")]
        violations, reloaded = diff_baseline_with(tmp_path, saved, current)
        assert violations == []
        assert reloaded == [
            {"col": 1, "file": "src/a.py", "line": 1, "msg": "x", "rule": "unused-import", "tool": "pylint"},
        ]


class TestMultiSavedToolDedup:
    def test_multi_saved_tool_dedup_given_duplicate_entries_then_removed_on_absence(self, tmp_path: Path) -> None:
        # Flat records: duplicate pylint violations for the same violation; current has no pylint
        # violations but has the ruff check one -> duplicate pylint removed, ruff check stays.
        saved = [
            {"tool": "pylint", "file": "src/a.py", "line": 1, "col": 1, "rule": "unused-import", "msg": "x"},
            {"tool": "pylint", "file": "src/a.py", "line": 1, "col": 1, "rule": "unused-import", "msg": "x"},
            {"tool": "ruff check", "file": "src/b.py", "line": 2, "col": 2, "rule": "E001", "msg": "y"},
        ]
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(json.dumps(saved))
        current = [make_lint_result(tool_name="ruff check", stdout="src/b.py:2:2: E001 y\n")]
        violations = _diff_baseline(current, baseline_path)
        assert violations == []
        reloaded = json.loads(baseline_path.read_text())
        assert len(reloaded) == 1
        assert reloaded[0]["tool"] == "ruff check"
        assert all(e["tool"] != "pylint" for e in reloaded)
