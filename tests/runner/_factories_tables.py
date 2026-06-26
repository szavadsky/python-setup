"""Parametrize tables for python-setup runner tests.

Moved from ``_factories.py`` to keep each file under 500 lines (pylint C0302).
"""

from __future__ import annotations

import pytest

# ── Parametrise tables ────────────────────────────────────────────

# ``_build_command`` rows — one row per (tool spec, kwargs, expected cmd).
BUILD_COMMAND_CASES: list[pytest.Param] = [  # type: ignore[name-defined]
    pytest.param(
        {
            "name": "test",
            "command": ["tool", "check"],
            "supports_path": True,
            "default_paths": ["src/"],
        },
        {},
        ["tool", "check", "src/"],
        id="default_no_flags",
    ),
    pytest.param(
        {"name": "test", "command": ["tool", "check"]},
        {},
        ["tool", "check"],
        id="no_default_paths",
    ),
    pytest.param(
        {"name": "test", "command": ["tool"], "supports_path": False},
        {"path": "src/"},
        ["tool"],
        id="path_no_support",
    ),
    pytest.param(
        {"name": "test", "command": ["tool"], "supports_path": True},
        {"path": "src/python_setup_lint"},
        ["tool", "src/python_setup_lint"],
        id="path_with_support",
    ),
    pytest.param(
        {
            "name": "test",
            "command": ["tool"],
            "supports_path": True,
            "default_paths": ["."],
        },
        {"path": "src/"},
        ["tool", "src/"],
        id="path_overrides_default",
    ),
    pytest.param(
        {"name": "test", "command": ["tool"], "supports_fix": False},
        {"fix": True},
        ["tool"],
        id="fix_no_support",
    ),
    pytest.param(
        {
            "name": "ruff check",
            "command": ["ruff", "check"],
            "supports_fix": True,
            "fix_flags": ("--fix", "--exit-non-zero-on-fix"),
        },
        {"fix": True},
        ["ruff", "check", "--fix", "--exit-non-zero-on-fix"],
        id="fix_ruff",
    ),
    pytest.param(
        {
            "name": "rumdl check",
            "command": ["rumdl", "check"],
            "supports_fix": True,
            "fix_flags": ("--fix",),
        },
        {"fix": True},
        ["rumdl", "check", "--fix"],
        id="fix_rumdl",
    ),
    pytest.param(
        {
            "name": "ty check",
            "command": ["ty", "check"],
            "supports_fix": True,
            "fix_flags": ("--fix",),
        },
        {"fix": True},
        ["ty", "check", "--fix"],
        id="fix_ty",
    ),
    pytest.param(
        {"name": "test", "command": ["tool"], "supports_exclude": False},
        {"exclude": "tests/"},
        ["tool"],
        id="exclude_no_support",
    ),
    pytest.param(
        {
            "name": "tach check",
            "command": ["tach", "check"],
            "supports_exclude": True,
            "exclude_flag": "-e",
        },
        {"exclude": "tests/"},
        ["tach", "check", "-e", "tests/"],
        id="exclude_tach",
    ),
    pytest.param(
        {"name": "ruff check", "command": ["ruff", "check"], "supports_exclude": True},
        {"exclude": "tests/"},
        ["ruff", "check", "--exclude", "tests/"],
        id="exclude_other",
    ),
    pytest.param(
        {
            "name": "ruff check",
            "command": ["ruff", "check"],
            "supports_path": True,
            "supports_exclude": True,
        },
        {"path": "src/", "exclude": "tests/"},
        ["ruff", "check", "src/", "--exclude", "tests/"],
        id="exclude_with_path",
    ),
]

# ``_build_statistics_flags`` rows — one row per (tool name, expected flag list).
STATISTICS_FLAG_CASES: list[pytest.Param] = [  # type: ignore[name-defined]
    pytest.param("ruff check", ["--statistics"], id="ruff_native"),
    pytest.param("rumdl check", ["--statistics"], id="rumdl_native"),
    pytest.param("pylint", ["--output-format=json2"], id="pylint_json2"),
    pytest.param("pyright check", ["--outputjson"], id="pyright_outputjson"),
    pytest.param("mypy", ["--no-error-summary"], id="mypy_no_error_summary"),
    pytest.param("ty check", ["--output-format", "concise"], id="ty_concise"),
    pytest.param("tach check", ["--output", "json"], id="tach_json"),
    pytest.param("yamllint", ["-f", "parsable"], id="yamllint_parsable"),
]

# ``main([...])`` flag-acceptance rows.
MAIN_ARGPARSE_CASES: list[pytest.Param] = [  # type: ignore[name-defined]
    pytest.param(["--path", "src/python_setup_lint/runner.py"], id="main_path"),
    pytest.param(["--fix", "--path", "src/python_setup_lint/runner.py"], id="main_fix"),
    pytest.param(
        ["--no-fail-fast", "--path", "src/python_setup_lint/runner.py"],
        id="main_no_fail_fast",
    ),
    pytest.param(
        ["--exclude", "tests/", "--path", "src/python_setup_lint/runner.py"],
        id="main_exclude",
    ),
    pytest.param(
        [
            "--package-name",
            "python_setup_lint",
            "--path",
            "src/python_setup_lint/runner.py",
        ],
        id="main_package_name",
    ),
    pytest.param(
        ["--tools", "ruff check,mypy", "--path", "src/python_setup_lint/runner.py"],
        id="main_tools",
    ),
    pytest.param(
        ["--default-py-dirs", "src,tests", "--path", "src/python_setup_lint/runner.py"],
        id="main_default_py_dirs",
    ),
    pytest.param([], id="main_no_args_backward_compat"),
]

# ``main([... --statistics ...])`` flag-acceptance rows for T7 group/sort.
MAIN_GROUP_SORT_CASES: list[pytest.Param] = [  # type: ignore[name-defined]
    pytest.param(
        [
            "--statistics",
            "--group",
            "tool",
            "--path",
            "src/python_setup_lint/runner.py",
        ],
        id="group_tool",
    ),
    pytest.param(
        [
            "--statistics",
            "--group",
            "rule",
            "--path",
            "src/python_setup_lint/runner.py",
        ],
        id="group_rule",
    ),
    pytest.param(
        ["--statistics", "--sort-by-rule", "--path", "src/python_setup_lint/runner.py"],
        id="sort_by_rule",
    ),
    pytest.param(
        [
            "--statistics",
            "--group",
            "rule",
            "--sort-by-rule",
            "--path",
            "src/python_setup_lint/runner.py",
        ],
        id="group_and_sort_by_rule",
    ),
]

# Per-parser statistics table.
ParserRow = tuple[str, str, str, list[tuple[str, int]]]
PARSER_STATISTICS_CASES: list[pytest.Param] = [  # type: ignore[name-defined]
    # ruff
    pytest.param(
        "ruff check",
        "Count\tCode\tDescription\n------\t----\t-----------\n3\tF401\tmodule imported but unused\n1\tE501\tline too long\n",
        "",
        [("F401", 3), ("E501", 1)],
        id="ruff_typical",
    ),
    pytest.param("ruff check", "", "", [], id="ruff_empty"),
    pytest.param("ruff check", "No violations found\n", "", [], id="ruff_no_header"),
    pytest.param(
        "ruff check",
        "Count\tCode\tDescription\n------\t----\t-----------\n2\tF401\tsomething\n2\tF401\tsomething else\n",
        "",
        [("F401", 4)],
        id="ruff_multiline_grouped",
    ),
    # rumdl (per-violation format — no --statistics flag)
    pytest.param(
        "rumdl check",
        "f.md:1:1: [MD041] First line in file should be a level 1 heading\nf.md:3:1: [MD012] Multiple consecutive blank lines\n",
        "",
        [("MD041", 1), ("MD012", 1)],
        id="rumdl_typical",
    ),
    pytest.param(
        "rumdl check",
        "f.md:1:1: [MD041] First line\nf.md:2:1: [MD041] Another\n",
        "",
        [("MD041", 2)],
        id="rumdl_multiple_same_rule",
    ),
    pytest.param("rumdl check", "", "", [], id="rumdl_empty"),
    pytest.param(
        "rumdl check",
        "Success: No issues found in 1 file (12ms)\n",
        "",
        [],
        id="rumdl_no_issues",
    ),
    # pylint json2
    pytest.param(
        "pylint",
        '[{"symbol":"unused-import"},{"symbol":"unused-import"},{"symbol":"too-complex"}]',
        "",
        [("unused-import", 2), ("too-complex", 1)],
        id="pylint_typical",
    ),
    pytest.param("pylint", "[]", "", [], id="pylint_empty_array"),
    pytest.param("pylint", "not json", "", [], id="pylint_invalid_json"),
    pytest.param("pylint", '{"key":"val"}', "", [], id="pylint_non_list"),
    pytest.param(
        "pylint",
        '{"messages":[{"symbol":"unused-import"},{"symbol":"too-complex"}],"status":1}',
        "",
        [("unused-import", 1), ("too-complex", 1)],
        id="pylint_json2_dict_shape",
    ),
    pytest.param(
        "pylint", '{"messages":[],"status":0}', "", [], id="pylint_json2_dict_empty"
    ),
    pytest.param(
        "pylint",
        '{"messages":[{"symbol":"unused-import"},{"symbol":"unused-import"}],"status":1}',
        "",
        [("unused-import", 2)],
        id="pylint_json2_dict_duplicates",
    ),
    # pyright outputjson
    pytest.param(
        "pyright check",
        '{"generalDiagnostics":[{"rule":"reportGeneralTypeIssues"},{"rule":"reportGeneralTypeIssues"},{"rule":"reportOptionalMemberAccess"}]}',
        "",
        [("reportGeneralTypeIssues", 2), ("reportOptionalMemberAccess", 1)],
        id="pyright_typical",
    ),
    pytest.param(
        "pyright check",
        '{"generalDiagnostics":[]}',
        "",
        [],
        id="pyright_empty_diagnostics",
    ),
    pytest.param("pyright check", '{"summary":{}}', "", [], id="pyright_missing_key"),
    pytest.param("pyright check", "bad", "", [], id="pyright_invalid_json"),
    # pyright verify types
    pytest.param(
        "pyright verify types",
        '{"typeCompleteness":{"symbols":[{"symbolName":"Foo","completeness":0.5},{"symbolName":"Bar","completeness":1.0}]}}',
        "",
        [("verifytypes:incomplete", 1)],
        id="verifytypes_with_incomplete",
    ),
    pytest.param(
        "pyright verify types",
        '{"typeCompleteness":{"symbols":[{"symbolName":"Foo","completeness":1.0}]}}',
        "",
        [],
        id="verifytypes_all_complete",
    ),
    pytest.param("pyright verify types", "bad", "", [], id="verifytypes_invalid_json"),
    pytest.param(
        "pyright verify types", "{}", "", [], id="verifytypes_missing_type_completeness"
    ),
    # mypy stderr
    pytest.param(
        "mypy",
        "",
        "file.py:1: error: Unused import [no-unused-import]\nfile.py:2: error: Not callable [operator]\n",
        [("no-unused-import", 1), ("operator", 1)],
        id="mypy_typical",
    ),
    pytest.param("mypy", "", "", [], id="mypy_empty"),
    # ty concise
    pytest.param(
        "ty check",
        "file.py:1:1: X001 some message\nfile.py:2:2: X002 another\n",
        "",
        [("X001", 1), ("X002", 1)],
        id="ty_typical",
    ),
    pytest.param("ty check", "", "", [], id="ty_empty"),
    # tach json
    pytest.param(
        "tach check",
        '{"errors":[{"message":"bad import"}]}',
        "",
        [("tach:error", 1)],
        id="tach_with_errors",
    ),
    pytest.param("tach check", '{"errors":[]}', "", [], id="tach_no_errors"),
    pytest.param("tach check", "bad", "", [], id="tach_invalid_json"),
    # yamllint parsable
    pytest.param(
        "yamllint",
        "f.yaml:1:1:trailing-spaces: message 1\nf.yaml:2:2:trailing-spaces: message 2\n",
        "",
        [("trailing-spaces", 2)],
        id="yamllint_typical",
    ),
    pytest.param("yamllint", "", "", [], id="yamllint_empty"),
    # stubtest stderr
    pytest.param(
        "mypy.stubtest",
        "",
        "error: X001 first error\nerror: X001 second error\nerror: X002 third error\n",
        [("X001", 2), ("X002", 1)],
        id="stubtest_typical",
    ),
    pytest.param(
        "mypy.stubtest", "info: something\n", "", [], id="stubtest_no_error_prefix"
    ),
    # detect-secrets json
    pytest.param(
        "detect-secrets",
        '{"results":{"file.py":[{"type":"Secret A"},{"type":"Secret A"},{"type":"Secret B"}]}}',
        "",
        [("Secret A", 2), ("Secret B", 1)],
        id="detect_secrets_typical",
    ),
    pytest.param("detect-secrets", '{"results":{}}', "", [], id="detect_secrets_empty"),
    pytest.param("detect-secrets", "bad", "", [], id="detect_secrets_invalid_json"),
]
