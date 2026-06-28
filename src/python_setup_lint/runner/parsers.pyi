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
"""Closed ``parse_strategy`` enum — 12 built-in names + ``regex_count`` /
``raw_lines`` + ``"none"``.  Update alongside ``_BUILTIN_PARSE_STRATEGY_TO_PARSER``
when adding a parser.
"""

def _parse_ruff_statistics(stdout: str, stderr: str) -> list[tuple[str, int]]:
    """Parse ruff ``--statistics`` output.  Format: ``<count>\\t<rule>\\t``."""

def _parse_rumdl_statistics(stdout: str, stderr: str) -> list[tuple[str, int]]:
    """Parse rumdl ``--statistics`` output.  Format matches ruff."""

def _parse_pylint_json2(stdout: str, stderr: str) -> list[tuple[str, int]]:
    """Parse pylint ``--output-format=json2`` output.

    JSON array of dicts, each with a ``symbol`` key.
    """

def _parse_pyright_outputjson(stdout: str, stderr: str) -> list[tuple[str, int]]:
    """Parse pyright ``--outputjson`` output.

    JSON object with ``generalDiagnostics`` array, each entry carrying a
    ``rule`` key.
    """

def _parse_pyright_verify_types(stdout: str, stderr: str) -> list[tuple[str, int]]:
    """Parse pyright ``--verifytypes`` JSON output.

    Reports symbols with completeness < 1.0 as ``verifytypes:incomplete``.
    """

def _parse_mypy_stderr(stdout: str, stderr: str) -> list[tuple[str, int]]:
    """Parse mypy stderr for error-code statistics.

    Extracts the ``[error-code]`` suffix from each error line.
    """

def _parse_ty_concise(stdout: str, stderr: str) -> list[tuple[str, int]]:
    """Parse ty ``--output-format concise`` output.

    Lines: ``file:line:col: error_code message`` — the error code is the
    first non-numeric token after the colon-space.
    """

def _parse_tach_json(stdout: str, stderr: str) -> list[tuple[str, int]]:
    """Parse tach ``--output json`` output.

    JSON object with an ``errors`` list; non-empty → single ``("tach:error", len)``
    pair.
    """

def _parse_yamllint_parsable(stdout: str, stderr: str) -> list[tuple[str, int]]:
    """Parse yamllint ``-f parsable`` output.  Format: ``file:line:col:rule_id:message``."""

def _parse_stubtest_stderr(stdout: str, stderr: str) -> list[tuple[str, int]]:
    """Parse mypy.stubtest stderr for error codes.  Lines: ``error: <code> ...``."""

def _parse_detect_secrets_json(stdout: str, stderr: str) -> list[tuple[str, int]]:
    """Parse detect-secrets ``--json`` output.

    JSON object with ``results`` dict mapping filename → secret list; each
    secret carries a ``type`` key.
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
"""``parse_strategy`` enum name → parser callable for the 12 built-in names.

``regex_count`` is parameterised by the per-entry ``parse_regex`` source
(resolved in :func:`python_setup_lint.runner.extra_tools._extra_tool_parser`);
``raw_lines`` is the single-arg form returned directly.
"""
