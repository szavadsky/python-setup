"""Statistics output parsers + dispatch tables.

A parser turns ``(stdout, stderr)`` from a tool's statistics-mode invocation
into ``list[(rule, count)]``.  The module-level
:data:`_STATISTICS_PARSERS` maps each built-in tool's :class:`~python_setup_lint.runner.types.ToolSpec`
name to its parser; :data:`_BUILTIN_PARSE_STRATEGY_TO_PARSER` maps the closed
``parse_strategy`` enum (T11 v1) to the same callables for the extra-tools
loader.

Importing this module has NO side effects on the live strategy registry —
the dispatch module wires parsers into :class:`~python_setup_lint.runner.dispatch.LintTool`
strategies via :data:`_STATISTICS_PARSERS`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

__all__ = [
    "PARSE_STRATEGIES",
    "_BUILTIN_PARSE_STRATEGY_TO_PARSER",
    "_STATISTICS_PARSERS",
    "_parse_detect_secrets_json",
    "_parse_mypy_stderr",
    "_parse_pylint_json2",
    "_parse_pyright_outputjson",
    "_parse_pyright_verify_types",
    "_parse_ruff_statistics",
    "_parse_rumdl_statistics",
    "_parse_stubtest_stderr",
    "_parse_tach_json",
    "_parse_ty_concise",
    "_parse_yamllint_parsable",
]


def _parse_ruff_statistics(stdout: str, stderr: str) -> list[tuple[str, int]]:
    """Parse ruff --statistics output.

    Each non-header line: ``<count>\t<rule>\t``.
    """
    _ = stderr
    counts: dict[str, int] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line or line.startswith(("-", "Count")):
            continue
        m = re.match(r"^(\d+)\s+(\S+)", line)
        if m:
            rule = m.group(2)
            counts[rule] = counts.get(rule, 0) + int(m.group(1))
    return list(counts.items())


def _parse_rumdl_statistics(stdout: str, stderr: str) -> list[tuple[str, int]]:
    """Parse rumdl check output.

    rumdl has no ``--statistics`` flag.  Its per-violation output format
    is ``file:line:col: [RULE] message``.  This parser aggregates
    violations by rule code (e.g. ``MD041``).
    """
    _ = stderr
    counts: dict[str, int] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # Format: file:line:col: [RULE] message
        m = re.match(r"^[^:]+:\d+:\d+:\s+\[(\S+)\]", line)
        if m:
            rule = m.group(1)
            counts[rule] = counts.get(rule, 0) + 1
    return list(counts.items())


def _parse_pylint_json2(stdout: str, stderr: str) -> list[tuple[str, int]]:
    """Parse pylint --output-format=json2 output.

    Accepts both the legacy JSON array shape (``[{...}, ...]``) and the
    modern dict shape (``{"messages": [{...}, ...], "status": ...}``).
    Each message dict has a ``symbol`` key.
    """
    _ = stderr
    try:
        raw: Any = json.loads(stdout)
    except json.JSONDecodeError, TypeError:
        return []
    # Modern dict shape: {"messages": [...], "status": ...}
    if isinstance(raw, dict):
        raw = raw.get("messages", [])
    if not isinstance(raw, list):
        return []
    counts: dict[str, int] = {}
    for msg in raw:
        symbol = msg.get("symbol") if isinstance(msg, dict) else None
        if isinstance(symbol, str):
            counts[symbol] = counts.get(symbol, 0) + 1
    return list(counts.items())


def _parse_pyright_outputjson(stdout: str, stderr: str) -> list[tuple[str, int]]:
    """Parse pyright --outputjson output.

    JSON object with ``generalDiagnostics`` array, each with a ``rule`` key.
    """
    _ = stderr
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    diags = data.get("generalDiagnostics", [])
    if not isinstance(diags, list):
        return []
    counts: dict[str, int] = {}
    for d in diags:
        rule = d.get("rule") if isinstance(d, dict) else None
        if isinstance(rule, str):
            counts[rule] = counts.get(rule, 0) + 1
    return list(counts.items())


def _parse_pyright_verify_types(stdout: str, stderr: str) -> list[tuple[str, int]]:
    """Parse pyright --verifytypes JSON output.

    JSON object with ``typeCompleteness`` containing per-symbol results.
    Reports any ``symbolName`` with completeness < 1.0 as
    ``verifytypes:incomplete``.
    """
    _ = stderr
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    tc = data.get("typeCompleteness", {})
    if not isinstance(tc, dict):
        return []
    symbols = tc.get("symbols", [])
    if not isinstance(symbols, list):
        return []
    incomplete = 0
    for s in symbols:
        if isinstance(s, dict) and s.get("completeness", 1.0) < 1.0:
            incomplete += 1
    if incomplete:
        return [("verifytypes:incomplete", incomplete)]
    return []


def _parse_mypy_stderr(stdout: str, stderr: str) -> list[tuple[str, int]]:
    """Parse mypy stderr for error-code statistics.

    Each error line: ``file:line: error: message [error-code]`` — extracts
    the ``[error-code]`` from the end of each line.
    """
    _ = stdout
    counts: dict[str, int] = {}
    for line in stderr.splitlines():
        m = re.search(r"\[([^\]]+)\]$", line)
        if m:
            code = m.group(1)
            counts[code] = counts.get(code, 0) + 1
    return list(counts.items())


def _parse_ty_concise(stdout: str, stderr: str) -> list[tuple[str, int]]:
    """Parse ty --output-format concise output.

    Lines: ``file:line:col: error_code message`` — the error code is the
    first non-numeric token after the colon-space.
    """
    _ = stderr
    counts: dict[str, int] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # Format: file:line:col: error_code message
        # Extract error_code after the last colon-space.
        m = re.search(r":\s+(\S+)\s+", line)
        if m:
            code = m.group(1)
            counts[code] = counts.get(code, 0) + 1
    return list(counts.items())


def _parse_tach_json(stdout: str, stderr: str) -> list[tuple[str, int]]:
    """Parse tach --output json output.

    JSON object with ``errors`` list.
    """
    _ = stderr
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    errors = data.get("errors", [])
    if isinstance(errors, list) and errors:
        return [("tach:error", len(errors))]
    return []


def _parse_yamllint_parsable(stdout: str, stderr: str) -> list[tuple[str, int]]:
    """Parse yamllint -f parsable output.

    Format: ``file:line:col:rule_id:message``.
    """
    _ = stderr
    counts: dict[str, int] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(":")
        # file:line:col:rule_id:message → parts[3] is rule_id
        if len(parts) >= 4:
            rule_id = parts[3]
            if rule_id:
                counts[rule_id] = counts.get(rule_id, 0) + 1
    return list(counts.items())


def _parse_stubtest_stderr(stdout: str, stderr: str) -> list[tuple[str, int]]:
    """Parse mypy.stubtest stderr for error codes.

    Lines: ``error: <code>`` — extracts the code after ``error: `` and
    before the first space.
    """
    _ = stdout
    counts: dict[str, int] = {}
    for line in stderr.splitlines():
        m = re.match(r"^error:\s+(\S+)", line)
        if m:
            code = m.group(1)
            counts[code] = counts.get(code, 0) + 1
    return list(counts.items())


def _parse_detect_secrets_json(stdout: str, stderr: str) -> list[tuple[str, int]]:
    """Parse detect-secrets --json output.

    JSON object with ``results`` dict mapping filename to list of secrets,
    each with a ``type`` key.
    """
    _ = stderr
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    results = data.get("results", {})
    if not isinstance(results, dict):
        return []
    counts: dict[str, int] = {}
    for secrets in results.values():
        if not isinstance(secrets, list):
            continue
        for secret in secrets:
            if isinstance(secret, dict):
                secret_type = secret.get("type", "unknown")
                if isinstance(secret_type, str):
                    counts[secret_type] = counts.get(secret_type, 0) + 1
    return list(counts.items())


# ── Parser dispatch table ──────────────────────────────────────────
_STATISTICS_PARSERS: dict[str, Callable[..., list[tuple[str, int]]]] = {
    "ruff check": _parse_ruff_statistics,
    "rumdl check": _parse_rumdl_statistics,
    "pylint": _parse_pylint_json2,
    "pyright check": _parse_pyright_outputjson,
    "pyright verify types": _parse_pyright_verify_types,
    "mypy": _parse_mypy_stderr,
    "ty check": _parse_ty_concise,
    "tach check": _parse_tach_json,
    "yamllint": _parse_yamllint_parsable,
    "mypy.stubtest": _parse_stubtest_stderr,
    "detect-secrets": _parse_detect_secrets_json,
}

# Map the ``parse_strategy`` enum name to the parser callable for the 11
# built-in strategy names (verbatim).  ``regex_count`` is parameterised by
# the per-entry ``parse_regex`` source — resolved in
# :func:`python_setup_lint.runner.extra_tools._extra_tool_parser`.  ``raw_lines``
# is the single-arg form returned directly by that resolver.

_BUILTIN_PARSE_STRATEGY_TO_PARSER: dict[str, Callable[..., list[tuple[str, int]]]] = {
    "ruff_statistics": _parse_ruff_statistics,
    "rumdl_statistics": _parse_rumdl_statistics,
    "pylint_json2": _parse_pylint_json2,
    "pyright_outputjson": _parse_pyright_outputjson,
    "pyright_verify_types": _parse_pyright_verify_types,
    "mypy_stderr": _parse_mypy_stderr,
    "ty_concise": _parse_ty_concise,
    "tach_json": _parse_tach_json,
    "yamllint_parsable": _parse_yamllint_parsable,
    "stubtest_stderr": _parse_stubtest_stderr,
    "detect_secrets_json": _parse_detect_secrets_json,
}

# Closed ``parse_strategy`` enum — names the 11 built-in parsers verbatim
# plus the two generic parsers (T11) plus ``"none"`` (skip stats
# aggregation, mirroring the ``_aggregate_statistics`` skip).  Update this
# string set AND ``_BUILTIN_PARSE_STRATEGY_TO_PARSER`` together when adding
# a parser.
PARSE_STRATEGIES: frozenset[str] = frozenset(
    {
        "none",
        "ruff_statistics",
        "rumdl_statistics",
        "pylint_json2",
        "pyright_outputjson",
        "pyright_verify_types",
        "mypy_stderr",
        "ty_concise",
        "tach_json",
        "yamllint_parsable",
        "stubtest_stderr",
        "detect_secrets_json",
        "regex_count",
        "raw_lines",
    }
)
