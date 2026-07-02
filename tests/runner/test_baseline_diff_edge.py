"""Edge-case and integration tests for baseline diff."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from python_setup_lint.runner import Record, peek_fallback_tools
from python_setup_lint.runner._record_types import _compare_records_key
from python_setup_lint.runner.baseline import (  # private import for white-box testing
    _capture_baseline,
    _compare_sorted,
    _diff_baseline,
)
from python_setup_lint.testing import make_lint_result
from tests.runner._factories import diff_baseline_with

# ── Mixed schema load ─────────────────────────────────────────────


class TestMixedSchemaLoad:
    def test_mixed_schema_given_legacy_pylint_output_then_upgraded_to_records(self, tmp_path: Path) -> None:
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
    def test_mixed_schema_given_unknown_tool_then_baseline_shrinks(self, tmp_path: Path) -> None:
        saved = [
            {"tool": "strange-tool", "file": "src/a.py", "line": 1, "col": 1, "rule": "E001", "msg": "old violation"},
        ]
        current = [make_lint_result(tool_name="strange-tool", stdout="")]
        violations, reloaded = diff_baseline_with(tmp_path, saved, current)
        assert violations == []
        assert reloaded == []

    def test_mixed_schema_given_empty_baseline_then_ok_for_all_tools(self, tmp_path: Path) -> None:
        tool_names = [
            "tach check", "ruff check", "rumdl check", "mypy", "yamllint",
            "ty check", "pyright verify types", "pylint", "detect-secrets",
        ]
        saved: list[dict[str, object]] = []
        current = [make_lint_result(tool_name=t, exit_code=0, stdout="") for t in tool_names]
        current.append(make_lint_result(
            tool_name="pyright check",
            stdout=json.dumps({"summary": {"errorCount": 0, "warningCount": 0}}),
        ))
        violations, _ = diff_baseline_with(tmp_path, saved, current)
        assert violations == []


# ── Performance benchmark: 50k-line baseline < 200ms ─────────────


@pytest.mark.slow
class TestPerfBenchmark:
    def test_50k_line_baseline_compares_under_200ms(self) -> None:
        records_saved: list[Record] = [
            Record(f"src/file_{f:04d}.py", line, 1, "E001", "m")
            for f in range(1000)
            for line in range(1, 51)
        ]
        records_current = [
            r for r in records_saved
            if not (r.file == "src/file_0999.py" and r.line and r.line > 5)
        ]
        records_current.extend(
            Record(f"src/new_{f:04d}.py", 1, 1, "E001", "m")
            for f in range(5000, 5500)
        )
        records_saved.sort(key=_compare_records_key)
        records_current.sort(key=_compare_records_key)
        t0 = time.perf_counter()
        added, removed = _compare_sorted(records_current, records_saved)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert len(added) == 500
        assert len(removed) == 45
        assert elapsed_ms < 200.0, f"_compare_sorted took {elapsed_ms:.1f}ms (>200ms ceiling)"

    def test_diff_baseline_50k_end_to_end_under_1s(self, tmp_path: Path) -> None:
        records: list[dict[str, Any]] = [  # dict shape: {"file": str, "line": int, "col": int, "rule": str, "msg": str}
            {"file": f"src/file_{f:04d}.py", "line": line, "col": 1, "rule": "E001", "msg": "m"}
            for f in range(1000)
            for line in range(1, 51)
        ]
        saved = [{"tool": "ruff check", "exit_code": 0, "schema": "v2", "records": records}]
        baseline_path = tmp_path / "big.json"
        baseline_path.write_text(json.dumps(saved))
        stdout = "\n".join(
            f"src/file_{f:04d}.py:{line}:1: E001 m"
            for f in range(1000) for line in range(1, 51)
        )
        current = [make_lint_result(tool_name="ruff check", stdout=stdout)]
        t0 = time.perf_counter()
        violations = _diff_baseline(current, baseline_path)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert violations == []
        assert elapsed_ms < 1000.0, f"_diff_baseline 50k took {elapsed_ms:.1f}ms (>1s ceiling)"


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
                [make_lint_result(tool_name="pyright check", stdout=json.dumps({
                    "summary": {"errorCount": 2, "warningCount": 0},
                    "generalDiagnostics": [
                        {"file": "src/a.py", "rule": "rule", "message": "msg1", "range": {"start": {"line": 0, "character": 0}}},
                        {"file": "src/b.py", "rule": "rule", "message": "msg2", "range": {"start": {"line": 1, "character": 0}}},
                    ],
                }))],
                lambda v, _: any("msg2 @ src/b.py:2" in x for x in v),
                id="diagnostics_errors_increase_flagged",
            ),
            pytest.param(
                [
                    {"tool": "pyright check", "file": "src/a.py", "line": 1, "col": 1, "rule": "rule", "msg": "msg1"},
                    {"tool": "pyright check", "file": "src/b.py", "line": 2, "col": 2, "rule": "rule", "msg": "msg2"},
                ],
                [make_lint_result(tool_name="pyright check", stdout=json.dumps({
                    "summary": {"errorCount": 1, "warningCount": 0},
                    "generalDiagnostics": [
                        {"file": "src/a.py", "rule": "rule", "message": "msg1", "range": {"start": {"line": 0, "character": 0}}},
                    ],
                }))],
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
        self, tmp_path: Path, saved: Any, current: list[Any], check: Any,
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

# ── T2-1 review-fix additions: gaps D1–D6 ────────────────────────


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


class TestFallbackTracking:
    def test_fallback_tracking_given_flat_records_then_no_violations_for_unchanged(self, tmp_path: Path) -> None:
        # Flat-record behavior: saved has one pylint violation, current has same -> 0 violations.
        saved = [{"tool": "pylint", "file": "src/a.py", "line": 1, "col": 1, "rule": "unused-import", "msg": "x"}]
        current = [make_lint_result(tool_name="pylint", stdout="src/a.py:1:1: W0611: x (unused-import)\n")]
        violations, reloaded = diff_baseline_with(tmp_path, saved, current)
        assert violations == []
        assert len(reloaded) == 1
        assert reloaded[0] == {"tool": "pylint", "file": "src/a.py", "line": 1, "col": 1, "rule": "unused-import", "msg": "x"}

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

class TestMixedShapeLegacyOutput:
    # Legacy output handling was removed in WS-6. These tests verify
    # that the flat-record baseline correctly handles pylint output.
    def test_mixed_shape_legacy_given_parseable_pylint_then_round_trips(self, tmp_path: Path) -> None:
        saved = [{"tool": "pylint", "file": "src/a.py", "line": 1, "col": 1, "rule": "unused-import", "msg": "x"}]
        current = [make_lint_result(tool_name="pylint", stdout="src/a.py:1:1: W0611: x (unused-import)\n")]
        violations, reloaded = diff_baseline_with(tmp_path, saved, current)
        assert violations == []
        assert reloaded == saved


class TestCaptureBaselineOnDisk:
    def test_capture_baseline_given_records_then_emitted_in_sorted_order(self) -> None:
        stdout = (
            "src/z.py:9:1: E501 zeta\n"
            "src/a.py:1:3: E501 alpha\n"
            "src/a.py:1: E501 alpha-no-col\n"
        )
        records = _capture_baseline([make_lint_result(tool_name="ruff check", stdout=stdout)])
        # _capture_baseline returns a flat list of violation dicts (no nested "records" key).
        keys = [
            (
                () if r["file"] is None else (r["file"],),
                () if r["line"] is None else (r["line"],),
                () if r["col"] is None else (r["col"],),
                r["rule"],
            )
            for r in records
        ]
        assert keys == sorted(keys), f"records not sorted: {records!r}"
        assert [r["file"] for r in records] == ["src/a.py", "src/a.py", "src/z.py"]
        assert records[0]["col"] is None
        assert records[1]["col"] == 3

    def test_capture_baseline_given_sorted_records_then_round_trips_through_diff(self, tmp_path: Path) -> None:
        stdout = "src/z.py:9:1: E501 zeta\nsrc/a.py:1:3: E501 alpha\nsrc/b.py:5:2: E501 beta\n"
        cap = _capture_baseline([make_lint_result(tool_name="ruff check", stdout=stdout)])
        saved = cap
        current = [make_lint_result(tool_name="ruff check", stdout=stdout)]
        violations, _ = diff_baseline_with(tmp_path, saved, current)
        assert violations == []
