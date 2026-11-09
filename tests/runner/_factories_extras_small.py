"""Small parametrize tables for python-setup runner tests.

Split from ``_factories_extras.py`` to keep each factory module under 500 lines (pylint C0302).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from python_setup_lint.runner.types import ViolationCount

if TYPE_CHECKING:
    from _pytest.mark.structures import ParameterSet

# ── Small parametrize tables ──────────────────────────────────────

# Print result format rows.
PRINT_FORMAT_CASES: list[ParameterSet] = [
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

# ``TestRunCmd`` rows.
RUN_CMD_CASES: list[ParameterSet] = [
    pytest.param(["echo", "hello"], "echo", lambda c: c == 0, "hello\n", id="success"),
    pytest.param(["false"], "false", lambda c: c != 0, None, id="failure"),
]

# ``TestPathHelpers._find_py_files`` boundary rows.
FIND_PY_FILES_BOUNDARY_CASES: list[ParameterSet] = [
    pytest.param(["nonexistent_dir_xyz"], [], id="nonexistent_dir"),
    pytest.param(
        ["src/python_setup_lint/runner/types.py"],
        ["src/python_setup_lint/runner/types.py"],
        id="single_file",
    ),
]


# ``TestPathHelpers._expand_globs`` rows.
def _is_passthrough(r: list[str]) -> bool:
    return r == ["src/python_setup_lint"]


def _is_py_glob(r: list[str]) -> bool:
    return bool(r) and all(f.endswith(".py") for f in r)


def _is_empty(r: list[str]) -> bool:
    return r == []


EXPAND_GLOBS_CASES: list[ParameterSet] = [
    pytest.param(["src/python_setup_lint"], _is_passthrough, id="passthrough"),
    pytest.param(["src/**/*.py"], _is_py_glob, id="expands_glob"),
    pytest.param(["*.nonexistent_ext_xyz"], _is_empty, id="empty_match"),
]

# ``TestStrategyBuildCommand`` stubtest+verifytypes rows.
STRATEGY_TOKENS_CASES: list[ParameterSet] = [
    pytest.param(
        "mypy.stubtest",
        "python_setup_lint",
        ["python_setup_lint", "--concise", "--ignore-missing-stub"],
        id="stubtest",
    ),
    pytest.param(
        "pyright verify types",
        "python_setup_lint",
        ["python_setup_lint", "--ignoreexternal", "--outputjson"],
        id="verifytypes",
    ),
]

# ``TestRunLintOrchestration.test_package_name_governs_stubtest_verifytypes`` rows.
PACKAGE_NAME_STUBTEST_CASES: list[ParameterSet] = [
    pytest.param(None, False, -2, id="package_name_none_skips"),
    pytest.param("python_setup_lint", True, 0, id="package_name_set_runs"),
]

# ``TestMainCLI.test_main_exit_codes`` rows.
MAIN_EXIT_CODE_CASES: list[ParameterSet] = [
    pytest.param(["--help"], True, id="help_exits_zero"),
    pytest.param(["--nonexistent-flag"], False, id="unknown_flag_exits_nonzero"),
]

# ``TestRunLintIntegration.test_run_lint_baseline_capture_with_ruff`` rows.
RUFF_BASELINE_FIX_CASES: list[ParameterSet] = [
    pytest.param(False, "no issues", id="ruff_present_in_baseline"),
    pytest.param(True, None, id="run_lint_fix"),
]
