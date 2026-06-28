"""Stub for :mod:`python_setup_lint.runner.extra_tools`.

Declarative extra-tools loader (T11 v1) + T8 fail-fast machinery.  Loads
``[[tool.python-setup-lint.extra-tools]]`` entries from ``pyproject.toml``
and registers each via :func:`python_setup_lint.runner.dispatch.register_lint_tool`.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .types import ToolSpec

class ExtraToolsConfigError(Exception):
    """Malformed pyproject / invalid tool config — T8 fail-fast envelope.

    Raised on:

    * A malformed ``[[tool.python-setup-lint.extra-tools]]`` entry (T8 R4
      failure table) — ``location`` is the resolved pyproject path.
    * An unreadable ``pyproject.toml`` (TOMLDecodeError, OSError) when the
      file is present — ``location`` is the resolved pyproject path.
    * An unknown tool name in :attr:`RunnerConfig.tools_override`
      (T8 fail-fast) — ``location`` is the synthetic token
      ``"<RunnerConfig.tools_override>"`` (no file for programmatic input).

    ``SystemExit`` is NOT raised for these — the typed exception propagates
    uncaught to the caller so the call surface (CLI ``main()`` returns int;
    Python API caller catches or Python prints a traceback + exits
    non-zero) is the caller's choice.  ``reason`` is a one-line identifier
    naming the offending key + reason; no raw :class:`KeyError` /
    :class:`ValueError` from ``tomllib`` leaks through.
    """

    location: str
    reason: str

    def __init__(self, location: str, reason: str) -> None: ...

_EXTRA_TOOL_FIELDS: frozenset[str]
"""Allowed ``[[tool.python-setup-lint.extra-tools]]`` entry field set (v1)."""

_EXTRA_TOOL_REQUIRED: tuple[str, ...]
"""Required v1 fields (``name``, ``command``)."""

@dataclass(frozen=True)
class _ExtraToolRegistration:
    """Bundle a validated extra's :class:`ToolSpec` + the registration kwargs.

    :func:`_load_extra_tools` returns these; :func:`_register_extra_tools`
    unpacks each into a :func:`register_lint_tool` call.  Carrying the
    parser callable + ``config_flag`` separately is necessary because
    :class:`ToolSpec` itself is the unchanged NamedTuple from the cycle-1
    contract (T4 owns its shape; T11 only constructs it positionally).
    """

    spec: ToolSpec
    statistics_flag: list[str] | None
    parser: Callable[..., list[tuple[str, int]]] | None
    config_flag: list[str] | None

_REGEX_CACHE: dict[str, re.Pattern[str]]
"""Per-source cache of compiled regexes for ``regex_count`` parse strategy."""

_EXTRA_TOOLS_CACHE: dict[tuple[Path, int], list[_ExtraToolRegistration]]
"""Per-process memo of ``_load_extra_tools`` results keyed by ``(path, mtime_ns)``."""

_EXTRA_TOOLS_REGISTERED_PATHS: set[Path]
"""Paths whose extras have already been registered — prevents re-registration."""

def _compile_regex_count(pattern: str) -> re.Pattern[str]:
    """Compile *pattern* once and cache the result by source string.

    Raises:
        ValueError: when *pattern* is not a valid regex or does NOT have
            exactly one capture group.
    """

def _parse_regex_count(
    stdout: str, stderr: str, *, regex: str
) -> list[tuple[str, int]]:
    """Count distinct capture-group values across all stdout+stderr lines.

    The regex MUST have exactly one capture group; the captured text is the
    rule identifier.  Lines that do not match are skipped.  Both stdout and
    stderr are scanned — most CLIs split diagnostics across the two streams.
    """

def _parse_raw_lines(stdout: str, _stderr: str) -> list[tuple[str, int]]:
    """Count non-empty stdout lines as a single synthetic rule ``"line"``.

    Escape hatch for tools with no notion of rule identifiers.  stderr is
    ignored (most tools surface diagnostics on stdout).
    """

def _extra_tool_parser(
    *,
    entry: dict[str, object],
    location: str,
) -> Callable[..., list[tuple[str, int]]] | None:
    """Resolve the parser callable for an extra-tools entry's ``parse_strategy``.

    Returns ``None`` for ``"none"`` (skip statistics aggregation).  For
    built-in strategy names, returns the parser verbatim.  For
    ``"regex_count"``, validates ``parse_regex`` is present and has exactly
    one capture group; returns a closure binding the compiled regex.  For
    ``"raw_lines"``, returns the parser directly.

    Raises:
        ExtraToolsConfigError: on a bad enum value, missing/invalid
            ``parse_regex``, or a regex without exactly one capture group.
    """

def _validate_extra_bool_fields(
    entry: dict[str, object], location: str
) -> tuple[bool, bool, bool]:
    """Validate supports_fix, supports_path, supports_exclude fields."""

def _validate_extra_list_field(
    entry: dict[str, object], key: str, location: str
) -> list[str]:
    """Validate a list-of-strings field and return the validated list."""

def _validate_extra_config_flag(
    entry: dict[str, object], location: str
) -> list[str] | None:
    """Validate config_flag field (str, list[str], or None)."""

def _validate_extra_fields(  # validated dict, keys are known strings; return dict is built from validated fields, values are str|list[str]|None|bool by construction
    entry: dict[str, object], location: str
    ) -> dict[str, Any]:  # validated dict, keys are known strings; values are str|list[str]|None|bool by construction
    """Validate all fields in an extra-tool entry and return validated values."""

def _validate_extra_name(
    name: str, seen_names: set[str], location: str
) -> str:
    """Validate extra-tool name uniqueness and return the validated name."""

def _validate_extra(  # validated dict, keys are known strings; Any because values are heterogeneous (str|list[str]|None|bool) by construction
    entry: dict[str, Any],
    *,
    location: str,
    seen_names: set[str],
) -> _ExtraToolRegistration:
    """Validate a single ``[[tool.python-setup-lint.extra-tools]]`` entry.

    Implements the T8 R4 failure table: missing required field, wrong type,
    empty name, duplicate within file, duplicate vs built-in, bad enum,
    regex missing or != 1 capture group, unknown field.  Each failure raises
    :class:`ExtraToolsConfigError` with a one-line ``reason`` identifier.

    Raises:
        ExtraToolsConfigError: on any malformed shape per T8 R4.
    """

def _reset_extra_tools_cache() -> None:
    """Clear the per-process memo for ``_load_extra_tools`` (test-only).

    Production callers should NOT invoke this; the cache invalidates on
    mtime change.  Tests use it to force a re-parse against a rewritten
    synthetic pyproject.toml in the same process.
    """

def _load_extra_tools(cwd: Path) -> list[_ExtraToolRegistration]:
    """Load ``[[tool.python-setup-lint.extra-tools]]`` entries from ``cwd/pyproject.toml``.

    Returns ``[]`` when the file is missing, the section is absent, the
    ``extra-tools`` key is empty, or every ``[[...]]`` block is empty.

    Raises:
        ExtraToolsConfigError: when ``pyproject.toml`` is unreadable OR a
            ``[[...]]`` entry fails :func:`_validate_extra` (T8 R4 table).
    """

def register_lint_tool(
    tool: ToolSpec, *, statistics_flag: str | None = None, parser: Callable[..., list[tuple[str, int]]] | None = None,
) -> None:
    """Register a custom lint tool (re-exported from dispatch)."""


def _register_extra_tools(registrations: list[_ExtraToolRegistration]) -> None:
    """Register each validated extra via :func:`register_lint_tool`.

    Idempotent — :func:`register_lint_tool` is already idempotent per
    ``tool.name`` so a re-merge in the same process is a no-op.

    Raises:
        ExtraToolsConfigError: when an extra's name collides with a built-in
            name (T8 R3 — defense-in-depth; :func:`_validate_extra` already
            rejects at load time).
    """
