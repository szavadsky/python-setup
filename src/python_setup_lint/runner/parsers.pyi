"""Stub for :mod:`python_setup_lint.runner.parsers`.

Statistics output parsers + dispatch tables.  A parser turns
``(stdout, stderr)`` from a tool's statistics-mode invocation into
``list[(rule, count)]``.  T2 adds the :class:`Record` violation-record
dataclass plus per-tool ``_parse_<tool>_records`` line→record parsers
feeding the drift-resistant baseline.
"""


from collections.abc import Callable

from ._record_types import Record

__all__ = [
    "PARSE_STRATEGIES",
    "Record",
]

PARSE_STRATEGIES: frozenset[str]
"""Closed ``parse_strategy`` enum — 13 built-in names + ``regex_count`` /
``raw_lines`` + ``"none"``.  Update alongside ``_BUILTIN_PARSE_STRATEGY_TO_PARSER``
when adding a parser.
"""

_RECORD_PARSERS: dict[str, Callable[..., list[Record]]]
"""Per-tool record-parser dispatch keyed by built-in tool name.

Tools absent here keep the legacy rstrip-set behaviour in
:mod:`python_setup_lint.runner.baseline`.  JSON-native tools (pyright,
rumdl-when-JSON) go through ``baseline.py``'s diagnostics path instead.
"""

_STATISTICS_PARSERS: dict[str, Callable[..., list[tuple[str, int]]]]
"""Per-tool parser dispatch keyed by built-in :class:`~python_setup_lint.runner.types.ToolSpec` name."""

_BUILTIN_PARSE_STRATEGY_TO_PARSER: dict[str, Callable[..., list[tuple[str, int]]]]
"""``parse_strategy`` enum name → parser callable for the 13 built-in names.

``regex_count`` is parameterised by the per-entry ``parse_regex`` source
(resolved in :func:`python_setup_lint.runner.extra_tools._extra_tool_parser`);
``raw_lines`` is the single-arg form returned directly.
"""
