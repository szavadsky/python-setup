"""Edge-case and integration tests for baseline diff."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from python_setup_lint.runner import (
    Record,
    _capture_baseline,
    _compare_records_key,
    _compare_sorted,
    _diff_baseline,
    peek_fallback_tools,
)
from python_setup_lint.testing import make_lint_result
from tests.runner._factories import diff_baseline_with


# ── Mixed schema load ─────────────────────────────────────────────


class TestMixedSchemaLoad:
    def test_legacy_pylint_output_upgraded_to_records_on_diff(self, tmp_path: Path) -> None:
        saved = [
            {
                "tool": "pylint", "exit_code": 0,
                "output": "src/a.py:1:1: W0611: x (unused-import)\nsrc/b.py:2:2: C0114: y (missing-module-docstring)\n",
            }
        ]
        current = [make_lint_result(tool_name="pylint", stdout="src/a.py:1:1: W0611: x (unused-import)\n")]
        violations, reloaded = diff_baseline_with(tmp_path, saved, current)
        assert violations == []
        assert reloaded[0]["schema"] == "v2"
        assert "output" not in reloaded[0]
        assert reloaded[0]["records"] == [
            {"file": "src/a.py", "line": 1, "col": 1, "rule": "unused-import", "msg": "x"},
        ]

    def test_legacy_unknown_tool_keeps_rstrip_set_path(self, tmp_path: Path) -> None:
        saved = [{"tool": "strange-tool", "exit_code": 0, "output": "line A\nline B\n"}]
        current = [make_lint_result(tool_name="strange-tool", stdout="line A\n")]
        violations, reloaded = diff_baseline_with(tmp_path, saved, current)
        assert violations == []
        assert reloaded[0]["output"] == "line A"

    def test_full_pre_t2_baseline_loads_all_tools(self, tmp_path: Path) -> None:
        legacy_tools = [
            "tach check", "ruff check", "rumdl check", "mypy", "yamllint",
            "ty check", "pyright verify types", "pylint", "detect-secrets",
        ]
        saved = [{"tool": t, "exit_code": 0, "output": ""} for t in legacy_tools]
        saved.append({
            "tool": "pyright check", "exit_code": 0,
            "diagnostics": {"summary": {"errorCount": 0, "warningCount": 0}},
        })
        current = [make_lint_result(tool_name=t, exit_code=0, stdout="") for t in legacy_tools]
        current.append(make_lint_result(
            tool_name="pyright check",
            stdout=json.dumps({"summary": {"errorCount": 0, "warningCount": 0}}),
        ))
        violations, _ = diff_baseline_with(tmp_path, saved, current)
        assert violations == []


# ── Performance benchmark: 50k-line baseline < 200ms ─────────────


class TestPerfBenchmark:
    def test_50k_line_baseline_compares_under_200ms(self) -> None:
        records_saved: list[Record] = []
        for f in range(1000):
            file = f"src/file_{f:04d}.py"
            for line in range(1, 51):
                records_saved.append(Record(file, line, 1, "E001", "m"))
        records_current = [
            r for r in records_saved
            if not (r.file == "src/file_0999.py" and r.line and r.line > 5)
        ]
        for f in range(5000, 5500):
            records_current.append(Record(f"src/new_{f:04d}.py", 1, 1, "E001", "m"))
        records_saved.sort(key=_compare_records_key)
        records_current.sort(key=_compare_records_key)
        t0 = time.perf_counter()
        added, removed = _compare_sorted(records_current, records_saved)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert len(added) == 500
        assert len(removed) == 45
        assert elapsed_ms < 200.0, f"_compare_sorted took {elapsed_ms:.1f}ms (>200ms ceiling)"

    def test_diff_baseline_50k_end_to_end_under_1s(self, tmp_path: Path) -> None:
        records: list[dict[str, Any]] = []
        for f in range(1000):
            file = f"src/file_{f:04d}.py"
            for line in range(1, 51):
                records.append({"file": file, "line": line, "col": 1, "rule": "E001", "msg": "m"})
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
                [{"tool": "pylint", "exit_code": 0, "schema": "v2", "records": []}],
                [make_lint_result(tool_name="ruff check", stdout="src/a.py:1:3: E501 msg\n")],
                lambda v, _: any("New tool result" in x for x in v),
                id="new_tool_result_no_baseline_entry",
            ),
            pytest.param(
                [{"tool": "pyright check", "exit_code": 0, "diagnostics": {"summary": {"errorCount": 0, "warningCount": 0}}}],
                [make_lint_result(tool_name="pyright check", stdout="not json\n")],
                lambda v, _: any("Diagnostics lost" in x for x in v),
                id="diagnostics_lost_when_current_not_json",
            ),
            pytest.param(
                [{"tool": "pyright check", "exit_code": 0, "diagnostics": {"summary": {"errorCount": 1, "warningCount": 0}}}],
                [make_lint_result(tool_name="pyright check", stdout=json.dumps({"summary": {"errorCount": 2, "warningCount": 0}}))],
                lambda v, _: any("Diagnostics changed" in x for x in v),
                id="diagnostics_errors_increase_flagged",
            ),
            pytest.param(
                [{"tool": "pyright check", "exit_code": 0, "diagnostics": {"summary": {"errorCount": 2, "warningCount": 0}}}],
                [make_lint_result(tool_name="pyright check", stdout=json.dumps({"summary": {"errorCount": 1, "warningCount": 0}}))],
                lambda v, r: v == [] and r[0]["diagnostics"]["summary"]["errorCount"] == 1,
                id="diagnostics_errors_decrease_shrinkage",
            ),
            pytest.param(
                [
                    {"tool": "pylint", "exit_code": 0, "schema": "v2", "records": []},
                    {"tool": "ruff check", "exit_code": 0, "schema": "v2", "records": []},
                ],
                [make_lint_result(tool_name="pylint", stdout="")],
                lambda v, r: v == [] and len(r) == 1 and r[0]["tool"] == "pylint",
                id="tool_absent_from_current_removed_from_baseline",
            ),
        ],
    )
    def test_error_paths(
        self, tmp_path: Path, saved: Any, current: list[Any], check: Any,
    ) -> None:
        baseline_path = tmp_path / "baseline.json"
        if saved is not None:
            baseline_path.write_text(json.dumps(saved) if isinstance(saved, list) else saved)
        violations = _diff_baseline(current, baseline_path)
        try:
            reloaded = json.loads(baseline_path.read_text()) if baseline_path.exists() else None
        except json.JSONDecodeError:
            reloaded = None
        assert check(violations, reloaded)


# ── T2-1 review-fix additions: gaps D1–D6 ────────────────────────


class TestPeekFallbackTools:
    def test_snapshot_is_frozen_copy_not_live_reference(self, tmp_path: Path) -> None:
        diff_baseline_with(
            tmp_path,
            [{"tool": "strange-tool", "exit_code": 0, "output": "line A\n"}],
            [make_lint_result(tool_name="strange-tool", stdout="line A\n")],
        )
        snap1 = peek_fallback_tools()
        assert isinstance(snap1, frozenset)
        assert snap1 == frozenset({"strange-tool"})
        diff_baseline_with(
            tmp_path,
            [{"tool": "pylint", "exit_code": 0, "schema": "v2", "records": []}],
            [make_lint_result(tool_name="pylint", stdout="")],
        )
        assert snap1 == frozenset({"strange-tool"})
        snap2 = peek_fallback_tools()
        assert "strange-tool" not in snap2
        assert "pylint" not in snap2
        assert snap2 == frozenset()


class TestFallbackTracking:
    def test_legacy_output_falls_back_when_parser_empty(self, tmp_path: Path) -> None:
        saved_output = "************* Module banner only\n"
        saved = [{"tool": "pylint", "exit_code": 0, "output": saved_output}]
        current = [make_lint_result(tool_name="pylint", stdout=saved_output)]
        violations, _ = diff_baseline_with(tmp_path, saved, current)
        assert "pylint" in peek_fallback_tools()
        assert violations == []

    def test_parser_known_tool_with_traceback_lands_in_fallback(self, tmp_path: Path) -> None:
        traceback = (
            "Traceback (most recent call last):\n"
            '  File "ruff_runner.py", line 12, in <module>\n'
            "    raise RuntimeError('boom')\n"
            "RuntimeError: boom\n"
        )
        captured = _capture_baseline([make_lint_result(tool_name="ruff check", stdout=traceback)])
        saved = captured
        violations, reloaded = diff_baseline_with(
            tmp_path, saved, [make_lint_result(tool_name="ruff check", stdout=traceback)],
        )
        assert "ruff check" in peek_fallback_tools()
        assert violations == []
        assert "records" not in reloaded[0]
        assert reloaded[0]["output"] == traceback


class TestLegacyRstripSet:
    def test_legacy_addition_flagged(self, tmp_path: Path) -> None:
        saved = [{"tool": "strange-tool", "exit_code": 0, "output": "line A\n"}]
        current = [make_lint_result(tool_name="strange-tool", stdout="line A\nline B\n")]
        violations, reloaded = diff_baseline_with(tmp_path, saved, current)
        assert any("Output changed" in v for v in violations)
        assert "strange-tool" in peek_fallback_tools()
        assert reloaded[0]["output"] == "line A\n"

    def test_legacy_addition_count_change_flagged(self, tmp_path: Path) -> None:
        saved = [{"tool": "strange-tool", "exit_code": 0, "output": "line A\nline A\n"}]
        current = [make_lint_result(tool_name="strange-tool", stdout="line A\nline A\nline B\n")]
        violations, _ = diff_baseline_with(tmp_path, saved, current)
        assert any("Output changed" in v for v in violations)


class TestExitCodeBothNonzero:
    def test_both_nonzero_diff_exit_codes_still_diff_content(self, tmp_path: Path) -> None:
        saved = [{"tool": "mypy", "exit_code": 1, "schema": "v2", "records": [{"file": "a.py", "line": 1, "col": None, "rule": "code", "msg": "m"}]}]
        current = [make_lint_result(tool_name="mypy", exit_code=2, stdout="a.py:1: error: m [code]\nb.py:2: error: n [other]\n")]
        violations, reloaded = diff_baseline_with(tmp_path, saved, current)
        assert any("mypy" in v for v in violations)
        assert not any("Exit code changed" in v for v in violations)
        assert reloaded[0]["exit_code"] == 1

    def test_both_nonzero_identical_content_no_diff(self, tmp_path: Path) -> None:
        saved = [{"tool": "mypy", "exit_code": 1, "schema": "v2", "records": [{"file": "a.py", "line": 1, "col": None, "rule": "code", "msg": "m"}]}]
        current = [make_lint_result(tool_name="mypy", exit_code=2, stdout="a.py:1: error: m [code]\n")]
        violations, reloaded = diff_baseline_with(tmp_path, saved, current)
        assert violations == []
        assert reloaded[0]["exit_code"] == 1


class TestMultiSavedToolDedup:
    def test_duplicate_saved_tool_entries_all_removed_on_tool_absence(self, tmp_path: Path) -> None:
        saved = [
            {"tool": "pylint", "exit_code": 0, "schema": "v2", "records": []},
            {"tool": "pylint", "exit_code": 1, "schema": "v2", "records": [{"file": "a.py", "line": 1, "col": None, "rule": "code", "msg": "m"}]},
            {"tool": "ruff check", "exit_code": 0, "schema": "v2", "records": []},
        ]
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(json.dumps(saved))
        current = [make_lint_result(tool_name="ruff check", stdout="")]
        violations = _diff_baseline(current, baseline_path)
        assert violations == []
        reloaded = json.loads(baseline_path.read_text())
        assert len(reloaded) == 1
        assert reloaded[0]["tool"] == "ruff check"
        assert all(e["tool"] != "pylint" for e in reloaded)


class TestMixedShapeLegacyOutput:
    def test_legacy_pylint_with_unparseable_lines_upgrades_partial(self, tmp_path: Path) -> None:
        saved_output = "Similar lines in 2 files\nsrc/a.py:1:1: W0611: x (unused-import)\n"
        saved = [{"tool": "pylint", "exit_code": 0, "output": saved_output}]
        current = [make_lint_result(tool_name="pylint", stdout=saved_output)]
        violations, reloaded = diff_baseline_with(tmp_path, saved, current)
        assert violations == []
        assert "pylint" in peek_fallback_tools()
        assert "records" not in reloaded[0]
        assert "schema" not in reloaded[0]
        assert reloaded[0]["output"] == saved_output

    def test_legacy_pylint_partial_parse_addition_flagged(self, tmp_path: Path) -> None:
        saved_output = "Similar lines in 2 files\nsrc/a.py:1:1: W0611: x (unused-import)\n"
        current_output = saved_output + "src/c.py:5:1: C0114: new (missing-module-docstring)\n"
        saved = [{"tool": "pylint", "exit_code": 0, "output": saved_output}]
        current = [make_lint_result(tool_name="pylint", stdout=current_output)]
        violations, _ = diff_baseline_with(tmp_path, saved, current)
        assert any("Output changed" in v for v in violations)
        assert "pylint" in peek_fallback_tools()

    def test_legacy_pylint_only_unparseable_falls_back(self, tmp_path: Path) -> None:
        saved_output = "************* Module banner only\n"
        saved = [{"tool": "pylint", "exit_code": 0, "output": saved_output}]
        current = [make_lint_result(tool_name="pylint", stdout=saved_output)]
        violations, reloaded = diff_baseline_with(tmp_path, saved, current)
        assert violations == []
        assert "pylint" in peek_fallback_tools()
        assert "records" not in reloaded[0]
        assert reloaded[0]["output"] == saved_output


class TestCaptureBaselineOnDisk:
    def test_records_emitted_in_sorted_order(self) -> None:
        stdout = (
            "src/z.py:9:1: E501 zeta\n"
            "src/a.py:1:3: E501 alpha\n"
            "src/a.py:1: E501 alpha-no-col\n"
        )
        cap = _capture_baseline([make_lint_result(tool_name="ruff check", stdout=stdout)])
        records = cap[0]["records"]
        keys = [
            (
                () if r["file"] is None else (r["file"],),
                () if r["line"] is None else (r["line"],),
                () if r["col"] is None else (r["col"],),
                r["rule"],
            )
            for r in records
        ]
        assert keys == sorted(keys), f"records not sorted on disk: {records!r}"
        assert [r["file"] for r in records] == ["src/a.py", "src/a.py", "src/z.py"]
        assert records[0]["col"] is None
        assert records[1]["col"] == 3

    def test_records_sorted_round_trip_through_diff(self, tmp_path: Path) -> None:
        stdout = "src/z.py:9:1: E501 zeta\nsrc/a.py:1:3: E501 alpha\nsrc/b.py:5:2: E501 beta\n"
        cap = _capture_baseline([make_lint_result(tool_name="ruff check", stdout=stdout)])
        saved = cap
        current = [make_lint_result(tool_name="ruff check", stdout=stdout)]
        violations, _ = diff_baseline_with(tmp_path, saved, current)
        assert violations == []
