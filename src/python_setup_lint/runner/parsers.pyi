"""Stub for :mod:`python_setup_lint.runner.parsers`.

Statistics output parsers + dispatch tables.  A parser turns
``(stdout, stderr)`` from a tool's statistics-mode invocation into
``list[(rule, count)]``.  T2 adds the :class:`Record` violation-record
dataclass plus per-tool ``_parse_<tool>_records`` line→record parsers
feeding the drift-resistant baseline.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class Record:
    """A single lint violation, order-tolerant + multiset-accurate.

    Invariant: records are kept sorted by ``(file, line, col, rule)``
    (the baseline diff reduces to a walk-merge over two sorted lists →
    O(n log n) sort + O(n) merge).  ``msg`` participates in equality so
    a same-key message rewrite still flags as a regression; identical
    records are distinct multiset members (count preserved).

    Attributes:
        file: Source file path or ``None`` for position-less messages
            (e.g. pylint ``R0801``/``R0401`` collapse signatures).
        line: 1-indexed source line or ``None``.
        col: 1-indexed source column or ``None``.
        rule: Rule / error code; for pylint R0801/R0401 this is the
            canonical collapse signature.
        msg: Human-readable violation message (participates in equality).
    """

    file: str | None
    line: int | None
    col: int | None
    rule: str
    msg: str

def _compare_records_key(rec: Record) -> tuple[Any, Any, Any, str]:
    """Stable sort key for the O(n log n) walk-merge.

    ``(file, line, col, rule)`` with ``None`` coerced to an empty-tuple
    sentinel that sorts below any real value — heterogeneous
    ``None`` vs ``str``/``int`` comparisons never raise.
    """

def _records_unchanged(a: list[Record], b: list[Record]) -> bool:
    """True iff sorted multiset of *a* equals sorted multiset of *b* (both pre-sorted)."""

PARSE_STRATEGIES: frozenset[str]
"""Closed ``parse_strategy`` enum — 11 built-in names + ``regex_count`` /
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

# ── Per-tool violation-record parsers (T2 baseline diff) ──────────

def _parse_pylint_records(stdout: str) -> list[Record]:
    """Parse pylint *text* output into sorted records.

    R0801/R0401 collapse to ONE record each whose ``rule`` is the canonical
    signature (``R0801:<sorted-spans>``, ``R0401:<cycle>``); remaining
    lines follow ``path:line:col: CODE: msg (symbol)`` — ``rule`` is the
    symbol when present, the bare code otherwise.
    """

def _parse_ruff_records(stdout: str) -> list[Record]:
    """Parse ruff text output into sorted records.  Format: ``path:line:col: CODE msg``."""

def _parse_mypy_records(stdout: str) -> list[Record]:
    """Parse mypy stdout into sorted records.  Lines without a code are skipped."""

def _parse_ty_records(stdout: str) -> list[Record]:
    """Parse ty ``--output-format concise`` AND the default multiline output.

    Multiline form: ``error[code]: msg`` + ``--> path:line:col`` arrow.
    """

def _parse_yamllint_records(stdout: str) -> list[Record]:
    """Parse yamllint ``-f parsable`` output into sorted records."""

def _parse_rumdl_records(stdout: str) -> list[Record]:
    """Parse rumdl check text output into sorted records (legacy text path).

    Multiline ``Found N issues in M files (XXXms)`` footer is filtered out.
    JSON-emitting rumdl runs are consumed directly as ``diagnostics`` in
    ``baseline.py``.
    """

def _parse_pyright_records(data: object) -> list[Record]:
    """Parse the pre-loaded pyright ``--outputjson`` dict into sorted records.

    Pyright lines/cols are 0-indexed; converted to 1-indexed to match the
    other tools.  Returns ``[]`` on an unexpected shape (caller falls back
    to the legacy set-diff path if the source stdout was non-empty).
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
"""``parse_strategy`` enum name → parser callable for the 11 built-in names.

``regex_count`` is parameterised by the per-entry ``parse_regex`` source
(resolved in :func:`python_setup_lint.runner.extra_tools._extra_tool_parser`);
``raw_lines`` is the single-arg form returned directly.
"""
