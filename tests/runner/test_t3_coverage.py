"""T3 coverage: statistics aggregation edge cases, tautology fixes, and
cross-cutting assertions that the implementer's tests did not cover."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import python_setup_lint.runner as _runner_module
from python_setup_lint.runner import (
    TOOLS,
    LintResult,
    ViolationCount,
    _aggregate_statistics,
    _build_statistics_flags,
    _parse_detect_secrets_json,
    _parse_mypy_stderr,
    _parse_tach_json,
    _parse_ty_concise,
    _parse_yamllint_parsable,
    _print_statistics_table,
    run_lint,
)
from python_setup_lint.testing import fake_run_cmd_factory, make_lint_result

if TYPE_CHECKING:
    import pytest

# ── All TOOLS must have a registered parser ────────────────────────


class TestParserCompleteness:
    """Every tool in TOOLS must have a corresponding statistics parser."""

    # Replicate the parser dispatch dict here to catch drift
    # (importing a private symbol is OK in the same package tests)
    EXPECTED_PARSER_TOOLS = {
        "ruff check",
        "rumdl check",
        "pylint",
        "pyright check",
        "pyright verify types",
        "mypy",
        "ty check",
        "tach check",
        "yamllint",
        "mypy.stubtest",
        "detect-secrets",
    }

    def test_all_tools_have_parser(self) -> None:
        """Every TOOLS entry has a statistics parser registered."""
        tool_names = {t.name for t in TOOLS}
        missing = tool_names - self.EXPECTED_PARSER_TOOLS
        assert not missing, f"TOOLS missing statistics parsers: {missing}"

    def test_all_parsers_correspond_to_tools(self) -> None:
        """Every registered parser tool name exists in TOOLS."""
        tool_names = {t.name for t in TOOLS}
        extra = self.EXPECTED_PARSER_TOOLS - tool_names
        assert not extra, f"Parsers exist for unknown tools: {extra}"

    def test_statistics_flags_align_with_parsers(self) -> None:
        """Tools with a statistics parser also have non-empty flags."""
        has_flags = set()
        for spec in TOOLS:
            if _build_statistics_flags(spec):
                has_flags.add(spec.name)
        # pyright verify types, mypy.stubtest, detect-secrets have no extra flags
        # but still have parsers
        assert has_flags <= self.EXPECTED_PARSER_TOOLS
        no_flag_but_parser = self.EXPECTED_PARSER_TOOLS - has_flags
        assert no_flag_but_parser <= {
            "pyright verify types",
            "mypy.stubtest",
            "detect-secrets",
        }, f"Tools with parsers but no flags: {no_flag_but_parser}"


# ── Parser edge cases ─────────────────────────────────────────────


class TestParserEdgeCases:
    """Boundary / malformed-input tests for parsers."""

    # ── mypy stderr ─────────────────────────────────────────────
    def test_mypy_stderr_error_code_not_at_end(self) -> None:
        """Error code in brackets mid-line (not at end) is NOT extracted.

        The parser uses $ anchor to match codes at line-end only.
        """
        err = "file.py:1: error: [arg-type] extra message after code\n"
        result = _parse_mypy_stderr("", err)
        assert result == [], f"Expected no match for mid-line code, got {result}"

    def test_mypy_stderr_no_brackets(self) -> None:
        """Line without error code brackets is ignored."""
        err = "file.py:1: error: Some message without code\n"
        assert _parse_mypy_stderr("", err) == []

    def test_mypy_stderr_brackets_no_content(self) -> None:
        """Line with empty brackets is ignored."""
        err = "file.py:1: error: message []\n"
        assert _parse_mypy_stderr("", err) == []

    # ── ty concise ──────────────────────────────────────────────
    def test_ty_concise_no_stdout(self) -> None:
        """Empty stdout returns empty."""
        assert _parse_ty_concise("", "") == []

    def test_ty_concise_whitespace_only(self) -> None:
        """Whitespace-only stdout returns empty."""
        assert _parse_ty_concise("   \n  \n", "") == []

    def test_ty_concise_no_error_code(self) -> None:
        """Line without recognizable error code is ignored."""
        out = "just a line without colons\n"
        result = _parse_ty_concise(out, "")
        assert result == []

    # ── yamllint parsable ───────────────────────────────────────
    def test_yamllint_parsable_extra_colons(self) -> None:
        """Colons in the message part must not confuse rule-id extraction."""
        # Format: file:line:col:rule_id:message:with:colons
        # rule_id is parts[3]
        out = "f.yaml:1:1:trailing-spaces:message:with:extra\n"
        result = _parse_yamllint_parsable(out, "")
        assert ("trailing-spaces", 1) in result, f"Expected trailing-spaces, got {result}"

    def test_yamllint_parsable_no_colons(self) -> None:
        """Line without colons is ignored."""
        out = "just a message\n"
        assert _parse_yamllint_parsable(out, "") == []

    def test_yamllint_parsable_empty_rule_id(self) -> None:
        """Rule ID after colon may be empty; should be skipped."""
        out = "f.yaml:1:1::message\n"  # empty rule_id
        result = _parse_yamllint_parsable(out, "")
        assert len(result) == 0, f"Expected no match for empty rule_id, got {result}"

    # ── detect-secrets ──────────────────────────────────────────
    def test_detect_secrets_missing_type(self) -> None:
        """Secret entry without 'type' key should be counted as 'unknown'."""
        out = json.dumps(
            {
                "results": {
                    "file.py": [{"type": "SecretA"}, {"other": "val"}],
                },
            }
        )
        result = _parse_detect_secrets_json(out, "")
        assert ("SecretA", 1) in result
        assert ("unknown", 1) in result, f"Expected unknown, got {result}"

    def test_detect_secrets_non_dict_secret(self) -> None:
        """Secret entry that is not a dict should be skipped."""
        out = json.dumps(
            {
                "results": {
                    "file.py": [{"type": "SecretA"}, "not_a_dict"],
                },
            }
        )
        result = _parse_detect_secrets_json(out, "")
        assert ("SecretA", 1) in result
        # Second entry is a string, skipped
        assert len(result) == 1

    def test_detect_secrets_non_list_results(self) -> None:
        """'results' value that is not a dict should be empty."""
        out = json.dumps({"results": "not_a_dict"})
        assert _parse_detect_secrets_json(out, "") == []

    def test_detect_secrets_non_string_type(self) -> None:
        """Secret with non-string 'type' is skipped (isinstance check)."""
        out = json.dumps(
            {
                "results": {
                    "file.py": [{"type": 123}],
                },
            }
        )
        result = _parse_detect_secrets_json(out, "")
        assert result == [], f"Expected empty for non-string type, got {result}"

    # ── tach json ───────────────────────────────────────────────
    def test_tach_json_non_dict_data(self) -> None:
        """Loaded JSON that is not a dict returns empty."""
        assert _parse_tach_json("[]", "") == []

    def test_tach_json_errors_not_list(self) -> None:
        """'errors' key that is not a list returns empty."""
        out = json.dumps({"errors": "not_a_list"})
        assert _parse_tach_json(out, "") == []


# ── Aggregation edge cases ────────────────────────────────────────


class TestAggregateStatisticsEdgeCases:
    """Tautology-resistant aggregation tests."""

    def test_duplicate_tool_in_results(self) -> None:
        """Same tool appearing twice in results with different violations.

        Each LintResult is a separate run; same tool can produce different
        stdout on different invocations. Both should contribute counts.
        """
        results = [
            LintResult("ruff check", 0, "Count\tCode\n-----\t----\n3\tF401\n", "", 0.0),
            LintResult("ruff check", 0, "Count\tCode\n-----\t----\n2\tE501\n", "", 0.0),
        ]
        counts = _aggregate_statistics(results)
        assert ViolationCount("ruff check", "F401", 3) in counts
        assert ViolationCount("ruff check", "E501", 2) in counts

    def test_all_parsers_reachable(self) -> None:
        """Every tool with a parser successfully processes empty output."""
        for tool_name in (
            "ruff check",
            "rumdl check",
            "pylint",
            "pyright check",
            "pyright verify types",
            "mypy",
            "ty check",
            "tach check",
            "yamllint",
            "mypy.stubtest",
            "detect-secrets",
        ):
            r = LintResult(tool_name, 0, "", "", 0.0)
            counts = _aggregate_statistics([r])
            assert counts == [], f"{tool_name} should produce empty counts from empty output"

    def test_aggregate_with_large_counts(self) -> None:
        """Large counts are preserved accurately."""
        stdout = "Count\tCode\n-----\t----\n9999\tF401\n"
        r = LintResult("ruff check", 0, stdout, "", 0.0)
        counts = _aggregate_statistics([r])
        assert ViolationCount("ruff check", "F401", 9999) in counts

    def test_aggregate_sorts_properly(self) -> None:
        """Sorting by count desc, then tool, then rule."""
        results = [
            LintResult("ruff check", 0, "Count\tCode\n-----\t----\n2\tE501\n1\tF401\n", "", 0.0),
            LintResult("mypy", 0, "", "file.py:1: error: x [code-a]\n" * 3, 0.0),
        ]
        counts = _aggregate_statistics(results)
        # Highest count first: code-a (3) > E501 (2) > F401 (1)
        assert len(counts) == 3
        assert counts[0] == ViolationCount("mypy", "code-a", 3)
        assert counts[1] == ViolationCount("ruff check", "E501", 2)
        assert counts[2] == ViolationCount("ruff check", "F401", 1)


# ── Observability: statistics JSON structure ─────────────────────


class TestStatisticsObservability:
    """Verify statistics output is structurally inspectable."""

    def test_statistics_json_structure(self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
        """--statistics --format json produces parseable structured array."""
        fake = fake_run_cmd_factory(
            {
                "ruff check": make_lint_result(
                    tool_name="ruff check",
                    stdout="Count\tCode\n-----\t----\n1\tF401\n",
                ),
            }
        )
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        rc = run_lint(
            path="src/main.py",
            statistics=True,
            statistics_format="json",
            no_fail_fast=True,
        )
        captured = capsys.readouterr()
        assert isinstance(rc, int)
        out = captured.out.strip()
        assert out, "JSON statistics output should not be empty"
        data = json.loads(out)
        assert isinstance(data, list), "JSON output should be a list"
        assert len(data) > 0, "Expected at least one violation entry"
        entry = data[0]
        assert isinstance(entry, dict), "Each entry should be a dict"
        assert "tool" in entry, "Each entry must have 'tool'"
        assert "rule" in entry, "Each entry must have 'rule'"
        assert "count" in entry, "Each entry must have 'count'"
        assert isinstance(entry["count"], int), "count must be an integer"

    def test_statistics_table_not_empty(self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
        """--statistics (table) output always includes the statistics header."""
        fake = fake_run_cmd_factory(
            {
                "ruff check": make_lint_result(
                    tool_name="ruff check",
                    stdout="Count\tCode\n-----\t----\n1\tF401\n",
                ),
            }
        )
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        rc = run_lint(
            path="src/main.py",
            statistics=True,
            no_fail_fast=True,
        )
        captured = capsys.readouterr()
        assert isinstance(rc, int)
        out = captured.out
        assert "VIOLATION STATISTICS" in out, (
            f"Statistics table should include 'VIOLATION STATISTICS' header. Output length: {len(out)} chars."
        )

    def test_statistics_json_empty_violations(self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
        """When no violations exist, JSON output is an empty array."""
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        rc = run_lint(
            path="src/main.py",
            statistics=True,
            statistics_format="json",
            no_fail_fast=True,
        )
        _ = rc
        captured = capsys.readouterr()
        out = captured.out.strip()
        data = json.loads(out)
        assert isinstance(data, list)
        assert data == [], f"Expected empty list, got {data}"


# ── Statistics table formatting ───────────────────────────────────


class TestPrintStatisticsTableEdgeCases:
    """Edge-case output for _print_statistics_table."""

    def test_mixed_tool_names_formatting(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Long tool names are displayed (column format is minimum width, not max)."""
        counts = [
            ViolationCount(tool="a" * 30, rule="X1", count=1),
        ]
        _print_statistics_table(counts)
        captured = capsys.readouterr()
        # Tool name appears (:<20 is minimum width, so long names are not truncated)
        assert "a" * 20 in captured.out
        assert "X1" in captured.out

    def test_zero_count_rule(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Zero counts are displayed (may indicate a parser found nothing)."""
        counts = [ViolationCount(tool="test", rule="Z001", count=0)]
        _print_statistics_table(counts)
        captured = capsys.readouterr()
        # zero is explicitly shown, not hidden
        assert "0" in captured.out
        assert "Z001" in captured.out

    def test_print_with_no_violations_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Empty list prints 'No violations found' message."""
        _print_statistics_table([])
        captured = capsys.readouterr()
        assert "No violations found" in captured.out
