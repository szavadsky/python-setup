"""Python CLI runner for the python-setup lint pipeline.

Replaces ``scripts/lint.sh``.  Runs all 13 lint steps sequentially with
optional path scoping, fix mode, baseline diffing, flexible failure
handling, statistics aggregation, declarative extra-tools (T11 v1), and
autofix (T4).  See ``AGENTS.md`` for the full architecture.

Public surface
--------------
- ``main`` / ``run_lint`` — CLI entry point and programmatic API.
- ``LintResult``, ``RunnerConfig``, ``ToolSpec``, ``ViolationCount`` — core types.
- ``LINT_TOOLS``, ``STRATEGIES``, ``TOOLS``, ``TOOLS_BY_NAME`` — tool registries.
- ``GenericLintTool``, ``LintTool`` — tool strategy base classes.
- ``register_lint_tool`` — register a custom tool.
- ``ExtraToolsConfigError`` — extra-tools configuration error.
- ``Record``, ``PARSE_STRATEGIES`` — parser types.
- ``peek_fallback_tools`` — baseline fallback inspection.
"""

from __future__ import annotations

from .baseline import peek_fallback_tools
from .cli import main, run_lint
from .dispatch import (
    LINT_TOOLS,
    STRATEGIES,
    TOOLS,
    TOOLS_BY_NAME,
    GenericLintTool,
    LintTool,
    register_lint_tool,
)
from .extra_tools import ExtraToolsConfigError
from .parsers import PARSE_STRATEGIES, Record
from .types import LintResult, RunnerConfig, ToolSpec, ViolationCount

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
    "Record",
    "RunnerConfig",
    "ToolSpec",
    "ViolationCount",
    "main",
    "peek_fallback_tools",
    "register_lint_tool",
    "run_lint",
]
