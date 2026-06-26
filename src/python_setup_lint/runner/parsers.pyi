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
"""Closed ``parse_strategy`` enum — 11 built-in names + ``regex_count`` /
``raw_lines`` + ``"none"``.  Update alongside ``_BUILTIN_PARSE_STRATEGY_TO_PARSER``
when adding a parser.
"""

    """Parse ruff ``--statistics`` output.  Format: ``<count>\\t<rule>\\t``."""

    """Parse rumdl ``--statistics`` output.  Format matches ruff."""

    """Parse pylint ``--output-format=json2`` output.

    JSON array of dicts, each with a ``symbol`` key.
    """

    """Parse pyright ``--outputjson`` output.

    JSON object with ``generalDiagnostics`` array, each entry carrying a
    ``rule`` key.
    """

    """Parse pyright ``--verifytypes`` JSON output.

    Reports symbols with completeness < 1.0 as ``verifytypes:incomplete``.
    """

    """Parse mypy stderr for error-code statistics.

    Extracts the ``[error-code]`` suffix from each error line.
    """

    """Parse ty ``--output-format concise`` output.

    Lines: ``file:line:col: error_code message`` — the error code is the
    first non-numeric token after the colon-space.
    """

    """Parse tach ``--output json`` output.

    JSON object with an ``errors`` list; non-empty → single ``("tach:error", len)``
    pair.
    """

    """Parse yamllint ``-f parsable`` output.  Format: ``file:line:col:rule_id:message``."""

    """Parse mypy.stubtest stderr for error codes.  Lines: ``error: <code> ...``."""

    """Parse detect-secrets ``--json`` output.

    JSON object with ``results`` dict mapping filename → secret list; each
    secret carries a ``type`` key.
    """

"""Per-tool record-parser dispatch keyed by built-in tool name.

Tools absent here keep the legacy rstrip-set behaviour in
:mod:`python_setup_lint.runner.baseline`.  JSON-native tools (pyright,
rumdl-when-JSON) go through ``baseline.py``'s diagnostics path instead.
"""

"""Per-tool parser dispatch keyed by built-in :class:`~python_setup_lint.runner.types.ToolSpec` name."""

"""``parse_strategy`` enum name → parser callable for the 11 built-in names.

``regex_count`` is parameterised by the per-entry ``parse_regex`` source
(resolved in :func:`python_setup_lint.runner.extra_tools._extra_tool_parser`);
``raw_lines`` is the single-arg form returned directly.
"""
