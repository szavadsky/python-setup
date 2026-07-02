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

All built-in tools now have record parsers; the new violations-only
baseline captures every tool through its record parser.  Tools without
a parser produce no violations.
"""

_STATISTICS_PARSERS: dict[str, Callable[..., list[tuple[str, int]]]]
"""Per-tool parser dispatch keyed by built-in :class:`~python_setup_lint.runner.types.ToolSpec` name."""

_BUILTIN_PARSE_STRATEGY_TO_PARSER: dict[str, Callable[..., list[tuple[str, int]]]]
"""``parse_strategy`` enum name → parser callable for the 13 built-in names.

``regex_count`` is parameterised by the per-entry ``parse_regex`` source
(resolved in :func:`python_setup_lint.runner.extra_tools._extra_tool_parser`);
``raw_lines`` is the single-arg form returned directly.
"""

def _parse_ruff_statistics(stdout: str, stderr: str) -> list[tuple[str, int]]: ...
def _parse_rumdl_statistics(stdout: str, stderr: str) -> list[tuple[str, int]]: ...
def _parse_pylint_json2(stdout: str, stderr: str) -> list[tuple[str, int]]: ...
def _parse_pyright_outputjson(stdout: str, stderr: str) -> list[tuple[str, int]]: ...
def _parse_pyright_verify_types(stdout: str, stderr: str) -> list[tuple[str, int]]: ...
def _parse_mypy_stderr(stdout: str, stderr: str) -> list[tuple[str, int]]: ...
def _parse_ty_concise(stdout: str, stderr: str) -> list[tuple[str, int]]: ...
def _parse_tach_json(stdout: str, stderr: str) -> list[tuple[str, int]]: ...
def _parse_yamllint_parsable(stdout: str, stderr: str) -> list[tuple[str, int]]: ...
def _parse_stubtest_stderr(stdout: str, stderr: str) -> list[tuple[str, int]]: ...
def _parse_detect_secrets_json(stdout: str, stderr: str) -> list[tuple[str, int]]: ...
