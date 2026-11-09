"""Synthetic unit tests for the golden snapshot helpers.

No lint pipeline runs here: every ``Finding`` list is built in memory and every
file is a ``tmp_path`` artifact.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from python_setup_lint.runner import TOOLS, LintResult, RunnerConfig, ToolSpec
from python_setup_lint.runner._record_types import Record
from tests._golden import (
    SEMANTIC_ENV,
    UPDATE_ENV,
    Finding,
    assert_matches_golden,
    assert_oracle_coverage,
    assert_tool_coverage,
    collect_findings,
    finding_key,
    normalize_record,
    read_golden,
    read_oracle_rules,
    serialize_findings,
    serialize_tool_minimums,
    slice_tool_section,
    tool_counts_path,
    tool_minimums,
    write_golden_files,
)


@pytest.fixture(autouse=True)
def _isolate_golden_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep host CI/update environment from influencing assertions."""
    monkeypatch.delenv(UPDATE_ENV, raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


def _finding(
    tool: str = "ruff check",
    file: str | None = "src/mod.py",
    line: int | None = 1,
    col: int | None = 1,
    rule: str = "F401",
) -> Finding:
    return {
        "tool": tool,
        "file": file,
        "line": line,
        "col": col,
        "rule": rule,
    }


def test_constants_expose_contract_env_names() -> None:
    assert UPDATE_ENV == "PYTHON_SETUP_LINT_UPDATE_GOLDEN"
    assert SEMANTIC_ENV == "PYTHON_SETUP_LINT_SEMANTIC"


def test_finding_key_given_none_fields_then_sorts_before_strings_and_numbers() -> None:
    none_key = finding_key(_finding(file=None, line=None, col=None))
    empty_key = finding_key(_finding(file="", line=-1, col=-1))
    zero_key = finding_key(_finding(file="a.py", line=0, col=0))

    assert none_key == ("ruff check", "", -1, -1, "F401")
    assert none_key == empty_key
    assert none_key < zero_key


def test_finding_key_given_mixed_files_then_full_none_safe_order() -> None:
    findings = [
        _finding(file="b.py", line=2, col=1),
        _finding(file=None, line=None, col=None),
        _finding(file="a.py", line=0, col=0),
        _finding(file="a.py", line=None, col=None),
    ]

    ordered = sorted(findings, key=finding_key)

    assert [(finding["file"], finding["line"]) for finding in ordered] == [
        (None, None),
        ("a.py", None),
        ("a.py", 0),
        ("b.py", 2),
    ]


def test_normalize_record_given_relative_backslash_path_then_posix(tmp_path: Path) -> None:
    record = {
        "tool": "ruff check",
        "file": "./src\\pkg\\mod.py",
        "line": 3,
        "col": 7,
        "rule": "F401",
        "msg": "unused import",
    }

    result = normalize_record(record, tmp_path / "project")

    assert result == {
        "tool": "ruff check",
        "file": "src/pkg/mod.py",
        "line": 3,
        "col": 7,
        "rule": "F401",
    }
    assert "msg" not in result


def test_normalize_record_given_absolute_path_then_relativized(tmp_path: Path) -> None:
    project = tmp_path / "project"
    record = {
        "tool": "pyright check",
        "file": str(project / "src" / "mod.py"),
        "line": 4,
        "col": 2,
        "rule": "reportMissingImports",
    }

    result = normalize_record(record, project)

    assert result["file"] == "src/mod.py"


def test_normalize_record_given_none_fields_then_preserved(tmp_path: Path) -> None:
    record = {"tool": "pylint", "file": None, "line": None, "col": None, "rule": "R0801"}

    result = normalize_record(record, tmp_path)

    assert result == {"tool": "pylint", "file": None, "line": None, "col": None, "rule": "R0801"}


def test_normalize_record_given_absolute_outside_project_then_asserts(tmp_path: Path) -> None:
    record = {
        "tool": "pyright check",
        "file": str(tmp_path / "elsewhere" / "mod.py"),
        "line": 1,
        "col": 1,
        "rule": "reportMissingImports",
    }

    with pytest.raises(AssertionError, match="outside project"):
        normalize_record(record, tmp_path / "project")


def test_serialize_findings_given_unsorted_then_sorted_canonical_json() -> None:
    findings = [
        _finding(tool="z", file="b.py", line=2, rule="R2"),
        _finding(tool="a", file="a.py", line=1, rule="R1"),
    ]

    text = serialize_findings(findings)

    expected_rows = [
        {
            "tool": finding["tool"],
            "file": finding["file"],
            "line": finding["line"],
            "col": finding["col"],
            "rule": finding["rule"],
        }
        for finding in sorted(findings, key=finding_key)
    ]
    assert text == json.dumps(expected_rows, indent=2, sort_keys=True) + "\n"
    assert text.endswith("]\n")
    assert not text.endswith("\n\n")
    assert text.index('"col"') < text.index('"file"') < text.index('"line"') < text.index('"rule"') < text.index('"tool"')


def test_serialize_tool_minimums_given_mapping_then_sorted_canonical_json() -> None:
    text = serialize_tool_minimums({"ruff check": 2, "mypy": 1})

    assert text == json.dumps({"ruff check": 2, "mypy": 1}, indent=2, sort_keys=True) + "\n"
    assert text.index('"mypy"') < text.index('"ruff check"')


def test_serialize_findings_given_empty_input_then_empty_canonical_arrays() -> None:
    assert serialize_findings([]) == "[]\n"
    assert serialize_tool_minimums({}) == "{}\n"


def test_write_golden_files_given_empty_findings_then_roundtrips_and_counts_zero(tmp_path: Path) -> None:
    golden = tmp_path / "empty_findings.json"

    write_golden_files(golden, [])

    assert golden.read_bytes() == b"[]\n"
    assert read_golden(golden) == []
    minimums = json.loads(tool_counts_path(golden).read_text(encoding="utf-8"))
    assert set(minimums) == {spec.name for spec in TOOLS}
    assert set(minimums.values()) == {0}
    assert_matches_golden([], golden_path=golden)


def _stub_collect_pipeline(monkeypatch: pytest.MonkeyPatch, results: list[LintResult]) -> None:
    """Replace ``collect_findings``' private pipeline with in-memory tool results."""
    specs = [ToolSpec("alpha", []), ToolSpec("beta", [])]
    records = {
        "alpha": [Record(file="mod.py", line=1, col=1, rule="A", msg="")],
        "beta": [Record(file="mod.py", line=2, col=1, rule="B", msg="")],
    }
    monkeypatch.setattr("python_setup_lint.runner._cli_complexity._apply_config_overrides", lambda config: config)
    monkeypatch.setattr("python_setup_lint.runner._cli_complexity._select_tools", lambda config: specs)
    monkeypatch.setattr(
        "python_setup_lint.runner.parsers._RECORD_PARSERS",
        {name: (lambda _stdout, rows=rows: rows) for name, rows in records.items()},
    )
    monkeypatch.setattr("python_setup_lint.runner.cli._run_tool_pipeline", lambda selected, **_kwargs: (0, results))


def test_collect_findings_given_tool_results_then_keeps_pipeline_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_collect_pipeline(monkeypatch, [LintResult("beta", 0, "", "", 0.0), LintResult("alpha", 0, "", "", 0.0)])

    findings = collect_findings(tmp_path, RunnerConfig(cwd=tmp_path))

    assert [finding["tool"] for finding in findings] == ["beta", "alpha"]
    assert [finding["rule"] for finding in findings] == ["B", "A"]


def test_collect_findings_given_no_tool_results_then_returns_empty_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_collect_pipeline(monkeypatch, [])

    assert collect_findings(tmp_path, RunnerConfig(cwd=tmp_path)) == []


def test_tool_counts_path_given_findings_name_then_sibling_tool_counts() -> None:
    assert tool_counts_path(Path("/x/minimal_sample_project_findings.json")) == Path("/x/minimal_sample_project_tool_counts.json")
    assert tool_counts_path(Path("/x/snapshot.json")) == Path("/x/snapshot_tool_counts.json")


def test_assert_matches_golden_given_identical_multiset_then_passes(tmp_path: Path) -> None:
    golden = tmp_path / "minimal_sample_project_findings.json"
    findings = [_finding(rule="R1"), _finding(rule="R2", line=2)]
    write_golden_files(golden, findings)

    assert_matches_golden(list(reversed(findings)), golden_path=golden)


def test_assert_matches_golden_given_missing_golden_then_fails_with_update_hint(tmp_path: Path) -> None:
    golden = tmp_path / "missing_findings.json"

    with pytest.raises(pytest.fail.Exception, match=UPDATE_ENV):
        assert_matches_golden([_finding()], golden_path=golden)


def test_assert_matches_golden_given_dropped_finding_then_reports_removed_key(tmp_path: Path) -> None:
    golden = tmp_path / "minimal_sample_project_findings.json"
    kept = _finding(rule="R1")
    dropped = _finding(rule="R2", line=2)
    write_golden_files(golden, [kept, dropped])

    with pytest.raises(pytest.fail.Exception) as excinfo:
        assert_matches_golden([kept], golden_path=golden)

    message = str(excinfo.value)
    assert "removed (1):" in message
    assert repr(finding_key(dropped)) in message
    assert "added" not in message


def test_assert_matches_golden_given_extra_findings_then_reports_sorted_added_keys(tmp_path: Path) -> None:
    golden = tmp_path / "minimal_sample_project_findings.json"
    write_golden_files(golden, [_finding(rule="BASE")])
    added_b = _finding(rule="B", line=2)
    added_a = _finding(rule="A", line=1)

    with pytest.raises(pytest.fail.Exception) as excinfo:
        assert_matches_golden([_finding(rule="BASE"), added_b, added_a], golden_path=golden)

    message = str(excinfo.value)
    assert "added (2):" in message
    assert "removed" not in message
    assert message.index(repr(finding_key(added_a))) < message.index(repr(finding_key(added_b)))


def test_assert_matches_golden_given_duplicate_golden_entry_then_reports_one_removed(tmp_path: Path) -> None:
    golden = tmp_path / "minimal_sample_project_findings.json"
    duplicate = _finding(rule="DUP")
    write_golden_files(golden, [duplicate, duplicate])

    with pytest.raises(pytest.fail.Exception) as excinfo:
        assert_matches_golden([duplicate], golden_path=golden)

    message = str(excinfo.value)
    assert "removed (1):" in message
    assert message.count(repr(finding_key(duplicate))) == 1


def test_diff_keys_given_duplicate_multisets_then_counts_duplicates_once() -> None:
    from tests._golden import _diff_keys  # testing the Counter internals directly

    duplicate = _finding(rule="DUP")
    added = _finding(rule="ADDED", line=2)
    removed = _finding(rule="REMOVED", line=3)

    added_keys, removed_keys = _diff_keys([duplicate, duplicate, added], [duplicate, removed])

    assert added_keys == sorted([finding_key(duplicate), finding_key(added)])
    assert removed_keys == [finding_key(removed)]
    assert _diff_keys([duplicate], [duplicate]) == ([], [])


@pytest.mark.parametrize("ci_var", ["CI", "GITHUB_ACTIONS"])
def test_assert_matches_golden_given_update_under_ci_then_refuses_and_keeps_golden(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ci_var: str,
) -> None:
    golden = tmp_path / "minimal_sample_project_findings.json"
    write_golden_files(golden, [_finding(rule="R1")])
    before = golden.read_bytes()
    counts_before = tool_counts_path(golden).read_bytes()
    monkeypatch.setenv(UPDATE_ENV, "1")
    monkeypatch.setenv(ci_var, "true")

    with pytest.raises(pytest.fail.Exception, match="refusing to rewrite golden under CI"):
        assert_matches_golden([_finding(rule="CHANGED")], golden_path=golden)

    assert golden.read_bytes() == before
    assert tool_counts_path(golden).read_bytes() == counts_before


def test_assert_matches_golden_given_update_locally_then_rewrites_both_byte_identically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    golden = tmp_path / "minimal_sample_project_findings.json"
    findings = [_finding(rule="R2", line=2), _finding(rule="R1")]
    monkeypatch.setenv(UPDATE_ENV, "1")

    with pytest.warns(UserWarning, match="updating golden"):
        assert_matches_golden(findings, golden_path=golden)

    counts_path = tool_counts_path(golden)
    assert golden.read_text(encoding="utf-8") == serialize_findings(findings)
    assert counts_path.read_text(encoding="utf-8") == serialize_tool_minimums(tool_minimums(findings))
    first_golden = golden.read_bytes()
    first_counts = counts_path.read_bytes()

    with pytest.warns(UserWarning, match="updating golden"):
        assert_matches_golden(list(reversed(findings)), golden_path=golden)

    assert golden.read_bytes() == first_golden
    assert counts_path.read_bytes() == first_counts


def test_read_oracle_rules_given_violations_file_then_returns_rule_symbols() -> None:
    rules = read_oracle_rules()

    assert "unjustified-suppression" in rules
    assert "duplicate-code" in rules
    assert "MD072" in rules
    assert all(rule == rule.strip() and rule and not rule.startswith("#") for rule in rules)


def test_assert_oracle_coverage_given_all_rules_present_then_passes() -> None:
    findings = [_finding(rule="unjustified-suppression"), _finding(rule="duplicate-code")]

    assert_oracle_coverage(findings, ["unjustified-suppression", "duplicate-code"])


def test_assert_oracle_coverage_given_missing_rule_then_names_it() -> None:
    with pytest.raises(AssertionError, match="oracle rules missing") as excinfo:
        assert_oracle_coverage([_finding(rule="present")], ["present", "absent"])

    assert "absent" in str(excinfo.value)


def test_assert_tool_coverage_given_met_minimums_then_passes() -> None:
    findings = [_finding(tool="ruff check"), _finding(tool="ruff check"), _finding(tool="mypy")]

    assert_tool_coverage(findings, {"ruff check": 2, "mypy": 1, "tach": 0})


def test_assert_tool_coverage_given_below_minimum_then_names_tool_and_counts() -> None:
    with pytest.raises(AssertionError, match="ruff check") as excinfo:
        assert_tool_coverage([_finding(tool="ruff check")], {"ruff check": 2})

    assert ", 2, 1)" in str(excinfo.value)


def test_tool_minimums_given_findings_then_includes_zero_count_registered_tools() -> None:
    minimums = tool_minimums([_finding(tool="ruff check"), _finding(tool="ruff check"), _finding(tool="mypy")])

    assert minimums["ruff check"] == 2
    assert minimums["mypy"] == 1
    assert minimums["tach check"] == 0
    assert list(minimums) == sorted(minimums)


def test_slice_tool_section_given_bracketed_markers_then_returns_inner_section() -> None:
    output = "preamble\n[pylint] FAILED\nmod.py:49\n[pylint-pyi] FAILED\nstub.py:1\n"

    assert slice_tool_section(output, "[pylint]", "[pylint-pyi]") == "[pylint] FAILED\nmod.py:49\n"


def test_slice_tool_section_given_missing_marker_then_asserts() -> None:
    with pytest.raises(AssertionError, match="start marker"):
        slice_tool_section("no sections", "[pylint]", "[mypy]")

    with pytest.raises(AssertionError, match="end marker"):
        slice_tool_section("[pylint] only", "[pylint]", "[mypy]")
