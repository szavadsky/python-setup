"""Stub for :mod:`python_setup_lint.runner._tool_specs`.

Single-source built-in :class:`ToolSpec` registry, re-exported by
:mod:`python_setup_lint.runner.dispatch`.
"""

from .types import ToolSpec

TOOLS: list[ToolSpec]
"""All 14 tool specifications in execution order (built-ins)."""

TOOLS_BY_NAME: dict[str, ToolSpec]
"""Tool specs keyed by name for fast lookup (built-ins only)."""
