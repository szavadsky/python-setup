"""Statistics output parsers + dispatch tables.

A parser turns ``(stdout, stderr)`` from a tool's statistics-mode invocation
into ``list[(rule, count)]``.  The module-level
:data:`_STATISTICS_PARSERS` maps each built-in tool's :class:`~python_setup_lint.runner.types.ToolSpec`
name to its parser; :data:`_BUILTIN_PARSE_STRATEGY_TO_PARSER` maps the closed
``parse_strategy`` enum to the same callables for the extra-tools loader.

T2 adds the :class:`Record` violation-record dataclass plus per-tool
``_parse_<tool>_records`` line->record parsers feeding the drift-resistant
baseline (:mod:`python_setup_lint.runner.baseline`).
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from ._record_parsers import (  # noqa: F401  # re-exported for backward compat
    _parse_mypy_records,
    _parse_pylint_records,
    _parse_pyright_records,
    _parse_ruff_records,
    _parse_rumdl_records,
    _parse_ty_records,
    _parse_yamllint_records,
)
from ._record_types import Record  # noqa: F401  # re-exported for backward compat

if TYPE_CHECKING:
    from collections.abc import Callable


__all__ = [
    "PARSE_STRATEGIES",
    "Record",
]


# ── Helpers ──────────────────────────────────────────────────────────


def _load_json_dict(data: str) -> dict[str, Any]:
    try:
        result = json.loads(data)
    except json.JSONDecodeError:
        return {}
    return result if isinstance(result, dict) else {}


def _count_lines(
    pattern: re.Pattern[str],
    text: str,
    group: int = 1,
) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for line in text.splitlines():
        m = pattern.search(line)
        if m:
            code = m.group(group)
            counts[code] = counts.get(code, 0) + 1
    return list(counts.items())


# ── Statistics parsers ───────────────────────────────────────────────


def _parse_ruff_statistics(stdout: str, stderr: str) -> list[tuple[str, int]]:
    _ = stderr
    counts: dict[str, int] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line or line.startswith(("-", "Count")):
            continue
        m = re.match(r"^(\d+)\s+(\S+)", line)
        if m:
            counts[m.group(2)] = counts.get(m.group(2), 0) + int(m.group(1))
    return list(counts.items())


def _parse_rumdl_statistics(stdout: str, stderr: str) -> list[tuple[str, int]]:
    _ = stderr
    counts: dict[str, int] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^[^:]+:\d+:\d+:\s+\[(\S+)\]", line)
        if m:
            rule = m.group(1)
            counts[rule] = counts.get(rule, 0) + 1
    return list(counts.items())


def _parse_pylint_json2(stdout: str, stderr: str) -> list[tuple[str, int]]:
    _ = stderr
    try:
        raw: Any = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return []
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
    _ = stderr
    data = _load_json_dict(stdout)
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
    _ = stderr
    data = _load_json_dict(stdout)
    tc = data.get("typeCompleteness", {})
    if not isinstance(tc, dict):
        return []
    symbols = tc.get("symbols", [])
    if not isinstance(symbols, list):
        return []
    incomplete = sum(
        1 for s in symbols if isinstance(s, dict) and s.get("completeness", 1.0) < 1.0
    )
    return [("verifytypes:incomplete", incomplete)] if incomplete else []


def _parse_mypy_stderr(stdout: str, stderr: str) -> list[tuple[str, int]]:
    _ = stdout
    return _count_lines(re.compile(r"\[([^\]]+)\]$"), stderr)


def _parse_ty_concise(stdout: str, stderr: str) -> list[tuple[str, int]]:
    _ = stderr
    return _count_lines(re.compile(r":\s+(\S+)\s+"), stdout)


def _parse_tach_json(stdout: str, stderr: str) -> list[tuple[str, int]]:
    _ = stderr
    data = _load_json_dict(stdout)
    errors = data.get("errors", [])
    if isinstance(errors, list) and errors:
        return [("tach:error", len(errors))]
    return []


def _parse_yamllint_parsable(stdout: str, stderr: str) -> list[tuple[str, int]]:
    _ = stderr
    counts: dict[str, int] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(":")
        if len(parts) >= 4 and parts[3]:
            counts[parts[3]] = counts.get(parts[3], 0) + 1
    return list(counts.items())


def _parse_stubtest_stderr(stdout: str, stderr: str) -> list[tuple[str, int]]:
    _ = stdout
    return _count_lines(re.compile(r"^error:\s+(\S+)"), stderr)


def _parse_detect_secrets_json(stdout: str, stderr: str) -> list[tuple[str, int]]:
    _ = stderr
    data = _load_json_dict(stdout)
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


# ── Dispatch tables ─────────────────────────────────────────────────

_RECORD_PARSERS: dict[str, Callable[..., list[Record]]] = {
    "ruff check": _parse_ruff_records,
    "mypy": _parse_mypy_records,
    "pylint": _parse_pylint_records,
    "pylint-pyi": _parse_pylint_records,
    "ty check": _parse_ty_records,
    "yamllint": _parse_yamllint_records,
    "rumdl check": _parse_rumdl_records,
}

_STATISTICS_PARSERS: dict[str, Callable[..., list[tuple[str, int]]]] = {
    "ruff check": _parse_ruff_statistics,
    "rumdl check": _parse_rumdl_statistics,
    "pylint": _parse_pylint_json2,
    "pylint-pyi": _parse_pylint_json2,
    "pyright check": _parse_pyright_outputjson,
    "pyright verify types": _parse_pyright_verify_types,
    "mypy": _parse_mypy_stderr,
    "ty check": _parse_ty_concise,
    "tach check": _parse_tach_json,
    "yamllint": _parse_yamllint_parsable,
    "mypy.stubtest": _parse_stubtest_stderr,
    "detect-secrets": _parse_detect_secrets_json,
}

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
