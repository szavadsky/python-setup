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
from .baseline import _capture_baseline as _capture_baseline
from .baseline import _compare_sorted as _compare_sorted
from .baseline import _diff_baseline as _diff_baseline
from .cli import _CONFIG_KEY_ALIASES as _CONFIG_KEY_ALIASES
from .cli import _SUPPORTED_CONFIG_KEYS as _SUPPORTED_CONFIG_KEYS
from .cli import main as main
from .cli import run_lint as run_lint
from .cmd_build import _build_command as _build_command
from .cmd_build import _build_statistics_flags as _build_statistics_flags
from .cmd_build import _config_flag_for as _config_flag_for
from .cmd_build import _expand_globs as _expand_globs
from .cmd_build import _find_py_files as _find_py_files
from .dispatch import LINT_TOOLS as LINT_TOOLS
from .dispatch import STRATEGIES as STRATEGIES
from .dispatch import TOOLS as TOOLS
from .dispatch import TOOLS_BY_NAME as TOOLS_BY_NAME
from .dispatch import GenericLintTool as GenericLintTool
from .dispatch import LintTool as LintTool
from .dispatch import _DetectSecretsLintTool as _DetectSecretsLintTool
from .dispatch import _PylintLintTool as _PylintLintTool
from .dispatch import _strategy_for as _strategy_for
from .dispatch import _StubtestLintTool as _StubtestLintTool
from .dispatch import _VerifyTypesLintTool as _VerifyTypesLintTool
from .dispatch import register_lint_tool as register_lint_tool
from .extra_tools import _EXTRA_TOOL_FIELDS as _EXTRA_TOOL_FIELDS
from .extra_tools import _EXTRA_TOOL_REQUIRED as _EXTRA_TOOL_REQUIRED
from .extra_tools import _EXTRA_TOOLS_CACHE as _EXTRA_TOOLS_CACHE
from .extra_tools import _EXTRA_TOOLS_REGISTERED_PATHS as _EXTRA_TOOLS_REGISTERED_PATHS
from .extra_tools import _REGEX_CACHE as _REGEX_CACHE
from .extra_tools import ExtraToolsConfigError as ExtraToolsConfigError
from .extra_tools import _compile_regex_count as _compile_regex_count
from .extra_tools import _extra_tool_parser as _extra_tool_parser
from .extra_tools import _ExtraToolRegistration as _ExtraToolRegistration
from .extra_tools import _load_extra_tools as _load_extra_tools
from .extra_tools import _parse_raw_lines as _parse_raw_lines
from .extra_tools import _parse_regex_count as _parse_regex_count
from .extra_tools import _register_extra_tools as _register_extra_tools
from .extra_tools import _reset_extra_tools_cache as _reset_extra_tools_cache
from .extra_tools import _validate_extra as _validate_extra
from .output import _aggregate_statistics as _aggregate_statistics
from .output import _print_result as _print_result
from .output import _print_statistics_grouped as _print_statistics_grouped
from .output import _print_statistics_table as _print_statistics_table
from .output import _run_cmd as _run_cmd
from .output import _sort_counts as _sort_counts
from .parsers import (
    _BUILTIN_PARSE_STRATEGY_TO_PARSER as _BUILTIN_PARSE_STRATEGY_TO_PARSER,
)
from .parsers import _RECORD_PARSERS as _RECORD_PARSERS
from .parsers import _STATISTICS_PARSERS as _STATISTICS_PARSERS
from .parsers import PARSE_STRATEGIES as PARSE_STRATEGIES
from .parsers import Record as Record
from .parsers import _compare_records_key as _compare_records_key
from .parsers import _parse_detect_secrets_json as _parse_detect_secrets_json
from .parsers import _parse_mypy_records as _parse_mypy_records
from .parsers import _parse_mypy_stderr as _parse_mypy_stderr
from .parsers import _parse_pylint_json2 as _parse_pylint_json2
from .parsers import _parse_pylint_records as _parse_pylint_records
from .parsers import _parse_pyright_outputjson as _parse_pyright_outputjson
from .parsers import _parse_pyright_records as _parse_pyright_records
from .parsers import _parse_pyright_verify_types as _parse_pyright_verify_types
from .parsers import _parse_ruff_records as _parse_ruff_records
from .parsers import _parse_ruff_statistics as _parse_ruff_statistics
from .parsers import _parse_rumdl_records as _parse_rumdl_records
from .parsers import _parse_rumdl_statistics as _parse_rumdl_statistics
from .parsers import _parse_stubtest_stderr as _parse_stubtest_stderr
from .parsers import _parse_tach_json as _parse_tach_json
from .parsers import _parse_ty_concise as _parse_ty_concise
from .parsers import _parse_ty_records as _parse_ty_records
from .parsers import _parse_yamllint_parsable as _parse_yamllint_parsable
from .parsers import _parse_yamllint_records as _parse_yamllint_records
from .parsers import _records_unchanged as _records_unchanged
from .types import LintResult as LintResult
from .types import RunnerConfig as RunnerConfig
from .types import ToolSpec as ToolSpec
from .types import ViolationCount as ViolationCount

__all__ = [
    "LINT_TOOLS",
    "PARSE_STRATEGIES",
    "STRATEGIES",
    "TOOLS",
    "TOOLS_BY_NAME",
    "ExtraToolsConfigError",
    "GenericLintTool",
    "LintResult",
    "LintTool",
    "RunnerConfig",
    "ToolSpec",
    "ViolationCount",
    "main",
    "register_lint_tool",
    "run_lint",
]
