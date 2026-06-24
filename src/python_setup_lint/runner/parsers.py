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

T2 adds the :class:`Record` violation-record dataclass plus per-tool
``_parse_<tool>_records`` line→record parsers feeding the drift-resistant
baseline (:mod:`python_setup_lint.runner.baseline`).  ``Records`` are
multiset-accurate (sorted list, count implicit) and order-tolerant by
construction (sorted by ``(file, line, col, rule)``).  R0801/R0401 pylint
messages collapse to one record whose ``rule`` carries the canonical
duplicate-region / cyclic-import signature (per-tool inventory semantics
preserved from the pre-T2 :func:`_pylint_inventory` helper).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

__all__ = [
    "PARSE_STRATEGIES",
    "Record",
    "_BUILTIN_PARSE_STRATEGY_TO_PARSER",
    "_RECORD_PARSERS",
    "_STATISTICS_PARSERS",
    "_compare_records_key",
    "_parse_detect_secrets_json",
    "_parse_mypy_records",
    "_parse_mypy_stderr",
    "_parse_pylint_json2",
    "_parse_pylint_records",
    "_parse_pyright_outputjson",
    "_parse_pyright_records",
    "_parse_pyright_verify_types",
    "_parse_ruff_records",
    "_parse_ruff_statistics",
    "_parse_rumdl_records",
    "_parse_rumdl_statistics",
    "_parse_stubtest_stderr",
    "_parse_tach_json",
    "_parse_ty_concise",
    "_parse_ty_records",
    "_parse_yamllint_parsable",
    "_parse_yamllint_records",
    "_records_unchanged",
]


@dataclass(frozen=True)
class Record:
    """A single lint violation, order-tolerant + multiset-accurate.

    Invariant (enforced by :func:`_compare_records_key`): records are kept
    sorted by ``(file, line, col, rule)`` so a baseline diff reduces to a
    walk-merge over two sorted lists → O(n log n) after sort, O(n) merge.
    The ``msg`` slot participates in equality so identical
    ``(file,line,col,rule)`` with a *different* message counts as a real
    change (regression), but two records with the same key are distinct
    multiset members (count preserved).  ``file``/``line``/``col`` are
    ``None`` for tools that emit no position (e.g. pylint ``R0801``/
    ``R0401`` whose identity is the signature-encoded ``rule``).

    Attributes:
        file: Source file path (relative to project root) or ``None``.
        line: 1-indexed source line or ``None``.
        col: 1-indexed source column or ``None``.
        rule: Rule / error code.  For pylint R0801/R0401 this is the
            canonical collapse signature (``R0801:...``, ``R0401:...``)
            so a duplicate-region reorder is byte-identical pre/post.
        msg: Human-readable violation message; participates in record
            equality (multiset-aware: a same-key rewrite of the message
            still flags as a regression).
    """

    file: str | None
    line: int | None
    col: int | None
    rule: str
    msg: str


def _compare_records_key(rec: Record) -> tuple[Any, Any, Any, str]:
    """Stable sort key for the O(n log n) walk-merge.

    ``(file, line, col, rule)``; ``None`` sorts BELOW every real value so
    ``None``-position records (e.g. R0801 collapse) cluster together.
    ``None`` is coerced to a sentinel tuple member so heterogeneous
    comparisons (``None`` vs ``str`` / ``int``) do not raise — Python
    refuses ``None < "x"`` even though it tolerates ``None == None``.
    The sentinel is the empty tuple ``()`` which compares less than any
    non-empty tuple at the same position, so a ``None`` in *file* sorts
    ahead of a real file string at *file*.
    """
    file_k: tuple = () if rec.file is None else (rec.file,)
    line_k: tuple = () if rec.line is None else (rec.line,)
    col_k: tuple = () if rec.col is None else (rec.col,)
    return (file_k, line_k, col_k, rec.rule)


def _records_unchanged(a: list[Record], b: list[Record]) -> bool:
    """True iff sorted multiset of *a* equals sorted multiset of *b*.

    Cheap reference equality used by the baseline diff to short-circuit
    the no-delta case.  Both sides must already be sorted (callers sort
    once at capture / load boundary).
    """
    return len(a) == len(b) and all(x == y for x, y in zip(a, b, strict=True))


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
    except (json.JSONDecodeError, TypeError):
        # Py3.14 WARNING: ``except A, B:`` parses as a tuple-handler
        # (``except (A, B):``), NOT Python-2 ``except AExc, target:``.
        # Parenthesise explicitly so future maintainers don't misread it
        # as a binding form (per decisions.md D8 precedent).
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


# ── Per-tool violation-record parsers (T2 baseline diff) ──────────
# A record parser turns ``stdout`` (string OR pre-parsed JSON object for
# the JSON-emitting tools) into ``list[Record]`` sorted by
# ``(file, line, col, rule)``.  Order-tolerant by construction;
# multiset-accurate because the count is implicit in the sorted list.
# Pylint keeps its pre-T2 R0801/R0401 signature-collapse behaviour
# INSIDE the parser so a duplicate-region reorder produces a
# byte-identical record set (no spurious diff).  Tools whose stdout a
# parser cannot match fall back to the legacy rstrip-set path in
# :mod:`python_setup_lint.runner.baseline` (with a ``decisions.md`` note).


def _parse_int(text: str) -> int | None:
    """Parse a leading integer; ``None`` when not an int (no exception)."""
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


# Pylint message line. Format emitted by the text renderer:
#   path:line:col: CODE: message (symbol)
# Capture the symbol when present (preferred over the bare CODE) so
# post-fix renaming of a rule code (e.g. ``W0611`` → ``unused-import``)
# does not cause a spurious diff as long as the symbol is stable.
_PYLINT_LINE_RE = re.compile(
    r"^(?P<file>\S+?):(?P<line>\d+):(?P<col>\d+):\s*"
    r"(?P<code>[A-Za-z]\d+): (?P<msg>.*?)"
    r"(?:\s+\((?P<symbol>[\w-]+)\))?\s*$"
)

# Pylint R0801 similar-lines span marker.  The real pylint renderer
# emits spans either on a dedicated line (``==file:[l:c]``) or two spans
# per line in compact form (``==a:[l:c] ==b:[l:c]``).  Either way, the
# spans always appear as a consecutive run of markers; the collapse rule
# is the sorted ``(file:l-c)`` pair.
_PYLINT_R0801_SPAN_RE = re.compile(r"==(?P<f>\S+?):\[(?P<l>\d+):(?P<c>\d+)\]")

# Pylint R0401 (cyclic-import) — the cycle is the identity.
_PYLINT_R0401_RE = re.compile(r"Cyclic import \((?P<cycle>[^)]+)\)")


def _parse_pylint_records(stdout: str) -> list[Record]:
    """Parse pylint *text* output (non-JSON mode) into sorted records.

    R0801/R0401 collapse: a duplicate-region or cyclic-import message
    maps to ONE record whose ``rule`` carries the canonical signature
    (``R0801:<sorted-spans>``, ``R0401:<cycle>``) and ``file``/``line``/
    ``col`` are ``None``.  The R0801 header spans multiple lines (a
    ``Similar lines in N files`` banner followed by one or two
    ``==file:[l:c]`` span marker lines); this parser scans for spans on
    the banner line AND any immediately-following span-marker lines,
    then emits one collapse record per consecutive pair (pylint always
    emits exactly two spans per similar-region report).  Remaining
    message lines follow the standard ``path:line:col: CODE: msg
    (symbol)`` shape; ``rule`` is the symbol when present, the bare
    code otherwise.
    """
    records: list[Record] = []
    lines = stdout.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].rstrip()
        # R0401 cyclic-import: self-contained on one line.
        cyc = _PYLINT_R0401_RE.search(line)
        if cyc:
            records.append(Record(None, None, None, f"R0401:{cyc.group('cycle')}", line))
            i += 1
            continue
        # R0801 similar-lines: gather all ``==file:[l:c]`` spans starting
        # on THIS line (inline form OR the banner line) and continuing
        # across subsequent span-marker-only lines (multi-line form).
        # pylint always emits exactly two spans per similar-region report.
        is_banner = "Similar lines in" in line or _PYLINT_R0801_SPAN_RE.search(line)
        if is_banner:
            collected: list[tuple[str, str, str]] = list(_PYLINT_R0801_SPAN_RE.findall(line))
            j = i + 1
            while j < n and len(collected) < 2:
                nxt = lines[j].rstrip()
                nxt_spans = _PYLINT_R0801_SPAN_RE.findall(nxt)
                if not nxt_spans:
                    break
                collected.extend(nxt_spans)
                j += 1
            if len(collected) >= 2:
                spans = sorted([
                    f"{collected[0][0]}:{collected[0][1]}-{collected[0][2]}",
                    f"{collected[1][0]}:{collected[1][1]}-{collected[1][2]}",
                ])
                records.append(Record(None, None, None, f"R0801:{spans[0]}<->{spans[1]}",
                                      "Similar lines (R0801)"))
                # Consume every line we scanned for spans (banner + spans).
                i = j
                continue
            # Banner without enough spans → fall through to the line regex.
        m = _PYLINT_LINE_RE.match(line)
        if m:
            rule = m.group("symbol") or m.group("code")
            records.append(Record(
                m.group("file"),
                _parse_int(m.group("line")),
                _parse_int(m.group("col")),
                rule,
                m.group("msg").rstrip(),
            ))
        i += 1
    records.sort(key=_compare_records_key)
    return records


# Ruff default output: ``path:line:col: CODE  msg``.  The column may be
# absent on some rules; tolerate both shapes.
_RUFF_LINE_RE = re.compile(
    r"^(?P<file>\S+?):(?P<line>\d+):(?:(?P<col>\d+):)?\s*"
    r"(?P<code>[A-Z]\d+)\s+(?P<msg>.*?)\s*$"
)


def _parse_ruff_records(stdout: str) -> list[Record]:
    """Parse ruff *text* output into sorted records (default compact renderer).

    Format: ``path:line:col: CODE msg`` (col optional).
    """
    records: list[Record] = []
    for line in stdout.splitlines():
        m = _RUFF_LINE_RE.match(line.rstrip())
        if not m:
            continue
        records.append(Record(
            m.group("file"),
            _parse_int(m.group("line")),
            _parse_int(m.group("col")) if m.group("col") else None,
            m.group("code"),
            m.group("msg").rstrip(),
        ))
    records.sort(key=_compare_records_key)
    return records


# Mypy: ``path:line: error: msg  [code]`` (note: code optional, colon-space
# separates severity from message).  The error/note severity is dropped —
# only violations carry a code, notes are skipped.
_MYPY_LINE_RE = re.compile(
    r"^(?P<file>\S+?):(?P<line>\d+): (?P<sev>error|note): (?P<msg>.*?)"
    r"(?:\s+\[(?P<code>[^\]]+)\])?\s*$"
)


def _parse_mypy_records(stdout: str) -> list[Record]:
    """Parse mypy stdout into sorted records.  Lines without a code are skipped."""
    records: list[Record] = []
    for line in stdout.splitlines():
        m = _MYPY_LINE_RE.match(line.rstrip())
        if not m or not m.group("code") or m.group("sev") != "error":
            continue
        records.append(Record(
            m.group("file"),
            _parse_int(m.group("line")),
            None,
            m.group("code"),
            m.group("msg").rstrip(),
        ))
    records.sort(key=_compare_records_key)
    return records


# Ty concise: ``path:line:col: error_code msg`` OR the multiline-renderer
# ``error[code]: msg\n   --> path:line:col`` shape.  Tolerate both by
# anchoring on the ``--> path:line:col`` marker when present.
_TY_LONG_RE = re.compile(
    r"^error\[(?P<code>[^\]]+)\]:\s*(?P<msg>.*?)\s*$"
)
_TY_ARROW_RE = re.compile(
    r"^\s*-->\s*(?P<file>\S+?):(?P<line>\d+):(?P<col>\d+)"
)
_TY_CONCISE_RE = re.compile(
    r"^(?P<file>\S+?):(?P<line>\d+):(?P<col>\d+):\s+(?P<code>\S+)\s+(?P<msg>.*?)\s*$"
)


def _parse_ty_records(stdout: str) -> list[Record]:
    """Parse ty ``--output-format concise`` AND the default multiline output.

    The concise form is ``path:line:col: code msg`` (one record per line).
    The default multiline form is ``error[code]: msg`` followed by
    ``--> path:line:col`` — the arrow carries the position.
    """
    records: list[Record] = []
    pending_code: str | None = None
    pending_msg: str | None = None
    for line in stdout.splitlines():
        line = line.rstrip()
        concise = _TY_CONCISE_RE.match(line)
        if concise:
            records.append(Record(
                concise.group("file"),
                _parse_int(concise.group("line")),
                _parse_int(concise.group("col")),
                concise.group("code"),
                concise.group("msg").rstrip(),
            ))
            continue
        long_form = _TY_LONG_RE.match(line)
        if long_form:
            pending_code = long_form.group("code")
            pending_msg = long_form.group("msg").rstrip()
            continue
        arrow = _TY_ARROW_RE.match(line)
        if arrow and pending_code is not None:
            records.append(Record(
                arrow.group("file"),
                _parse_int(arrow.group("line")),
                _parse_int(arrow.group("col")),
                pending_code,
                pending_msg or "",
            ))
            pending_code = None
            pending_msg = None
    records.sort(key=_compare_records_key)
    return records


# Yamllint parsable: ``file:line:col:rule_id:message``.  The message may
# itself contain colons so split on the FIRST four colons; tolerate an
# optional space between ``col:`` and ``rule_id`` (some yamllint configs
# emit ``file:line:col: rule: msg`` with a space before the rule id).
_YAMLLINT_RE = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s*(?P<rule>[^:\s]+):(?P<msg>.*)$"
)


def _parse_yamllint_records(stdout: str) -> list[Record]:
    """Parse yamllint ``-f parsable`` output into sorted records.

    Format: ``file:line:col:rule_id:message`` (tolerant of an optional
    space before the rule id).  Message is whitespace-stripped both ends
    so a literal-space-after-colon in yamllint's renderer does not leak
    into the stored record.
    """
    records: list[Record] = []
    for line in stdout.splitlines():
        m = _YAMLLINT_RE.match(line.rstrip())
        if not m:
            continue
        records.append(Record(
            m.group("file"),
            _parse_int(m.group("line")),
            _parse_int(m.group("col")),
            m.group("rule"),
            m.group("msg").strip(),
        ))
    records.sort(key=_compare_records_key)
    return records


# Rumdl: prefers ``file:line:col: [RULE] msg``.  The success banner +
# ``Issues: Found N ...`` footer lines are skipped (no match).
_RUMDL_LINE_RE = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s+\[(?P<rule>[^\]]+)\]\s+(?P<msg>.*?)\s*$"
)


def _parse_rumdl_records(stdout: str) -> list[Record]:
    """Parse rumdl check text output into sorted records.

    Multiline ``Found N issues in M files (XXXms)`` footer is filtered out.
    Note: rumdl JSON output is consumed directly in
    :mod:`python_setup_lint.runner.baseline` (it already emits
    ``diagnostics``); this parser handles the legacy text path only.
    """
    records: list[Record] = []
    for line in stdout.splitlines():
        m = _RUMDL_LINE_RE.match(line.rstrip())
        if not m:
            continue
        records.append(Record(
            m.group("file"),
            _parse_int(m.group("line")),
            _parse_int(m.group("col")),
            m.group("rule"),
            m.group("msg").rstrip(),
        ))
    records.sort(key=_compare_records_key)
    return records


# Pyright --outputjson: ``{generalDiagnostics:[{file,rule,message,range:{start:{line,col}}}]}``.
# Pyright lines are 0-indexed; convert to 1-indexed so the sort key is
# consistent with all the other tools (which are 1-indexed).
def _parse_pyright_records(data: Any) -> list[Record]:
    """Parse the pre-loaded pyright ``--outputjson`` dict into sorted records.

    ``data`` is the JSON object (already ``json.loads``-ed by the caller).
    Returns ``[]`` when the shape is unexpected (defensive — the caller
    falls back to the legacy set-diff path if the records list is empty
    AND the source stdout was non-empty).
    """
    if not isinstance(data, dict):
        return []
    diags = data.get("generalDiagnostics", [])
    if not isinstance(diags, list):
        return []
    records: list[Record] = []
    for d in diags:
        if not isinstance(d, dict):
            continue
        rule = d.get("rule")
        if not isinstance(rule, str):
            continue
        file = d.get("file")
        rng = d.get("range") or {}
        start = rng.get("start") or {} if isinstance(rng, dict) else {}
        line_raw = start.get("line") if isinstance(start, dict) else None
        col_raw = start.get("character") if isinstance(start, dict) else None
        line_int = _parse_int(str(line_raw)) if line_raw is not None else None
        col_int = _parse_int(str(col_raw)) if col_raw is not None else None
        records.append(Record(
            file if isinstance(file, str) else None,
            (line_int + 1) if line_int is not None else None,
            (col_int + 1) if col_int is not None else None,
            rule,
            (d.get("message") or "").rstrip() if isinstance(d.get("message"), str) else "",
        ))
    records.sort(key=_compare_records_key)
    return records


# Dispatch table: built-in tool name → record parser.  JSON-native tools
# (pyright, rumdl when it emits JSON) are NOT in this table — they go
# through the ``diagnostics`` path in ``baseline.py`` and convert to
# records via :func:`_parse_pyright_records` there.  Tools absent here
# keep the legacy rstrip-set behaviour (a ``decisions.md`` note records
# each such fallback).
_RECORD_PARSERS: dict[str, Callable[..., list[Record]]] = {
    "ruff check": _parse_ruff_records,
    "mypy": _parse_mypy_records,
    "pylint": _parse_pylint_records,
    "ty check": _parse_ty_records,
    "yamllint": _parse_yamllint_records,
    "rumdl check": _parse_rumdl_records,
}


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
