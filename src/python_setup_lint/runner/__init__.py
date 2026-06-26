"""Python CLI runner for the python-setup lint pipeline.

Replaces ``scripts/lint.sh``.  Runs all 11 lint steps sequentially with
optional path scoping, fix mode, baseline diffing, flexible failure
handling, statistics aggregation, declarative extra-tools (T11 v1), and
T8 fail-fast validation.

The runner is split across cohesive submodules (each ≤500 LOC) — see
``runner/`` directory layout.  This ``__init__`` re-exports the public
surface AND the private helpers tests reach through the
``python_setup_lint.runner`` import path, so consumer code
(``consultant_mcp._lint_scripts``) and the existing test suite resolve
unchanged after the T9 split.

CLI
---

::

    uv run lint                              # all 11 steps, fail-fast
    uv run lint --path src/python_setup_lint      # scope to a single dir
    uv run lint --fix                         # apply autofixes
    uv run lint --baseline lint.baseline      # diff vs stored baseline
    uv run lint --no-fail-fast                # run all, report aggregate
    uv run lint --exclude tests/              # exclude a path
    uv run lint --statistics                  # per-rule violation counts
    uv run lint --statistics --format json    # machine-readable
"""

from __future__ import annotations

# ── Public surface (re-exported for consumers + tests) ────────────
# All names re-exported via redundant ``as`` aliases so ruff F401
# (imported-but-unused) treats them as intentional re-exports.  Both
# public symbols and the ``_``-prefixed helpers tests reach through the
# ``python_setup_lint.runner`` import path are listed here so the
# pre-split single-module surface resolves unchanged after the T9 split.
from .baseline import _capture_baseline
from .baseline import _compare_sorted
from .baseline import _diff_baseline
from .baseline import peek_fallback_tools
from ._autofix import _AUTOFIX_ENV_VAR
from ._autofix import _E999_RULE
from ._autofix import _apply_autofix_conflict_aware
from ._autofix import _autofix_target_paths
from ._autofix import _git_changed_files
from ._autofix import _ruff_parseability_errors
from ._config import _CONFIG_KEY_ALIASES
from ._config import _SUPPORTED_CONFIG_KEYS
from ._config import _default_config_paths
from ._config import _infer_package_name
from ._config import _print_config_status
from .cli import main
from .cli import run_lint
from .cmd_build import _build_command
from .cmd_build import _build_statistics_flags
from .cmd_build import _compose_pyright_config
from .cmd_build import _compose_ruff_config
from .cmd_build import _config_flag_for
from .cmd_build import _expand_globs
from .cmd_build import _find_py_files
from .dispatch import LINT_TOOLS
from .dispatch import STRATEGIES
from .dispatch import TOOLS
from .dispatch import TOOLS_BY_NAME
from .dispatch import GenericLintTool
from .dispatch import LintTool
from .dispatch import _DetectSecretsLintTool
from .dispatch import _PylintLintTool
from .dispatch import _strategy_for
from .dispatch import _StubtestLintTool
from .dispatch import _VerifyTypesLintTool
from .dispatch import register_lint_tool
from .extra_tools import _EXTRA_TOOL_FIELDS
from .extra_tools import _EXTRA_TOOL_REQUIRED
from .extra_tools import _EXTRA_TOOLS_CACHE
from .extra_tools import _EXTRA_TOOLS_REGISTERED_PATHS
from .extra_tools import _REGEX_CACHE
from .extra_tools import ExtraToolsConfigError
from .extra_tools import _compile_regex_count
from .extra_tools import _extra_tool_parser
from .extra_tools import _ExtraToolRegistration
from .extra_tools import _load_extra_tools
from .extra_tools import _parse_raw_lines
from .extra_tools import _parse_regex_count
from .extra_tools import _register_extra_tools
from .extra_tools import _reset_extra_tools_cache
from .extra_tools import _validate_extra
from .output import _aggregate_statistics
from .output import _print_result
from .output import _print_statistics_grouped
from .output import _print_statistics_table
from .output import _run_cmd
from .output import _sort_counts
from .parsers import _BUILTIN_PARSE_STRATEGY_TO_PARSER
from .parsers import _RECORD_PARSERS
from .parsers import _STATISTICS_PARSERS
from .parsers import PARSE_STRATEGIES
from .parsers import Record
from .parsers import _compare_records_key
from .parsers import _parse_detect_secrets_json
from .parsers import _parse_mypy_records
from .parsers import _parse_mypy_stderr
from .parsers import _parse_pylint_json2
from .parsers import _parse_pylint_records
from .parsers import _parse_pyright_outputjson
from .parsers import _parse_pyright_records
from .parsers import _parse_pyright_verify_types
from .parsers import _parse_ruff_records
from .parsers import _parse_ruff_statistics
from .parsers import _parse_rumdl_records
from .parsers import _parse_rumdl_statistics
from .parsers import _parse_stubtest_stderr
from .parsers import _parse_tach_json
from .parsers import _parse_ty_concise
from .parsers import _parse_ty_records
from .parsers import _parse_yamllint_parsable
from .parsers import _parse_yamllint_records
from .parsers import _records_unchanged
from .types import LintResult
from .types import RunnerConfig
from .types import ToolSpec
from .types import ViolationCount

__all__ = [
    "_AUTOFIX_ENV_VAR",
    "_BUILTIN_PARSE_STRATEGY_TO_PARSER",
    "_CONFIG_KEY_ALIASES",
    "_E999_RULE",
    "_compile_regex_count",
    "_EXTRA_TOOL_FIELDS",
    "_EXTRA_TOOL_REQUIRED",
    "_EXTRA_TOOLS_CACHE",
    "_EXTRA_TOOLS_REGISTERED_PATHS",
    "_ExtraToolRegistration",
    "_RECORD_PARSERS",
    "_REGEX_CACHE",
    "_STATISTICS_PARSERS",
    "_SUPPORTED_CONFIG_KEYS",
    "_aggregate_statistics",
    "_apply_autofix_conflict_aware",
    "_autofix_target_paths",
    "_build_command",
    "_build_statistics_flags",
    "_capture_baseline",
    "_compare_records_key",
    "_compare_sorted",
    "_compose_pyright_config",
    "_compose_ruff_config",
    "_config_flag_for",
    "_default_config_paths",
    "_DetectSecretsLintTool",
    "_diff_baseline",
    "_expand_globs",
    "_extra_tool_parser",
    "_find_py_files",
    "_git_changed_files",
    "_infer_package_name",
    "_load_extra_tools",
    "_parse_detect_secrets_json",
    "_parse_mypy_records",
    "_parse_mypy_stderr",
    "_parse_pylint_json2",
    "_parse_pylint_records",
    "_parse_pyright_outputjson",
    "_parse_pyright_records",
    "_parse_pyright_verify_types",
    "_parse_raw_lines",
    "_parse_regex_count",
    "_parse_ruff_records",
    "_parse_ruff_statistics",
    "_parse_rumdl_records",
    "_parse_rumdl_statistics",
    "_parse_stubtest_stderr",
    "_parse_tach_json",
    "_parse_ty_concise",
    "_parse_ty_records",
    "_parse_yamllint_parsable",
    "_parse_yamllint_records",
    "_print_config_status",
    "_print_result",
    "_print_statistics_grouped",
    "_print_statistics_table",
    "_PylintLintTool",
    "_records_unchanged",
    "_register_extra_tools",
    "_reset_extra_tools_cache",
    "_ruff_parseability_errors",
    "_run_cmd",
    "_sort_counts",
    "_strategy_for",
    "_StubtestLintTool",
    "_validate_extra",
    "_VerifyTypesLintTool",
    "LINT_TOOLS",
    "PARSE_STRATEGIES",
    "STRATEGIES",
    "TOOLS",
    "TOOLS_BY_NAME",
    "ExtraToolsConfigError",
    "GenericLintTool",
    "LintResult",
    "LintTool",
    "Record",
    "RunnerConfig",
    "ToolSpec",
    "ViolationCount",
    "main",
    "peek_fallback_tools",
    "register_lint_tool",
    "run_lint",
]
