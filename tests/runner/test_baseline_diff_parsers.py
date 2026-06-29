"""Parser and capture unit tests for baseline diff."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from python_setup_lint.runner import Record
from python_setup_lint.runner._record_types import _compare_records_key
from python_setup_lint.runner.baseline import (  # private import for white-box testing
    _capture_baseline,
    _compare_sorted,
    _diff_baseline,
)
from python_setup_lint.runner.parsers import (  # type: ignore[attr-defined]  # private import for white-box testing
    _parse_mypy_records,
    _parse_pylint_records,
    _parse_pyright_records,
    _parse_ruff_records,
    _parse_rumdl_records,
    _parse_ty_records,
    _parse_yamllint_records,
)
from python_setup_lint.testing import make_lint_result


def _sorted(records: list[Record]) -> list[Record]:  # pylint: disable=trivial-wrapper  # test helper; readability over DRY
    return sorted(records, key=_compare_records_key)


# ── Private-complex unit: per-tool record parsers ────────────────


class TestRecordParsers:
    @pytest.mark.parametrize(
        ("tool", "output_lines", "expected"),
        [
            pytest.param(
                _parse_ruff_records,
                "src/a.py:1:3: E501 line too long\n",
                [Record("src/a.py", 1, 3, "E501", "line too long")],
                id="ruff_parses_path_line_col_code_msg",
            ),
            pytest.param(
                _parse_ruff_records,
                "src/a.py:1: E501 line too long\n",
                [Record("src/a.py", 1, None, "E501", "line too long")],
                id="ruff_col_optional",
            ),
            pytest.param(
                _parse_ruff_records,
                "warning: something\nsrc/a.py:1:3: E501 msg\nFound 1 error.\n",
                [Record("src/a.py", 1, 3, "E501", "msg")],
                id="ruff_skips_non_match_lines",
            ),
            pytest.param(
                _parse_mypy_records,
                "src/a.py:1: error: Bad type [arg-type]\n"
                "src/a.py:2: note: see docs\n"
                "src/a.py:3: error: No code here\n",
                [Record("src/a.py", 1, None, "arg-type", "Bad type")],
                id="mypy_skips_notes_and_codeless_lines",
            ),
            pytest.param(
                _parse_mypy_records,
                "src/b.py:5: error: X [code-b]\nsrc/a.py:1: error: Y [code-a]\n",
                [Record("src/a.py", 1, None, "code-a", "Y"), Record("src/b.py", 5, None, "code-b", "X")],
                id="mypy_records_sorted_by_file_line",
            ),
            pytest.param(
                _parse_pylint_records,
                "************* Module foo\n"
                "src/foo.py:1:1: W0611: Unused import (unused-import)\n"
                "Similar lines in 2 files\n"
                "==src/a.py:[1:5]\n"
                "==src/b.py:[10:15]\n"
                "def foo():\n"
                "    return 1\n",
                None,
                id="pylint_r0801_collapses_to_one_record",
            ),
            pytest.param(
                _parse_pylint_records,
                "Similar lines in 2 files\n==src/a.py:[1:5]\n==src/b.py:[10:15]\n",
                None,
                id="pylint_r0801_reorder_produces_identical_record",
            ),
            pytest.param(
                _parse_pylint_records,
                "Cyclic import (foo \u2192 bar \u2192 foo)\n",
                [Record(None, None, None, "R0401:foo \u2192 bar \u2192 foo", "Cyclic import (foo \u2192 bar \u2192 foo)")],
                id="pylint_r0401_cyclic_import_collapses",
            ),
            pytest.param(
                _parse_pylint_records,
                "src/a.py:1:1: W0611: Unused import (unused-import)\n",
                [Record("src/a.py", 1, 1, "unused-import", "Unused import")],
                id="pylint_rule_prefers_symbol_over_code",
            ),
            pytest.param(
                _parse_pylint_records,
                "src/a.py:1:1: W0611: Unused import\n",
                [Record("src/a.py", 1, 1, "W0611", "Unused import")],
                id="pylint_falls_back_to_code_when_no_symbol",
            ),
            pytest.param(
                _parse_ty_records,
                "src/a.py:1:3: invalid-argument-type foo\n",
                [Record("src/a.py", 1, 3, "invalid-argument-type", "foo")],
                id="ty_concise_form",
            ),
            pytest.param(
                _parse_ty_records,
                "error[invalid-argument-type]: Bad arg\n"
                "  --> src/a.py:1:3\n"
                "   |\n"
                " 1 | code\n",
                [Record("src/a.py", 1, 3, "invalid-argument-type", "Bad arg")],
                id="ty_multiline_arrow_form",
            ),
            pytest.param(
                _parse_yamllint_records,
                "config/a.yaml:1:3: indentation: msg with: colons\n",
                [Record("config/a.yaml", 1, 3, "indentation", "msg with: colons")],
                id="yamllint_parsable",
            ),
            pytest.param(
                _parse_rumdl_records,
                "README.md:8:1: [MD013] Line length 200 exceeds 80 characters\n"
                "README.md:73:1: [MD032] List should be preceded by blank line [*]\n"
                "\nIssues: Found 2 issues in 1 file (XXXms)\n"
                "Run `rumdl fmt` to automatically fix 1 of the 2 issues\n",
                [Record("README.md", 8, 1, "MD013", "Line length 200 exceeds 80 characters"),
                 Record("README.md", 73, 1, "MD032", "List should be preceded by blank line [*]")],
                id="rumdl_text_strips_footer",
            ),
            pytest.param(
                _parse_pyright_records,
                {
                    "generalDiagnostics": [
                        {
                            "file": "a.py",
                            "rule": "X",
                            "message": "m",
                            "range": {"start": {"line": 5, "character": 10}},
                        },
                    ]
                },
                [Record("a.py", 6, 11, "X", "m")],
                id="pyright_zero_indexed_line_col_plus_one",
            ),
            pytest.param(
                _parse_pyright_records,
                {
                    "generalDiagnostics": [
                        {
                            "file": "b.py",
                            "rule": "Z",
                            "message": "m",
                            "range": {"start": {"line": 2, "character": 0}},
                        },
                        {
                            "file": "a.py",
                            "rule": "A",
                            "message": "m",
                            "range": {"start": {"line": 1, "character": 0}},
                        },
                    ]
                },
                [Record("a.py", 2, 1, "A", "m"), Record("b.py", 3, 1, "Z", "m")],
                id="pyright_records_sorted_by_file_line_col_rule",
            ),
            pytest.param(
                _parse_pyright_records,
                {"generalDiagnostics": "not a list"},
                [],
                id="pyright_malformed_returns_empty_not_a_list",
            ),
            pytest.param(
                _parse_pyright_records,
                [],
                [],
                id="pyright_malformed_returns_empty_empty_list",
            ),
            pytest.param(
                _parse_pyright_records,
                {"generalDiagnostics": [42]},
                [],
                id="pyright_malformed_returns_empty_invalid_diag",
            ),
        ],
    )
    def test_parser(self, tool: Any, output_lines: Any, expected: Any, request: Any) -> None:
        if expected is None:
            recs = tool(output_lines)
            rules = [r.rule for r in recs]
            if "r0801_collapses" in request.node.callspec.id:
                assert "R0801:src/a.py:1-5<->src/b.py:10-15" in rules
                assert "unused-import" in rules
                assert len(recs) == 2
            elif "r0801_reorder" in request.node.callspec.id:
                a = _parse_pylint_records(
                    "Similar lines in 2 files\n==src/a.py:[1:5]\n==src/b.py:[10:15]\n"
                )
                b = _parse_pylint_records(
                    "Similar lines in 2 files\n==src/b.py:[10:15]\n==src/a.py:[1:5]\n"
                )
                assert a == b
                assert a[0].rule == "R0801:src/a.py:1-5<->src/b.py:10-15"
        else:
            recs = tool(output_lines)
            assert recs == expected


# ── _capture_baseline schema-v2 surface ───────────────────────────


class TestCaptureSchemaV2:
    @pytest.mark.parametrize(
        ("tool_name", "stdout", "check"),
        [
            pytest.param(
                "pylint",
                "src/a.py:1:1: W0611: x (unused-import)\n",
                lambda cap: (
                    cap[0]["schema"] == "v2"
                    and cap[0]["records"] == [
                        {"file": "src/a.py", "line": 1, "col": 1, "rule": "unused-import", "msg": "x"},
                    ]
                ),
                id="pylint_captured_as_schema_v2_records",
            ),
            pytest.param(
                "ruff check",
                "src/a.py:1:3: E501 msg\n",
                lambda cap: (
                    cap[0]["schema"] == "v2"
                    and cap[0]["records"] == [
                        {"file": "src/a.py", "line": 1, "col": 3, "rule": "E501", "msg": "msg"},
                    ]
                ),
                id="ruff_captured_as_schema_v2_records",
            ),
            pytest.param(
                "mypy",
                "src/a.py:1: error: Bad [arg-type]\n",
                lambda cap: cap[0]["schema"] == "v2" and cap[0]["records"][0]["rule"] == "arg-type",
                id="mypy_captured_as_schema_v2_records",
            ),
            pytest.param(
                "strange-tool",
                "noise\n",
                lambda cap: "schema" not in cap[0] and cap[0]["output"] == "noise\n",
                id="unknown_tool_keeps_legacy_output",
            ),
            pytest.param(
                "pylint",
                "************* Module banner only\n",
                lambda cap: "schema" not in cap[0] and cap[0]["output"] == "************* Module banner only\n",
                id="pylint_empty_records_nonempty_stdout_falls_back_to_output",
            ),
        ],
    )
    def test_capture(self, tool_name: str, stdout: str, check: Any) -> None:
        cap = _capture_baseline([make_lint_result(tool_name=tool_name, stdout=stdout)])
        assert check(cap)


# ── _capture_one edge cases ──────────────────────────────────────


class TestCaptureOneEdgeCases:
    @pytest.mark.parametrize(
        ("tool_name", "stdout", "check"),
        [
            pytest.param(
                "pyright check",
                json.dumps({"summary": {"errorCount": 0, "warningCount": 0}}),
                lambda cap: cap[0]["diagnostics"]["summary"]["errorCount"] == 0,
                id="pyright_captured_as_diagnostics",
            ),
            pytest.param(
                "pyright check",
                json.dumps({"time": "2024-01-01", "version": "1.0", "summary": {"errorCount": 0, "warningCount": 0, "timeInSec": 1.5}}),
                lambda cap: (
                    "time" not in cap[0]["diagnostics"]
                    and "version" not in cap[0]["diagnostics"]
                    and "timeInSec" not in cap[0]["diagnostics"].get("summary", {})
                ),
                id="pyright_volatile_fields_stripped",
            ),
            pytest.param(
                "pyright verify types",
                json.dumps({"version": "1.1.410", "time": "1782394246865", "timeInSec": 0.51, "diagnostics": []}),
                lambda cap: (
                    "time" not in cap[0].get("output", "")
                    and "timeInSec" not in cap[0].get("output", "")
                    and "version" not in cap[0].get("output", "")
                ),
                id="pyright_verifytypes_volatile_fields_stripped",
            ),
            pytest.param(
                "rumdl check",
                json.dumps([{"file": "README.md", "rule": "MD013"}]),
                lambda cap: "diagnostics" in cap[0],
                id="rumdl_json_captured_as_diagnostics",
            ),
            pytest.param(
                "rumdl check",
                "README.md:8:1: [MD013] Line too long\n",
                lambda cap: cap[0]["schema"] == "v2" and cap[0]["records"][0]["rule"] == "MD013",
                id="rumdl_text_captured_as_records",
            ),
            pytest.param(
                "rumdl check",
                "No issues found (42ms)\n",
                lambda cap: "schema" not in cap[0] and "(XXXms)" in cap[0]["output"],
                id="rumdl_text_empty_records_nonempty_stdout_falls_back",
            ),
            pytest.param(
                "rumdl check",
                "README.md:8:1: [MD013] Line too long\nIssues: Found 1 issue (123ms)\n",
                lambda cap: cap[0]["schema"] == "v2" and cap[0]["records"][0]["rule"] == "MD013",
                id="rumdl_timing_normalised_in_output",
            ),
        ],
    )
    def test_capture_one(self, tool_name: str, stdout: str, check: Any) -> None:
        cap = _capture_baseline([make_lint_result(tool_name=tool_name, stdout=stdout)])
        assert check(cap)

    def test_pyright_verifytypes_baseline_diff_stable(self, tmp_path: Path) -> None:
        baseline_path = tmp_path / "baseline.json"
        saved = [{
            "tool": "pyright verify types", "exit_code": 0,
            "output": json.dumps({"version": "1.1.410", "time": "1782394246865", "timeInSec": 0.51, "diagnostics": []}),
        }]
        baseline_path.write_text(json.dumps(saved))
        current = [make_lint_result(tool_name="pyright verify types", stdout=json.dumps(
            {"version": "1.1.411", "time": "1782394247000", "timeInSec": 0.72, "diagnostics": []},
        ))]
        violations = _diff_baseline(current, baseline_path)
        assert violations == []


# ── _compare_sorted edge cases ───────────────────────────────────


class TestCompareSortedEdgeCases:
    @pytest.mark.parametrize(
        ("current", "saved", "exp_additions", "exp_removals"),
        [
            pytest.param([], [], 0, 0, id="both_empty"),
            pytest.param(
                [],
                _sorted([Record("a.py", 1, 1, "E1", "m")]),
                0, 1,
                id="current_empty_saved_has_records",
            ),
            pytest.param(
                _sorted([Record("a.py", 1, 1, "E1", "m")]),
                [],
                1, 0,
                id="current_has_records_saved_empty",
            ),
            pytest.param(
                _sorted([Record(None, None, None, "R0801:x<->y", "dup")]),
                _sorted([Record(None, None, None, "R0801:x<->y", "dup")]),
                0, 0,
                id="none_file_on_both_sides",
            ),
            pytest.param(
                _sorted([Record(None, None, None, "R0801:x<->y", "dup"), Record("a.py", 1, 1, "E1", "m")]),
                _sorted([Record("a.py", 1, 1, "E1", "m")]),
                1, 0,
                id="none_file_added",
            ),
        ],
    )
    def test_compare_sorted_edge(
        self, current: list[Record], saved: list[Record],
        exp_additions: int, exp_removals: int,
    ) -> None:
        added, removed = _compare_sorted(current, saved)
        assert len(added) == exp_additions
        assert len(removed) == exp_removals


# ── Parser edge cases ────────────────────────────────────────────


class TestParserEdgeCases:
    @pytest.mark.parametrize(
        ("tool", "stdout", "expected"),
        [
            pytest.param(
                _parse_yamllint_records,
                "config/a.yaml:1:3: indentation: msg\n",
                [Record("config/a.yaml", 1, 3, "indentation", "msg")],
                id="yamllint_space_before_rule_id",
            ),
            pytest.param(
                _parse_rumdl_records,
                "Issues: Found 0 issues in 1 file (XXXms)\n",
                [],
                id="rumdl_no_violations_footer_only",
            ),
            pytest.param(
                _parse_mypy_records,
                "src/a.py:1: note: see docs\nsrc/b.py:2: note: also docs\n",
                [],
                id="mypy_notes_only_no_errors",
            ),
            pytest.param(
                _parse_ty_records,
                "error[invalid-argument-type]: Bad arg\n  --> src/a.py:1:3\n",
                [Record("src/a.py", 1, 3, "invalid-argument-type", "Bad arg")],
                id="ty_arrow_form_only",
            ),
            pytest.param(
                _parse_ty_records,
                "error[invalid-argument-type]: Bad arg\n  --> src/a.py:1:3\n"
                "error[missing-return-type]: No return\n  --> src/b.py:5:1\n",
                [Record("src/a.py", 1, 3, "invalid-argument-type", "Bad arg"),
                 Record("src/b.py", 5, 1, "missing-return-type", "No return")],
                id="ty_arrow_form_multiple_errors",
            ),
            pytest.param(
                _parse_pylint_records,
                "Similar lines in 2 files\n==src/a.py:[1:5] ==src/b.py:[10:15]\n",
                None,
                id="pylint_r0801_inline_spans",
            ),
            pytest.param(
                _parse_pylint_records,
                "Similar lines in 2 files\n",
                None,
                id="pylint_r0801_banner_without_enough_spans",
            ),
            pytest.param(
                _parse_ruff_records,
                "",
                [],
                id="ruff_empty_stdout",
            ),
            pytest.param(
                _parse_ruff_records,
                "Found 1 error.\n",
                [],
                id="ruff_stdout_with_only_footer",
            ),
        ],
    )
    def test_parser_edge(self, tool: Any, stdout: str, expected: Any, request: Any) -> None:
        recs = tool(stdout)
        if expected is None:
            if "r0801_inline_spans" in request.node.callspec.id:
                rules = [r.rule for r in recs]
                assert "R0801:src/a.py:1-5<->src/b.py:10-15" in rules
            elif "r0801_banner" in request.node.callspec.id:
                assert not any(r.rule.startswith("R0801") for r in recs)
        else:
            assert recs == expected
