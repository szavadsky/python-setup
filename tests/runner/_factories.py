"""Shared non-fixture factory functions for python-setup runner tests.

Distinct from ``tests/conftest.py``: pytest auto-discovers and auto-injects
``conftest.py`` fixtures, but module-level functions used by
``@pytest.mark.parametrize`` rows at collection time must be importable.
This module is the import target — all test files do
``from tests.runner._factories import ...`` so collection never depends on
which pytest ``rootdir`` setting is active.

Factories here are pure (no side effects). Registry snapshot/restore lives
in the ``isolated_runner_registries`` fixture in ``tests/conftest.py``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from python_setup_lint.runner import (
    TOOLS,
    LintResult,
    RunnerConfig,
    ViolationCount,
    _diff_baseline,
)

if TYPE_CHECKING:
    import pytest

# Type alias for parametrise-row callables that mutate a fake-install + runner.
InstallFakeFn = Callable[..., Any]


# The 11 built-in tool names — used both for the canned-results factory
# (dict-mode ``FakeRunCmd``) and for the "every tool dispatched" assertion
# in the orchestration tests.
ALL_TOOL_NAMES: frozenset[str] = frozenset(t.name for t in TOOLS)


def canned_results_all_tools(
    *,
    exit_code: int = 0,
    stdout: str = "",
    overrides: Mapping[str, LintResult] | None = None,
) -> dict[str, LintResult]:
    """Build the 11-tool canned-result dict for ``fake_run_cmd_factory``.

    Every built-in label maps to a ``LintResult`` with defaults; pass
    *overrides* to vary any subset. Used by the orchestration / smoke
    tests so they stop repeating the 11-key dict literal.
    """
    # Late import to avoid any conftest-collection ordering surprise.
    from python_setup_lint.testing import make_lint_result

    base = {name: make_lint_result(tool_name=name, exit_code=exit_code, stdout=stdout)
            for name in ALL_TOOL_NAMES}
    if overrides:
        base.update(overrides)
    return base


def install_fake_runner(
    monkeypatch: pytest.MonkeyPatch,
    overrides: Mapping[str, LintResult] | None = None,
    *,
    package_name: str | None = "python_setup_lint",
    default_py_dirs: list[str] | None = None,
) -> tuple[Any, RunnerConfig]:
    """Install a fake ``_run_cmd`` on the runner module + build a matching ``RunnerConfig``.

    Replaces the 3-line ``fake = fake_run_cmd_factory({}); monkeypatch.setattr(_runner_module, "_run_cmd", fake)``
    boilerplate duplicated in 25+ runner tests. Returns ``(fake, config)`` so callers
    can introspect ``fake.calls`` after invoking ``run_lint(config=config, ...)`` /
    ``main([..], config=config)``.
    """
    import python_setup_lint.runner as _runner_module
    from python_setup_lint.testing import fake_run_cmd_factory

    fake = fake_run_cmd_factory(dict(overrides) if overrides else {})
    monkeypatch.setattr(_runner_module, "_run_cmd", fake)
    cfg = RunnerConfig(
        cwd=Path.cwd(),
        package_name=package_name,
        default_py_dirs=default_py_dirs if default_py_dirs is not None else ["src", "scripts", "tests"],
    )
    return fake, cfg


def tmp_config(tmp_path: Path, **overrides: Any) -> RunnerConfig:
    """Build a default test ``RunnerConfig`` rooted at *tmp_path*; *overrides* win."""
    defaults: dict[str, Any] = dict(
        cwd=tmp_path, package_name="python_setup_lint", default_py_dirs=["src", "scripts", "tests"],
    )
    defaults.update(overrides)
    return RunnerConfig(**defaults)


def write_baseline(tmp_path: Path, entries: list[dict[str, Any]], name: str = "baseline.json") -> Path:
    """Write a JSON baseline file under *tmp_path* and return its path."""
    path = tmp_path / name
    path.write_text(json.dumps(entries))
    return path


def diff_baseline_with(
    tmp_path: Path,
    saved: dict[str, Any] | list[dict[str, Any]],
    current: Iterable[LintResult],
    *,
    baseline_name: str = "baseline.json",
) -> tuple[list[str], list[dict[str, Any]]]:
    """Write *saved*, run ``_diff_baseline`` against *current*, return ``(violations, reloaded_baseline)``.

    Removes the 4-line write-then-call-then-json.load boilerplate that
    every ``TestBaseline`` test duplicates. The returned ``reloaded`` is
    the post-diff on-disk state (which ``_diff_baseline`` may have mutated
    in place when handling shrinkage).

    Accepts a single saved entry OR a list of saved entries; a single
    dict is wrapped in a list before writing.
    """
    saved_list = [saved] if isinstance(saved, dict) else list(saved)
    baseline_path = write_baseline(tmp_path, saved_list, name=baseline_name)
    violations = _diff_baseline(list(current), baseline_path)
    reloaded = json.loads(baseline_path.read_text())
    return violations, reloaded


def assert_violation_contains_any(violations: list[str], *needles: str) -> None:
    """Assert at least one violation mentions at least one *needle* (case-insensitive)."""
    lowered = [v.lower() for v in violations]
    found = any(any(n in v for v in lowered) for n in needles)
    assert found, (
        f"Expected a violation mentioning any of {needles!r}; got {violations!r}"
    )


def find_tool_entry(entries: list[dict[str, Any]], tool: str) -> dict[str, Any]:
    """Return the FIRST baseline entry whose ``tool`` field equals *tool* (asserts at least one)."""
    matches = [e for e in entries if e.get("tool") == tool]
    assert matches, f"No baseline entry for tool {tool!r} in {entries!r}"
    return matches[0]


def baseline_entry_for_tool(entries: list[dict[str, Any]], tool: str) -> dict[str, Any]:
    """Return the first baseline entry whose ``tool`` equals *tool* (asserts at least one)."""
    return find_tool_entry(entries, tool)


# ── Parametrise tables ────────────────────────────────────────────
# Single source-of-truth for the per-tool / per-flag rows that previously
# existed as one test-per-row with duplicated scaffolding. Each table is a
# list of ``pytest.param(...)`` rows so the ``id`` of the failing row is
# meaningful.

import pytest

# ``_build_command`` rows — one row per (tool spec, kwargs, expected cmd).
# Previously ~20 separate ``TestBuildCommand`` tests each varied a single
# flag. The rows below cover the exact same surface (path/no-path, fix per
# tool, exclude per tool, override-default-paths, no-support flags).
BUILD_COMMAND_CASES: list[pytest.Param] = [
    pytest.param(
        dict(name="test", command=["tool", "check"], supports_path=True, default_paths=["src/"]),
        {}, ["tool", "check", "src/"], id="default_no_flags",
    ),
    pytest.param(
        dict(name="test", command=["tool", "check"]), {}, ["tool", "check"], id="no_default_paths",
    ),
    pytest.param(
        dict(name="test", command=["tool"], supports_path=False),
        dict(path="src/"), ["tool"], id="path_no_support",
    ),
    pytest.param(
        dict(name="test", command=["tool"], supports_path=True),
        dict(path="src/python_setup_lint"), ["tool", "src/python_setup_lint"], id="path_with_support",
    ),
    pytest.param(
        dict(name="test", command=["tool"], supports_path=True, default_paths=["."]),
        dict(path="src/"), ["tool", "src/"], id="path_overrides_default",
    ),
    pytest.param(
        dict(name="test", command=["tool"], supports_fix=False),
        dict(fix=True), ["tool"], id="fix_no_support",
    ),
    pytest.param(
        dict(name="ruff check", command=["ruff", "check"], supports_fix=True,
             fix_flags=("--fix", "--exit-non-zero-on-fix")),
        dict(fix=True), ["ruff", "check", "--fix", "--exit-non-zero-on-fix"], id="fix_ruff",
    ),
    pytest.param(
        dict(name="rumdl check", command=["rumdl", "check"], supports_fix=True, fix_flags=("--fix",)),
        dict(fix=True), ["rumdl", "check", "--fix"], id="fix_rumdl",
    ),
    pytest.param(
        dict(name="ty check", command=["ty", "check"], supports_fix=True, fix_flags=("--fix",)),
        dict(fix=True), ["ty", "check", "--fix"], id="fix_ty",
    ),
    pytest.param(
        dict(name="test", command=["tool"], supports_exclude=False),
        dict(exclude="tests/"), ["tool"], id="exclude_no_support",
    ),
    pytest.param(
        dict(name="tach check", command=["tach", "check"], supports_exclude=True, exclude_flag="-e"),
        dict(exclude="tests/"), ["tach", "check", "-e", "tests/"], id="exclude_tach",
    ),
    pytest.param(
        dict(name="ruff check", command=["ruff", "check"], supports_exclude=True),
        dict(exclude="tests/"), ["ruff", "check", "--exclude", "tests/"], id="exclude_other",
    ),
    pytest.param(
        dict(name="ruff check", command=["ruff", "check"], supports_path=True, supports_exclude=True),
        dict(path="src/", exclude="tests/"),
        ["ruff", "check", "src/", "--exclude", "tests/"], id="exclude_with_path",
    ),
]


# ``_build_statistics_flags`` rows — one row per (tool name, expected flag list).
STATISTICS_FLAG_CASES: list[pytest.Param] = [
    pytest.param("ruff check", ["--statistics"], id="ruff_native"),
    pytest.param("rumdl check", ["--statistics"], id="rumdl_native"),
    pytest.param("pylint", ["--output-format=json2"], id="pylint_json2"),
    pytest.param("pyright check", ["--outputjson"], id="pyright_outputjson"),
    pytest.param("mypy", ["--no-error-summary"], id="mypy_no_error_summary"),
    pytest.param("ty check", ["--output-format", "concise"], id="ty_concise"),
    pytest.param("tach check", ["--output", "json"], id="tach_json"),
    pytest.param("yamllint", ["-f", "parsable"], id="yamllint_parsable"),
]


# ``main([...])`` flag-acceptance rows — every row is one prev. argparse smoke
# test. All share the same ``fake installed + main(args)`` scaffolding; the
# only thing that varies is the CLI args list. The assertion is just that
# the call didn't raise (returns int) — i.e. the flag parses.
MAIN_ARGPARSE_CASES: list[pytest.Param] = [
    pytest.param(["--path", "src/python_setup_lint/runner.py"], id="main_path"),
    pytest.param(["--fix", "--path", "src/python_setup_lint/runner.py"], id="main_fix"),
    pytest.param(["--no-fail-fast", "--path", "src/python_setup_lint/runner.py"], id="main_no_fail_fast"),
    pytest.param(["--exclude", "tests/", "--path", "src/python_setup_lint/runner.py"], id="main_exclude"),
    pytest.param(["--package-name", "python_setup_lint", "--path", "src/python_setup_lint/runner.py"],
                 id="main_package_name"),
    pytest.param(["--tools", "ruff check,mypy", "--path", "src/python_setup_lint/runner.py"], id="main_tools"),
    pytest.param(["--default-py-dirs", "src,tests", "--path", "src/python_setup_lint/runner.py"],
                 id="main_default_py_dirs"),
    pytest.param([], id="main_no_args_backward_compat"),
]


# ``main([... --statistics ...])`` flag-acceptance rows for T7 group/sort.
MAIN_GROUP_SORT_CASES: list[pytest.Param] = [
    pytest.param(["--statistics", "--group", "tool", "--path", "src/python_setup_lint/runner.py"],
                 id="group_tool"),
    pytest.param(["--statistics", "--group", "rule", "--path", "src/python_setup_lint/runner.py"],
                 id="group_rule"),
    pytest.param(["--statistics", "--sort-by-rule", "--path", "src/python_setup_lint/runner.py"],
                 id="sort_by_rule"),
    pytest.param(
        ["--statistics", "--group", "rule", "--sort-by-rule", "--path", "src/python_setup_lint/runner.py"],
        id="group_and_sort_by_rule"),
]


# Per-parser statistics table. Each row carries (tool_name, raw_input,
# expected_rule_count_pairs, stderr). Replaces 11 3-5-test classes
# (TestParseRuffStatistics, TestParseRumdlStatistics, ...) with one
# parametrised test body that exercises the per-tool parser dispatcher.
#
# The cases use the parsers' direct call signature (parser(stdout, stderr)).
# They are dispatched from the test body via ``_STATISTICS_PARSERS[tool]``.
ParserRow = tuple[str, str, str, list[tuple[str, int]]]
PARSER_STATISTICS_CASES: list[pytest.Param] = [
    # ruff
    pytest.param("ruff check",
        "Count\tCode\tDescription\n------\t----\t-----------\n3\tF401\tmodule imported but unused\n1\tE501\tline too long\n",
        "", [("F401", 3), ("E501", 1)], id="ruff_typical"),
    pytest.param("ruff check", "", "", [], id="ruff_empty"),
    pytest.param("ruff check", "No violations found\n", "", [], id="ruff_no_header"),
    pytest.param("ruff check",
        "Count\tCode\tDescription\n------\t----\t-----------\n2\tF401\tsomething\n2\tF401\tsomething else\n",
        "", [("F401", 4)], id="ruff_multiline_grouped"),
    # rumdl (per-violation format — no --statistics flag)
    pytest.param("rumdl check",
        "f.md:1:1: [MD041] First line in file should be a level 1 heading\nf.md:3:1: [MD012] Multiple consecutive blank lines\n",
        "", [("MD041", 1), ("MD012", 1)], id="rumdl_typical"),
    pytest.param("rumdl check",
        "f.md:1:1: [MD041] First line\nf.md:2:1: [MD041] Another\n",
        "", [("MD041", 2)], id="rumdl_multiple_same_rule"),
    pytest.param("rumdl check", "", "", [], id="rumdl_empty"),
    pytest.param("rumdl check", "Success: No issues found in 1 file (12ms)\n", "", [], id="rumdl_no_issues"),
    # pylint json2
    pytest.param("pylint",
        '[{"symbol":"unused-import"},{"symbol":"unused-import"},{"symbol":"too-complex"}]',
        "", [("unused-import", 2), ("too-complex", 1)], id="pylint_typical"),
    pytest.param("pylint", "[]", "", [], id="pylint_empty_array"),
    pytest.param("pylint", "not json", "", [], id="pylint_invalid_json"),
    pytest.param("pylint", '{"key":"val"}', "", [], id="pylint_non_list"),
    pytest.param("pylint",
        '{"messages":[{"symbol":"unused-import"},{"symbol":"too-complex"}],"status":1}',
        "", [("unused-import", 1), ("too-complex", 1)], id="pylint_json2_dict_shape"),
    pytest.param("pylint",
        '{"messages":[],"status":0}',
        "", [], id="pylint_json2_dict_empty"),
    pytest.param("pylint",
        '{"messages":[{"symbol":"unused-import"},{"symbol":"unused-import"}],"status":1}',
        "", [("unused-import", 2)], id="pylint_json2_dict_duplicates"),
    # pyright outputjson
    pytest.param("pyright check",
        '{"generalDiagnostics":[{"rule":"reportGeneralTypeIssues"},{"rule":"reportGeneralTypeIssues"},{"rule":"reportOptionalMemberAccess"}]}',
        "", [("reportGeneralTypeIssues", 2), ("reportOptionalMemberAccess", 1)], id="pyright_typical"),
    pytest.param("pyright check", '{"generalDiagnostics":[]}', "", [], id="pyright_empty_diagnostics"),
    pytest.param("pyright check", '{"summary":{}}', "", [], id="pyright_missing_key"),
    pytest.param("pyright check", "bad", "", [], id="pyright_invalid_json"),
    # pyright verify types
    pytest.param("pyright verify types",
        '{"typeCompleteness":{"symbols":[{"symbolName":"Foo","completeness":0.5},{"symbolName":"Bar","completeness":1.0}]}}',
        "", [("verifytypes:incomplete", 1)], id="verifytypes_with_incomplete"),
    pytest.param("pyright verify types",
        '{"typeCompleteness":{"symbols":[{"symbolName":"Foo","completeness":1.0}]}}',
        "", [], id="verifytypes_all_complete"),
    pytest.param("pyright verify types", "bad", "", [], id="verifytypes_invalid_json"),
    pytest.param("pyright verify types", "{}", "", [], id="verifytypes_missing_type_completeness"),
    # mypy stderr
    pytest.param("mypy", "",
        "file.py:1: error: Unused import [no-unused-import]\nfile.py:2: error: Not callable [operator]\n",
        [("no-unused-import", 1), ("operator", 1)], id="mypy_typical"),
    pytest.param("mypy", "", "", [], id="mypy_empty"),
    # ty concise
    pytest.param("ty check", "file.py:1:1: X001 some message\nfile.py:2:2: X002 another\n",
        "", [("X001", 1), ("X002", 1)], id="ty_typical"),
    pytest.param("ty check", "", "", [], id="ty_empty"),
    # tach json
    pytest.param("tach check", '{"errors":[{"message":"bad import"}]}',
        "", [("tach:error", 1)], id="tach_with_errors"),
    pytest.param("tach check", '{"errors":[]}', "", [], id="tach_no_errors"),
    pytest.param("tach check", "bad", "", [], id="tach_invalid_json"),
    # yamllint parsable
    pytest.param("yamllint", "f.yaml:1:1:trailing-spaces: message 1\nf.yaml:2:2:trailing-spaces: message 2\n",
        "", [("trailing-spaces", 2)], id="yamllint_typical"),
    pytest.param("yamllint", "", "", [], id="yamllint_empty"),
    # stubtest stderr
    pytest.param("mypy.stubtest", "",
        "error: X001 first error\nerror: X001 second error\nerror: X002 third error\n",
        [("X001", 2), ("X002", 1)], id="stubtest_typical"),
    pytest.param("mypy.stubtest", "info: something\n", "", [], id="stubtest_no_error_prefix"),
    # detect-secrets json
    pytest.param("detect-secrets",
        '{"results":{"file.py":[{"type":"Secret A"},{"type":"Secret A"},{"type":"Secret B"}]}}',
        "", [("Secret A", 2), ("Secret B", 1)], id="detect_secrets_typical"),
    pytest.param("detect-secrets", '{"results":{}}', "", [], id="detect_secrets_empty"),
    pytest.param("detect-secrets", "bad", "", [], id="detect_secrets_invalid_json"),
]


# ── ``_diff_baseline`` invariant matrix ────────────────────────────
# Single source-of-truth for the ``test_diff_baseline_matrix`` rows.
# Each row: (saved_baseline, current_make_lint_kwargs, want_kind,
#            post_assert_id). Surrounding write+diff+reload boilerplate
# lives in ``diff_baseline_with``.
#
# ``want_kind``: ``"no_violations"`` ⇒ assert empty; otherwise the kind
#                substring matched case-insensitively against the returned
#                violations.
# ``post_assert_id``: selects a small post-diff assertion closure over the
#                reloaded baseline JSON. ``"no_post"`` ⇒ no extra assertion.

DIFF_BASELINE_CASES: list[pytest.Param] = [
    # ── pure shrinkage auto-records silently ───────────────────
    pytest.param(
        {"tool": "ruff check", "exit_code": 0,
         "output": "src/a.py:1: error A\nsrc/b.py:2: error B"},
        {"ruff check": "src/a.py:1: error A", "mypy": "src/c.py:3: error C"},
        "no_violations", "ruff_shrunk_b_removed",
        id="pure_shrinkage_auto_records",
    ),
    pytest.param(
        {"tool": "ruff check", "exit_code": 0, "output": "src/a.py:1: error A"},
        {"ruff check": "src/a.py:1: error A\nsrc/b.py:2: error B"},
        "output changed", "no_post",  # baseline UNCHANGED for additions
        id="pure_addition_flags_regression",
    ),
    pytest.param(
        {"tool": "ruff check", "exit_code": 0,
         "output": "src/a.py:1: error A\nsrc/b.py:2: error B"},
        {"ruff check": "src/a.py:1: error A\nsrc/c.py:3: error C"},
        "output changed", "b_removed_c_not_added",  # mixed: shrink records, addition flags
        id="mixed_shrinkage_and_addition",
    ),
    pytest.param(
        {"tool": "pylint", "exit_code": 0,
         "output": "1 src/a.py:1:1: W0611: unused-import\n1 src/b.py:2:2: C0114: missing-module-docstring"},
        {"pylint": "src/a.py:1:1: W0611: unused-import"},
        "no_violations", "c0114_removed",
        id="pylint_shrinkage_auto_records",
    ),
    # The exit_code_shrink case (saved exit_code=1 output non-empty →
    # current exit_code=0 output empty → shrinkage records new exit_code=0)
    # needs a non-zero current exit_code, which the compact map builder doesn't
    # support — kept as a standalone test in ``TestDiffBaselineEdgeCases``.
    pytest.param(
        {"tool": "ruff check", "exit_code": 0, "output": "ok"},
        {"ruff check": "ok"},  # mypy in baseline but absent from current
        "no_violations", "mypy_removed",
        id="tool_removed_shrinkage_auto_records",
    ),
    pytest.param(
        {"tool": "pyright check", "exit_code": 0,
         "diagnostics": {"summary": {"errorCount": 2, "warningCount": 0}}},
        {"pyright check": {"summary": {"errorCount": 1, "warningCount": 0}}},
        "no_violations", "diag_count_1",
        id="diagnostics_shrinkage_auto_records",
    ),
    pytest.param(
        {"tool": "pylint", "exit_code": 0, "output": "1 src/a.py:1:1: W0611: unused-import"},
        {"pylint": "src/a.py:1:1: W0611: unused-import\nsrc/b.py:2:2: C0114: missing-module-docstring"},
        "output changed", "no_post",
        id="pylint_addition_flags_regression",
    ),
    pytest.param(
        {"tool": "rumdl check", "exit_code": 0,
         "output": "src/a.md:1 MD012 (10ms)\nsrc/b.md:3 MD013 (20ms)"},
        {"rumdl check": "src/a.md:1 MD012 (5ms)"},
        "no_violations", "md013_removed",
        id="rumdl_shrinkage_auto_records_ignoring_timing",
    ),
    pytest.param(
        {"tool": "mypy", "exit_code": 0, "output": "src/a.py:1: error"},
        {"mypy": ""},
        "no_violations", "output_emptied",
        id="output_to_empty_shrinkage",
    ),
    # ── D6/D7 invariants ─────────────────────────────────────
    pytest.param(
        {"tool": "mypy", "exit_code": 0, "output": "src/a.py:1: error A  \nsrc/b.py:2: error B  "},
        {"mypy": "src/a.py:1: error A\nsrc/b.py:2: error B"},
        "no_violations", "no_post",  # D6: trailing whitespace only → not flagged
        id="whitespace_normalization_d6",
    ),
    pytest.param(
        {"tool": "mypy", "exit_code": 0, "output": "src/a.py:1: error A"},
        {"mypy": "src/a.py:1: error A\nsrc/a.py:1: error A\nsrc/a.py:1: error A"},
        "no_violations", "no_post",  # D7: set semantics — count increase not flagged
        id="duplicate_line_count_set_semantics_d7",
    ),
    # ── ruff ordering-insensitivity (line-sort baseline) ─────
    pytest.param(
        {"tool": "ruff check", "exit_code": 0,
         "output": "src/a.py:1: error A\nsrc/b.py:2: error B"},
        {"ruff check": "src/b.py:2: error B\nsrc/a.py:1: error A"},
        "no_violations", "no_post",
        id="ruff_ordering_insensitive",
    ),
    # ── diagnostics-loss regression (D4) ──────────────────────
    pytest.param(
        {"tool": "pyright check", "exit_code": 0,
         "diagnostics": {"summary": {"errorCount": 1, "warningCount": 0}}},
        {"pyright check": "non-JSON"},  # current stdout is plain text, not JSON
        "diagnostics lost", "diag_preserved",
        id="diagnostics_lost_regression_d4",
    ),
    # ── duplicate tool in baseline (D3) ──────────────────────
    pytest.param(
        {"tool": "ruff check", "exit_code": 0, "output": "src/a.py:1: error A"},
        {"ruff check": "src/a.py:1: error A"},
        "no_violations", "all_mypy_dupes_removed",
        id="duplicate_tool_in_baseline_d3",
    ),
]


# Per-row post-diff baseline assertion dispatch table — used by
# ``test_diff_baseline_matrix`` to assert on the reloaded on-disk JSON.
# Keys are ``post_assert_id`` strings; values are callables
# ``reloaded -\u003e None`` raising AssertionError on failure.

def _entries_for_tool(entries: list[dict[str, Any]], tool: str) -> list[dict[str, Any]]:
    return [e for e in entries if e["tool"] == tool]


def _assert_removed(entries: list[dict[str, Any]], tool: str) -> None:
    assert not _entries_for_tool(entries, tool), f"{tool!r} should be removed from {entries!r}"


def _no_op(_reloaded: list) -> None:
    """No post-diff assertion — row has no bespoke baseline check."""


def _ruff_shrunk_b_removed(reloaded: list) -> None:
    ruff = baseline_entry_for_tool(reloaded, "ruff check")
    assert "src/b.py:2: error B" not in ruff.get("output", "")


def _b_removed_c_not_added(reloaded: list) -> None:
    ruff = baseline_entry_for_tool(reloaded, "ruff check")
    assert "src/b.py:2: error B" not in ruff.get("output", "")  # shrunken
    assert "src/c.py:3: error C" not in ruff.get("output", "")  # not added


def _c0114_removed(reloaded: list) -> None:
    assert "C0114" not in baseline_entry_for_tool(reloaded, "pylint").get("output", "")


def _exit_0_recorded(reloaded: list) -> None:
    assert baseline_entry_for_tool(reloaded, "mypy")["exit_code"] == 0


def _mypy_removed(reloaded: list) -> None:
    _assert_removed(reloaded, "mypy")
    assert len(reloaded) == 1 and reloaded[0]["tool"] == "ruff check"


def _diag_count_1(reloaded: list) -> None:
    assert reloaded[0]["diagnostics"]["summary"]["errorCount"] == 1


def _md013_removed(reloaded: list) -> None:
    assert "MD013" not in baseline_entry_for_tool(reloaded, "rumdl check").get("output", "")


def _output_emptied(reloaded: list) -> None:
    assert baseline_entry_for_tool(reloaded, "mypy").get("output", "") == ""


def _diag_preserved(reloaded: list) -> None:
    # Regression path: baseline diagnostics should NOT be replaced with None.
    assert reloaded[0]["diagnostics"] is not None


def _all_mypy_dupes_removed(reloaded: list) -> None:
    _assert_removed(reloaded, "mypy")
    assert len(_entries_for_tool(reloaded, "ruff check")) == 1


# Dispatch ID → post-diff assertion callable.
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


def build_current_results(saved_baseline: dict[str, Any] | list[dict[str, Any]],
                           current_map: dict[str, Any]) -> list[LintResult]:
    """Construct ``LintResult`` list from a matrix row's compact ``current_map``.

    The matrix rows carry the current state as a ``{tool_name: stdout_or_diag}``
    shortcut: every tool that's in the saved baseline AND in the map produces
    a ``LintResult(tool_name=tool, exit_code=0, stdout=value)`` (or a
    JSON-emitted dict for pyright-style diagnostics). Tools in the saved
    baseline but absent from the map are considered "removed" — they do not
    appear in the current results (matching the shrinkage-auto-records
    invariant the row tests). Map values that are dict/list are JSON-serialised.

    Accepts a single saved entry OR a list of saved entries.

    NOTE: this builder always emits exit_code=0 (the runner's success state).
    Rows that need a non-zero current exit_code should bypass this helper and
    construct the ``LintResult`` list directly (e.g. the ``exit_code_shrink``
    rows test an exit-code-1→0 transition).
    """
    from python_setup_lint.testing import make_lint_result  # local import per original layout

    if isinstance(saved_baseline, dict):
        saved_entries = [saved_baseline]
    else:
        saved_entries = saved_baseline

    current: list[LintResult] = []
    for entry in saved_entries:
        tool = entry["tool"]
        if tool not in current_map:
            continue  # this tool was removed from baseline; skip
        value = current_map[tool]
        if isinstance(value, (dict, list)):
            current.append(make_lint_result(tool_name=tool, stdout=json.dumps(value)))
        else:
            current.append(make_lint_result(tool_name=tool, stdout=str(value)))
    return current


def diff_violation_kind(violations: list[str], want: str) -> None:
    """Assert *want* substring is in any violation (case-insensitive)."""
    lowered = [v.lower() for v in violations]
    assert any(want in v for v in lowered), f"Expected {want!r} in violations; got {violations!r}"


def extra_block(entries: str) -> str:
    """Wrap one-or-more ``[[tool.python-setup-lint.extra-tools]]`` body lines."""
    return f"[tool.python-setup-lint]\n[[tool.python-setup-lint.extra-tools]]\n{entries}"


def write_pyproject(tmp_path: Path, body: str) -> Path:
    """Write a synthetic ``pyproject.toml`` body under *tmp_path*, reset extras cache, return resolved path."""
    from python_setup_lint.runner import _reset_extra_tools_cache
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(body, encoding="utf-8")
    _reset_extra_tools_cache()
    return pyproject.resolve()


# ── Extra-tools test data (moved from test_extra_tools.py) ────────

BUILTIN_NAME = "ruff check"

VALID_EXTRA_BLOCK = (
    'name = "grep-noqa-scan"\n'
    'command = ["grep", "-rnE", "--exclude-dir=__pycache__", '
    '"--include=*.py", "noqa: "]\n'
    "supports_path = true\n"
    'default_paths = ["src/", "tests/"]\n'
    'parse_strategy = "regex_count"\n'
    'parse_regex = "^[^:]+:\\\\d+:.*# noqa: (\\\\S+)"\n'
)

EMPTY_LOADER_CASES: list = [
    ("no_pyproject", None),
    ("no_section", "[tool.python-setup-lint]\nsome = 1\n"),
    ("empty_array", "[tool.python-setup-lint]\nextra-tools = []\n"),
]


# Combined R4 reason-match table — one pytest.param per previously-distinct
# named test. (body, reason_want, want_kind) where want_kind is "exact" or
# "starts_with". Locked per DESIGN-8 D6 — production code is source-of-truth.
R4_EXACT_REASON_CASES: list[pytest.Param] = [
    pytest.param(
        extra_block('name = "x"\ncommand = ["x"]\nbogus_field = 1\n'),
        "unknown field: ", "starts_with", id="unknown_field",
    ),
    pytest.param(
        extra_block('name = "x"\n'), "missing required field: command", "exact",
        id="missing_required_field",
    ),
    pytest.param(
        extra_block('name = "x"\ncommand = ["x"]\nparse_strategy = "regex_count"\n'),
        "missing required field: parse_regex", "starts_with",
        id="regex_count_requires_parse_regex",
    ),
    pytest.param(
        extra_block('name = "x"\ncommand = ["x"]\nparse_strategy = "regex_count"\n'
                    'parse_regex = "no_groups_here"\n'),
        "regex missing or != 1 capture group", "starts_with",
        id="regex_count_bad_group_count",
    ),
    pytest.param(
        extra_block('name = "dup"\ncommand = ["x"]\n')
        + "[[tool.python-setup-lint.extra-tools]]\n"
        + 'name = "dup"\ncommand = ["x"]\n',
        "duplicate within file: dup", "exact",
        id="duplicate_within_file",
    ),
    pytest.param(
        extra_block(f'name = "{BUILTIN_NAME}"\ncommand = ["x"]\n'),
        f"duplicate vs built-in: {BUILTIN_NAME}", "exact",
        id="duplicate_vs_builtin",
    ),
    pytest.param(
        extra_block('name = 123\ncommand = ["x"]\n'),
        "wrong type: name must be non-empty str", "exact", id="name_non_str",
    ),
    pytest.param(
        extra_block('name = "   "\ncommand = ["x"]\n'),
        "wrong type: name must be non-empty str", "exact", id="name_whitespace",
    ),
    pytest.param(
        extra_block('name = "x"\ncommand = "ruff"\n'),
        "wrong type: command must be non-empty list[str]", "exact", id="command_scalar",
    ),
    pytest.param(
        extra_block('name = "x"\ncommand = ["x", 1]\n'),
        "wrong type: command must be list[str]", "exact", id="command_non_str_parts",
    ),
]


# Wrong-type flag fields (boolean / list / scalar shapes) — each row follows
# the valid `name = "x"`/`command = ["x"]` prefix; the flag varies.
R4_FLAG_WRONG_TYPE_CASES: list[pytest.Param] = [
    pytest.param('supports_fix = "yes"\n', "wrong type: supports_fix must be bool", id="supports_fix"),
    pytest.param("supports_path = 1\n", "wrong type: supports_path must be bool", id="supports_path"),
    pytest.param('supports_exclude = "no"\n', "wrong type: supports_exclude must be bool",
                id="supports_exclude"),
    pytest.param('default_paths = "src/"\n', "wrong type: default_paths must be list[str]",
                id="default_paths_scalar"),
    pytest.param('default_paths = ["x", 1]\n', "wrong type: default_paths must be list[str]",
                id="default_paths_non_str_parts"),
    pytest.param("config_flag = 12\n", "wrong type: config_flag must be str | list[str]",
                id="config_flag_int"),
    pytest.param('config_flag = ["--x", 1]\n', "wrong type: config_flag must be str | list[str]",
                id="config_flag_non_str_parts"),
    pytest.param("parse_strategy = 7\n", "wrong type: parse_strategy must be str",
                id="parse_strategy_int"),
    pytest.param('parse_strategy = "bogus"\n', "bad enum: parse_strategy 'bogus'",
                id="parse_strategy_bad_enum"),
]


REGEX_BAD_GROUP_CASES: list[str] = [
    "no_groups_here",   # zero capture groups
    "(a)(b)",           # two capture groups
    "(unclosed",        # unparseable regex
]


# Downstream-integration test blocks + cases (T11 extra-tools pipeline).
REGEX_BLOCK = (
    'name = "regextool"\n'
    'command = ["fake-regex-cli"]\n'
    "supports_path = true\n"
    'default_paths = []\n'
    'parse_strategy = "regex_count"\n'
    'parse_regex = "^(?P<rule>[A-Z]+[0-9]+): .*"\n'
)

NONE_BLOCK = (
    'name = "nonestattool"\n'
    'command = ["fake-none-cli"]\n'
    "supports_path = true\n"
    'default_paths = []\n'
    'parse_strategy = "none"\n'
)

DOWNSTREAM_CASES: list[pytest.Param] = [
    pytest.param(
        REGEX_BLOCK, "regextool", ["fake-regex-cli"],
        "RC1: bad line\nRC2: worse line\nRC1: another",
        [("regextool", "RC1", 2), ("regextool", "RC2", 1)],
        id="regex_count_extra_emits_rule_counts",
    ),
    pytest.param(
        NONE_BLOCK, "nonestattool", ["fake-none-cli"],
        "noise\nthat has no rule ids\nRC1: ignored too\n",
        [],
        id="parse_strategy_none_skips_aggregate",
    ),
]


# Observability test block: a regex_count extra whose stdout has 2 RC1 + 1 RC2.
EXTRA_OBSERV_BLOCK = REGEX_BLOCK
EXTRA_OBSERV_STDOUT = "RC1: bad line\nRC2: worse line\nRC1: another"
EXTRA_OBSERV_NAME = "regextool"


# ── T8 fail-fast malformation table (moved from test_lint_runner.py) ─
# Each row: (pyproject_body, expected_reason_or_substring, exact_match).
# When ``exact_match`` is True the reason matches exactly; otherwise it
# matches the listed substring. All rows assert ``err.location == str(pyproject)``.
MALFORMATION_CASES: list[pytest.Param] = [
    pytest.param(
        '[tool.python-setup-lint]\nextra-tools = "not-a-list"\n',
        "wrong type: extra-tools must be a list of tables", True,
        id="malformed_extra_tools_section",
    ),
    pytest.param(
        '[tool.python-setup-lint]\n[[tool.python-setup-lint.extra-tools]]\nname = "no-command"\n',
        "missing required field: command", True,
        id="missing_required_key",
    ),
    pytest.param(
        '[tool.python-setup-lint]\n[[tool.python-setup-lint.extra-tools]]\n'
        'name = "my-tool"\ncommand = ["tool"]\nfoo = "bar"\n',
        "unknown field: ['foo']; allowed:", False,
        id="unknown_field",
    ),
    pytest.param(
        '[tool.python-setup-lint]\n[[tool.python-setup-lint.extra-tools]]\n'
        'name = "my-tool"\ncommand = ["tool"]\nparse_strategy = "invalid-strat"\n',
        "bad enum: parse_strategy", False,
        id="bad_parse_strategy_enum",
    ),
    pytest.param(
        "[[[\ninvalid toml\n",
        "pyproject unreadable:", False,
        id="unreadable_pyproject_toml",
    ),
]


# ── Grouped statistics output table (moved from test_lint_runner.py) ─
# Each row: (group, counts, header, header_markers, sum_tokens).
GROUPED_OUTPUT_CASES: list[pytest.Param] = [
    pytest.param(
        "tool",
        [ViolationCount("tool_a", "A001", 10), ViolationCount("tool_a", "B001", 5),
         ViolationCount("tool_b", "A001", 3)],
        "VIOLATION STATISTICS (grouped by tool)",
        ["[tool_a]", "[tool_b]", "Subtotal", "Total"],
        ["15", "3"],  # subtotals (tool_a=15, tool_b=3)
        id="group_tool_has_subtotals",
    ),
    pytest.param(
        "rule",
        [ViolationCount("tool_a", "Z001", 3), ViolationCount("tool_b", "A001", 7),
         ViolationCount("tool_b", "A001", 5)],
        "VIOLATION STATISTICS (grouped by rule)",
        ["[A001]", "[Z001]", "Subtotal"],
        ["12", "3"],  # A001=12, Z001=3
        id="group_rule_has_per_rule_subtotals",
    ),
    pytest.param(
        "file",
        [ViolationCount("tool_x", "R001", 1)],
        "VIOLATION STATISTICS (grouped by tool)",
        ["[tool_x]"],
        [],
        id="group_file_aliases_to_tool",
    ),
    pytest.param(
        "tool", [], "VIOLATION STATISTICS (grouped by tool)",
        [], ["No violations found"],
        id="group_empty_prints_no_violations",
    ),
]


# Clean extras-pyproject body for the T8 positive-path integration test
# (one ``[[...]]`` extra named ``t8-grep-noqa`` using ``parse_strategy=raw_lines``).
CLEAN_EXTRAS_PYPROJECT_BODY = (
    '[project]\nname = "t8-clean"\nversion = "0.0.1"\n\n'
    '[tool.python-setup-lint]\n[[tool.python-setup-lint.extra-tools]]\n'
    'name = "t8-grep-noqa"\ncommand = ["grep", "-rnE", "noqa: "]\n'
    'supports_path = true\ndefault_paths = ["src/"]\nparse_strategy = "raw_lines"\n'
)


def lint_config(cwd: Path, *, package_name: str | None = "python_setup_lint",
                tools_override: list[str] | None = None) -> RunnerConfig:
    """Build a test RunnerConfig rooted at *cwd* with optional tools override."""
    return RunnerConfig(cwd=cwd, package_name=package_name, tools_override=tools_override)


def _make_result(tool_name: str, exit_code: int = 0, stdout: str = ""):
    """Lazy make_lint_result wrapper (avoids eager import of testing module)."""
    from python_setup_lint.testing import make_lint_result
    return make_lint_result(tool_name=tool_name, exit_code=exit_code, stdout=stdout)


# ── FakeRunCmd dispatch contract table (moved from test_testing_fakes.py) ─
# Each row: (factory_kind, results_for_factory, calls_to_make,
#           expected_exit_per_call, expected_tool_name_per_call).
# ``factory_kind`` picks which ``fake_run_cmd_factory`` shape to exercise.
DISPATCH_CASES: list[pytest.Param] = [
    pytest.param(
        "dict",
        {"ruff check": _make_result("ruff check", exit_code=1, stdout="issues")},
        [(["ruff", "check", "src/"], "ruff check")],
        [1], ["ruff check"], id="dict_known_label_returns_canned",
    ),
    pytest.param(
        "dict",
        {"ruff check": _make_result("ruff check")},
        [(["python", "-m", "mypy.stubtest"], "mypy.stubtest")],
        [0], ["mypy.stubtest"], id="dict_unknown_label_returns_zero_exit_empty",
    ),
    pytest.param(
        "dict",
        {},
        [(["ruff", "check", "."], "ruff check")],
        [0], ["ruff check"], id="dict_empty_returns_zero_exit_empty",
    ),
    pytest.param(
        "list",
        [_make_result("ruff check", exit_code=0), _make_result("mypy", exit_code=1)],
        [(["ruff", "check", "."], "ruff check"), (["mypy", "."], "mypy")],
        [0, 1], ["ruff check", "mypy"], id="list_returns_results_in_order",
    ),
    pytest.param(
        "list",
        [],
        [(["ruff", "check", "."], "ruff check")],
        [0], ["ruff check"], id="list_empty_returns_zero_exit_empty",
    ),
]


# Cmd + label capture table — shared by dict + list modes (moved from test_testing_fakes.py).
# Each row: (results_for_factory, calls_to_make, expected_records [{cmd, label}]).
CALLS_CAPTURED_CASES: list[pytest.Param] = [
    pytest.param(
        {"ruff check": _make_result("ruff check")},
        [(["ruff", "check", "src/", "--fix"], "ruff check")],
        [dict(label="ruff check", cmd=["ruff", "check", "src/", "--fix"])],
        id="dict_single",
    ),
    pytest.param(
        {"ruff check": _make_result("ruff check"), "mypy": _make_result("mypy", exit_code=1)},
        [(["ruff", "check", "."], "ruff check"), (["mypy", "."], "mypy")],
        [dict(label="ruff check", cmd=["ruff", "check", "."]),
         dict(label="mypy", cmd=["mypy", "."])],
        id="dict_multiple",
    ),
    pytest.param(
        [_make_result("ruff check")],
        [(["ruff", "check", "--fix"], "ruff check")],
        [dict(label="ruff check", cmd=["ruff", "check", "--fix"])],
        id="list_single",
    ),
]


# Smoke-integration invariant table for ``test_testing_fakes`` — rows:
# (run_lint_kwargs, predicate(FakeRunCmd) → bool). Covers tool count, --fix
# propagation, --exclude propagation, package_name=None skip.
RUN_LINT_FAKE_INVARIANT_CASES: list[pytest.Param] = [
    # every tool dispatched, each cmd non-empty
    pytest.param(dict(path="src/python_setup_lint/runner.py"),
        lambda f: len(f.calls) == 11 and all(len(c.cmd) > 0 and c.label for c in f.calls),
        id="all_11_tools_dispatched"),
    # --fix propagates to ruff/rumdl/ty
    pytest.param(dict(path="src/python_setup_lint/runner.py", fix=True),
        lambda f: all("--fix" in c.cmd for c in f.calls if c.label in {"ruff check", "rumdl check", "ty check"}),
        id="fix_flag_propagates_to_supports_fix_labels"),
    # --exclude propagates to tach/ruff/rumdl/ty
    pytest.param(dict(path="src/python_setup_lint/runner.py", exclude="tests/"),
        lambda f: all(("--exclude" in c.cmd or "-e" in c.cmd)
                      for c in f.calls if c.label in {"tach check", "ruff check", "rumdl check", "ty check"}),
        id="exclude_flag_propagates_to_supports_exclude_labels"),
    # package_name=None skips stubtest + verifytypes → 9 dispatched
    pytest.param(dict(package_name=None, path="src/python_setup_lint/runner.py"),
        lambda f: (len(f.calls) == 9 and "mypy.stubtest" not in {c.label for c in f.calls}
                   and "pyright verify types" not in {c.label for c in f.calls}),
        id="package_name_none_skips_stubtest_verifytypes"),
]


# ── _diff_baseline edge-case tables (moved from test_lint_runner.py) ─
# Three parametrise tables that previously lived inline in
# ``TestDiffBaselineEdgeCases``. Split because each needs a different
# fixture shape (current map / direct LintResult list / baseline path).


# timeInSec skip / diagnostics-present / identical saved=current → no violation.
# Row: (saved, current_map, want_kind).
DIFF_EDGE_CASES: list[pytest.Param] = [
    pytest.param(
        {"tool": "pyright check", "exit_code": 0,
         "diagnostics": {"summary": {"errorCount": 1, "timeInSec": 10.0, "filesAnalyzed": 100}}},
        {"pyright check": {"summary": {"errorCount": 1, "timeInSec": 15.0, "filesAnalyzed": 100}}},
        "no_violations", id="pyright_ignores_time_in_sec",
    ),
    pytest.param(
        {"tool": "pyright check", "exit_code": 0, "diagnostics": {"summary": {"errorCount": 1}}},
        {"pyright check": {"summary": {"errorCount": 1}}},
        "no_violations", id="diagnostics_used_when_present",
    ),
    pytest.param(
        {"tool": "test", "exit_code": 0, "output": "ok"},
        {"test": "ok"}, "no_violations", id="identical",
    ),
]


# Exit-code changed / shrinkage / new-tool rows — each builds LintResult directly.
# Row: (saved, results, want_kind).
DIFF_EDGE_INVARIANTS: list[pytest.Param] = [
    # exit_code 0→1 (other fields identical) → flags ``exit code``
    pytest.param({"tool": "test", "exit_code": 0, "output": "ok"},
                 [_make_result("test", exit_code=1, stdout="ok")],
                 "exit code", id="exit_code_changed_flags_regression"),
    # exit_code 1→0 (output empties) → silent auto-record, exit_code rewritten to 0
    pytest.param({"tool": "mypy", "exit_code": 1, "output": "some error"},
                 [_make_result("mypy", exit_code=0, stdout="")],
                 "no_violations", id="exit_code_shrinkage_auto_records"),
    # new tool in current (no baseline entry) → ``no baseline entry``
    pytest.param({"tool": "tool_a", "exit_code": 0, "output": ""},
                 [_make_result("tool_a"), _make_result("tool_b")],
                 "no baseline entry", id="new_tool_flags_regression"),
]


# Baseline path error rows — (baseline_setup_kind, body_or_None, want_substr_or_None).
# kind: "missing" / "invalid" / "empty".
DIFF_BASELINE_PATH_ERRORS: list[pytest.Param] = [
    pytest.param("missing", None, "not found", id="no_baseline_file"),
    pytest.param("invalid", "not valid json", "Cannot read", id="invalid_json"),
    pytest.param("empty", "[]", None, id="empty_baseline_no_current"),
]


# ── Small parametrize tables (moved from test_lint_runner.py) ────


# Print result format rows: (exit_code, stdout, stderr, want_tokens).
PRINT_FORMAT_CASES: list[pytest.Param] = [
    pytest.param(0, "all good\n", None, ["[mytool]", "PASSED", "all good"], id="passed"),
    pytest.param(2, None, "error: x\n", ["FAILED", "exit=2", "error: x"], id="failed"),
]


# ``TestSortCounts`` default ordering row.
SORT_DEFAULT_COUNTS: list[ViolationCount] = [
    ViolationCount("tool_b", "Z001", 5),
    ViolationCount("tool_a", "A001", 10),
    ViolationCount("tool_a", "B001", 5),
]
# ``TestSortCounts`` --sort-by-rule ordering row.
SORT_BY_RULE_COUNTS: list[ViolationCount] = [
    ViolationCount("tool_b", "Z001", 5),
    ViolationCount("tool_a", "A001", 10),
    ViolationCount("tool_b", "A001", 3),
]
# ``TestGroupedOutput.test_group_rule_with_sort_by_rule_orders_sections`` counts row.
GROUPED_SORT_BY_RULE_COUNTS: list[ViolationCount] = [
    ViolationCount("tool_b", "A001", 3),
    ViolationCount("tool_a", "A001", 10),
    ViolationCount("tool_a", "Z001", 5),
]


# ``TestRunCmd`` rows: (cmd, label, exit_predicate, stdout_want_or_None).
RUN_CMD_CASES: list[pytest.Param] = [
    pytest.param(["echo", "hello"], "echo", lambda c: c == 0, "hello\n", id="success"),
    pytest.param(["false"], "false", lambda c: c != 0, None, id="failure"),
]


# ``TestPathHelpers._find_py_files`` boundary rows: (paths, expected).
FIND_PY_FILES_BOUNDARY_CASES: list[pytest.Param] = [
    pytest.param(["nonexistent_dir_xyz"], [], id="nonexistent_dir"),
    pytest.param(["src/python_setup_lint/runner/types.py"], ["src/python_setup_lint/runner/types.py"], id="single_file"),
]


# ``TestPathHelpers._expand_globs`` rows: (paths, check_predicate).
def _is_passthrough(r: list[str]) -> bool:
    return r == ["src/python_setup_lint"]


def _is_py_glob(r: list[str]) -> bool:
    return bool(r) and all(f.endswith(".py") for f in r)


def _is_empty(r: list[str]) -> bool:
    return r == []


EXPAND_GLOBS_CASES: list[pytest.Param] = [
    pytest.param(["src/python_setup_lint"], _is_passthrough, id="passthrough"),
    pytest.param(["src/**/*.py"], _is_py_glob, id="expands_glob"),
    pytest.param(["*.nonexistent_ext_xyz"], _is_empty, id="empty_match"),
]


# ``TestStrategyBuildCommand`` stubtest+verifytypes rows.
STRATEGY_TOKENS_CASES: list[pytest.Param] = [
    pytest.param("mypy.stubtest", "python_setup_lint",
                 ["python_setup_lint", "--concise", "--ignore-missing-stub"], id="stubtest"),
    pytest.param("pyright verify types", "python_setup_lint",
                 ["python_setup_lint", "--ignoreexternal", "--outputjson"], id="verifytypes"),
]


# ``TestRunLintOrchestration.test_package_name_governs_stubtest_verifytypes`` rows.
PACKAGE_NAME_STUBTEST_CASES: list[pytest.Param] = [
    pytest.param(None, False, -2, id="package_name_none_skips"),  # skips stubtest + verifytypes (9 dispatched)
    pytest.param("python_setup_lint", True, 0, id="package_name_set_runs"),  # set → 11 dispatched
]


# ``TestMainCLI.test_main_exit_codes`` rows: (args, want_code_zero).
MAIN_EXIT_CODE_CASES: list[pytest.Param] = [
    pytest.param(["--help"], True, id="help_exits_zero"),
    pytest.param(["--nonexistent-flag"], False, id="unknown_flag_exits_nonzero"),
]


# ``TestRunLintIntegration.test_run_lint_baseline_capture_with_ruff`` rows.
RUFF_BASELINE_FIX_CASES: list[pytest.Param] = [
    pytest.param(False, "no issues", id="ruff_present_in_baseline"),
    pytest.param(True, None, id="run_lint_fix"),
]


# ExtraToolsConfigError R4 reason+match-kind dispatch helper.
def assert_r4_reason(err, pyproject: Path, reason_want: str, want_kind: str) -> None:
    """Assert ``ExtraToolsConfigError.location`` matches *pyproject* + reason by kind."""
    assert err.location == str(pyproject), (
        f"location mismatch: got {err.location!r}, want {str(pyproject)!r}"
    )
    if want_kind == "exact":
        assert err.reason == reason_want, (
            f"reason mismatch: got {err.reason!r}, want {reason_want!r}"
        )
    else:  # starts_with
        assert err.reason.startswith(reason_want), (
            f"reason mismatch: got {err.reason!r}, want prefix {reason_want!r}"
        )
