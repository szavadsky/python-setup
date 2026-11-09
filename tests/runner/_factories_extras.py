"""Extra-tools, dispatch, and integration test data for python-setup runner tests.

Moved from ``_factories.py`` to keep each file under 500 lines (pylint C0302).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from _pytest.mark.structures import ParameterSet


from python_setup_lint.runner.types import (  # pylint: disable=wrong-import-position  # conditional import after module-level check
    ViolationCount,
)

from ._factories_baseline import (  # pylint: disable=wrong-import-position  # conditional import after module-level check
    _make_result,
)

# ── Extra-tools test data ──────────────────────────────────────────

BUILTIN_NAME = "ruff check"

VALID_EXTRA_BLOCK = (
    'name = "grep-noqa-scan"\n'
    'command = ["grep", "-rnE", "--exclude-dir=__pycache__", '
    '"--include=*.py", "noqa: "]\n'
    "supports_path = true\n"
    'default_paths = ["src/", "tests/"]\n'
    'parse_strategy = "regex_count"\n'
    'parse_regex = "^[^:]+:\\\\d+:.*# noqa: (\\\\S+)"\n'  # noqa: W9704  # string literal contains noqa pattern text, not a real suppression
)

EMPTY_LOADER_CASES: list[tuple[str, str | None]] = [
    ("no_pyproject", None),
    ("no_section", "[tool.python-setup-lint]\nsome = 1\n"),
    ("empty_array", "[tool.python-setup-lint]\nextra-tools = []\n"),
]


def extra_block(entries: str) -> str:
    """Wrap one-or-more ``[[tool.python-setup-lint.extra-tools]]`` body lines."""
    return f"[tool.python-setup-lint]\n[[tool.python-setup-lint.extra-tools]]\n{entries}"


# Combined R4 reason-match table.
R4_EXACT_REASON_CASES: list[ParameterSet] = [
    pytest.param(
        extra_block('name = "x"\ncommand = ["x"]\nbogus_field = 1\n'),
        "unknown field: ",
        "starts_with",
        id="unknown_field",
    ),
    pytest.param(
        extra_block('name = "x"\n'),
        "missing required field: command",
        "exact",
        id="missing_required_field",
    ),
    pytest.param(
        extra_block('name = "x"\ncommand = ["x"]\nparse_strategy = "regex_count"\n'),
        "missing required field: parse_regex",
        "starts_with",
        id="regex_count_requires_parse_regex",
    ),
    pytest.param(
        extra_block('name = "x"\ncommand = ["x"]\nparse_strategy = "regex_count"\nparse_regex = "no_groups_here"\n'),
        "regex missing or != 1 capture group",
        "starts_with",
        id="regex_count_bad_group_count",
    ),
    pytest.param(
        extra_block('name = "dup"\ncommand = ["x"]\n')
        + "[[tool.python-setup-lint.extra-tools]]\n"
        + 'name = "dup"\ncommand = ["x"]\n',
        "duplicate within file: dup",
        "exact",
        id="duplicate_within_file",
    ),
    pytest.param(
        extra_block(f'name = "{BUILTIN_NAME}"\ncommand = ["x"]\n'),
        f"duplicate vs built-in: {BUILTIN_NAME}",
        "exact",
        id="duplicate_vs_builtin",
    ),
    pytest.param(
        extra_block('name = 123\ncommand = ["x"]\n'),
        "wrong type: name must be non-empty str",
        "exact",
        id="name_non_str",
    ),
    pytest.param(
        extra_block('name = "   "\ncommand = ["x"]\n'),
        "wrong type: name must be non-empty str",
        "exact",
        id="name_whitespace",
    ),
    pytest.param(
        extra_block('name = "x"\ncommand = "ruff"\n'),
        "wrong type: command must be list[str]",
        "exact",
        id="command_scalar",
    ),
    pytest.param(
        extra_block('name = "x"\ncommand = ["x", 1]\n'),
        "wrong type: command must be list[str]",
        "exact",
        id="command_non_str_parts",
    ),
]

# Wrong-type flag fields (boolean / list / scalar shapes).
R4_FLAG_WRONG_TYPE_CASES: list[ParameterSet] = [
    pytest.param(
        'supports_fix = "yes"\n',
        "wrong type: supports_fix must be bool",
        id="supports_fix",
    ),
    pytest.param(
        "supports_path = 1\n",
        "wrong type: supports_path must be bool",
        id="supports_path",
    ),
    pytest.param(
        'supports_exclude = "no"\n',
        "wrong type: supports_exclude must be bool",
        id="supports_exclude",
    ),
    pytest.param(
        'default_paths = "src/"\n',
        "wrong type: default_paths must be list[str]",
        id="default_paths_scalar",
    ),
    pytest.param(
        'default_paths = ["x", 1]\n',
        "wrong type: default_paths must be list[str]",
        id="default_paths_non_str_parts",
    ),
    pytest.param(
        "config_flag = 12\n",
        "wrong type: config_flag must be str | list[str]",
        id="config_flag_int",
    ),
    pytest.param(
        'config_flag = ["--x", 1]\n',
        "wrong type: config_flag must be str | list[str]",
        id="config_flag_non_str_parts",
    ),
    pytest.param(
        "parse_strategy = 7\n",
        "wrong type: parse_strategy must be str",
        id="parse_strategy_int",
    ),
    pytest.param(
        'parse_strategy = "bogus"\n',
        "bad enum: parse_strategy 'bogus'",
        id="parse_strategy_bad_enum",
    ),
]

REGEX_BAD_GROUP_CASES: list[str] = [
    "no_groups_here",  # zero capture groups
    "(a)(b)",  # two capture groups
    "(unclosed",  # unparseable regex
]

# Downstream-integration test blocks + cases (T11 extra-tools pipeline).
REGEX_BLOCK = (
    'name = "regextool"\n'
    'command = ["fake-regex-cli"]\n'
    "supports_path = true\n"
    "default_paths = []\n"
    'parse_strategy = "regex_count"\n'
    'parse_regex = "^(?P<rule>[A-Z]+[0-9]+): .*"\n'
)

NONE_BLOCK = (
    'name = "nonestattool"\ncommand = ["fake-none-cli"]\nsupports_path = true\ndefault_paths = []\nparse_strategy = "none"\n'
)

DOWNSTREAM_CASES: list[ParameterSet] = [
    pytest.param(
        REGEX_BLOCK,
        "regextool",
        ["fake-regex-cli"],
        "RC1: bad line\nRC2: worse line\nRC1: another",
        [("regextool", "RC1", 2), ("regextool", "RC2", 1)],
        id="regex_count_extra_emits_rule_counts",
    ),
    pytest.param(
        NONE_BLOCK,
        "nonestattool",
        ["fake-none-cli"],
        "noise\nthat has no rule ids\nRC1: ignored too\n",
        [],
        id="parse_strategy_none_skips_aggregate",
    ),
]

# Observability test block.
EXTRA_OBSERV_BLOCK = REGEX_BLOCK
EXTRA_OBSERV_STDOUT = "RC1: bad line\nRC2: worse line\nRC1: another"
EXTRA_OBSERV_NAME = "regextool"

# ── T8 fail-fast malformation table ────────────────────────────────

MALFORMATION_CASES: list[ParameterSet] = [
    pytest.param(
        '[tool.python-setup-lint]\nextra-tools = "not-a-list"\n',
        "wrong type: extra-tools must be a list of tables",
        True,
        id="malformed_extra_tools_section",
    ),
    pytest.param(
        '[tool.python-setup-lint]\n[[tool.python-setup-lint.extra-tools]]\nname = "no-command"\n',
        "missing required field: command",
        True,
        id="missing_required_key",
    ),
    pytest.param(
        '[tool.python-setup-lint]\n[[tool.python-setup-lint.extra-tools]]\nname = "my-tool"\ncommand = ["tool"]\nfoo = "bar"\n',
        "unknown field: ['foo']; allowed:",
        False,
        id="unknown_field",
    ),
    pytest.param(
        "[tool.python-setup-lint]\n[[tool.python-setup-lint.extra-tools]]\n"
        'name = "my-tool"\ncommand = ["tool"]\nparse_strategy = "invalid-strat"\n',
        "bad enum: parse_strategy",
        False,
        id="bad_parse_strategy_enum",
    ),
    pytest.param(
        "[[[\ninvalid toml\n",
        "pyproject unreadable:",
        False,
        id="unreadable_pyproject_toml",
    ),
]

# ── Grouped statistics output table ────────────────────────────────

GROUPED_OUTPUT_CASES: list[ParameterSet] = [
    pytest.param(
        "tool",
        [
            ViolationCount("tool_a", "A001", 10),
            ViolationCount("tool_a", "B001", 5),
            ViolationCount("tool_b", "A001", 3),
        ],
        "VIOLATION STATISTICS (grouped by tool)",
        ["[tool_a]", "[tool_b]", "Subtotal", "Total"],
        ["15", "3"],
        id="group_tool_has_subtotals",
    ),
    pytest.param(
        "rule",
        [
            ViolationCount("tool_a", "Z001", 3),
            ViolationCount("tool_b", "A001", 7),
            ViolationCount("tool_b", "A001", 5),
        ],
        "VIOLATION STATISTICS (grouped by rule)",
        ["[A001]", "[Z001]", "Subtotal"],
        ["12", "3"],
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
        "tool",
        [],
        "VIOLATION STATISTICS (grouped by tool)",
        [],
        ["No violations found"],
        id="group_empty_prints_no_violations",
    ),
]

# Clean extras-pyproject body for the T8 positive-path integration test.
CLEAN_EXTRAS_PYPROJECT_BODY = (
    '[project]\nname = "t8-clean"\nversion = "0.0.1"\n\n'
    "[tool.python-setup-lint]\n[[tool.python-setup-lint.extra-tools]]\n"
    'name = "t8-grep-noqa"\ncommand = ["grep", "-rnE", "noqa: "]\n'
    'supports_path = true\ndefault_paths = ["src/"]\nparse_strategy = "raw_lines"\n'
)

# ── FakeRunCmd dispatch contract table ─────────────────────────────

DISPATCH_CASES: list[ParameterSet] = [
    pytest.param(
        "dict",
        {"ruff check": _make_result("ruff check", exit_code=1, stdout="issues")},
        [(["ruff", "check", "src/"], "ruff check")],
        [1],
        ["ruff check"],
        id="dict_known_label_returns_canned",
    ),
    pytest.param(
        "dict",
        {"ruff check": _make_result("ruff check")},
        [(["python", "-m", "mypy.stubtest"], "mypy.stubtest")],
        [0],
        ["mypy.stubtest"],
        id="dict_unknown_label_returns_zero_exit_empty",
    ),
    pytest.param(
        "dict",
        {},
        [(["ruff", "check", "."], "ruff check")],
        [0],
        ["ruff check"],
        id="dict_empty_returns_zero_exit_empty",
    ),
    pytest.param(
        "list",
        [_make_result("ruff check", exit_code=0), _make_result("mypy", exit_code=1)],
        [(["ruff", "check", "."], "ruff check"), (["mypy", "."], "mypy")],
        [0, 1],
        ["ruff check", "mypy"],
        id="list_returns_results_in_order",
    ),
    pytest.param(
        "list",
        [],
        [(["ruff", "check", "."], "ruff check")],
        [0],
        ["ruff check"],
        id="list_empty_returns_zero_exit_empty",
    ),
]

# Cmd + label capture table.
CALLS_CAPTURED_CASES: list[ParameterSet] = [
    pytest.param(
        {"ruff check": _make_result("ruff check")},
        [(["ruff", "check", "src/", "--fix"], "ruff check")],
        [{"label": "ruff check", "cmd": ["ruff", "check", "src/", "--fix"]}],
        id="dict_single",
    ),
    pytest.param(
        {
            "ruff check": _make_result("ruff check"),
            "mypy": _make_result("mypy", exit_code=1),
        },
        [(["ruff", "check", "."], "ruff check"), (["mypy", "."], "mypy")],
        [
            {"label": "ruff check", "cmd": ["ruff", "check", "."]},
            {"label": "mypy", "cmd": ["mypy", "."]},
        ],
        id="dict_multiple",
    ),
    pytest.param(
        [_make_result("ruff check")],
        [(["ruff", "check", "--fix"], "ruff check")],
        [{"label": "ruff check", "cmd": ["ruff", "check", "--fix"]}],
        id="list_single",
    ),
]

# Smoke-integration invariant table.


def _expected_dispatched_tool_count(*, skipped: frozenset[str] = frozenset()) -> int:
    """Count built-in tools minus *skipped*, read from the public registry."""
    from ._factories import runner_registry_constant

    return len(runner_registry_constant("EXPECTED_TOOL_NAMES") - skipped)


RUN_LINT_FAKE_INVARIANT_CASES: list[ParameterSet] = [
    pytest.param(
        {"path": "src/python_setup_lint/runner.py"},
        lambda f: len(f.calls) == _expected_dispatched_tool_count() and all(len(c.cmd) > 0 and c.label for c in f.calls),
        id="all_14_tools_dispatched",
    ),
    pytest.param(
        {"path": "src/python_setup_lint/runner.py", "fix": True},
        lambda f: all(
            any("--fix" in c.cmd for c in f.calls if c.label == name) for name in ("ruff check", "rumdl check", "ty check")
        ),
        id="fix_flag_propagates_to_supports_fix_labels",
    ),
    pytest.param(
        {"path": "src/python_setup_lint/runner.py", "exclude": "tests/"},
        lambda f: all(
            ("--exclude" in c.cmd or "-e" in c.cmd)
            for c in f.calls
            if c.label in {"tach check", "ruff check", "rumdl check", "ty check"}
        ),
        id="exclude_flag_propagates_to_supports_exclude_labels",
    ),
    pytest.param(
        {"package_name": None, "path": "src/python_setup_lint/runner.py"},
        lambda f: (
            len(f.calls) == _expected_dispatched_tool_count(skipped=frozenset({"mypy.stubtest", "pyright verify types"}))
            and "mypy.stubtest" not in {c.label for c in f.calls}
            and "pyright verify types" not in {c.label for c in f.calls}
        ),
        id="package_name_none_skips_stubtest_verifytypes",
    ),
]
