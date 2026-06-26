"""Per-tool violation-record parsers (T2 baseline diff).

Each parser converts a tool's stdout into sorted ``list[Record]`` for the
drift-resistant baseline comparison.
"""

from __future__ import annotations

import re


from ._record_types import Record, _compare_records_key


def _parse_int(text: str) -> int | None:
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


# Pylint message line: path:line:col: CODE: message (symbol)
_PYLINT_LINE_RE = re.compile(
    r"^(?P<file>\S+?):(?P<line>\d+):(?P<col>\d+):\s*"
    r"(?P<code>[A-Za-z]\d+[A-Z]?\d*): (?P<msg>.*?)"
    r"(?:\s+\((?P<symbol>[\w-]+)\))?\s*$"
)

# Pylint R0801 similar-lines span marker
_PYLINT_R0801_SPAN_RE = re.compile(r"==(?P<f>\S+?):\[(?P<l>\d+):(?P<c>\d+)\]")

# Pylint R0401 (cyclic-import)
_PYLINT_R0401_RE = re.compile(r"Cyclic import \((?P<cycle>[^)]+)\)")


def _parse_pylint_records(stdout: str) -> list[Record]:
    records: list[Record] = []
    lines = stdout.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].rstrip()
        # R0401 cyclic-import
        cyc = _PYLINT_R0401_RE.search(line)
        if cyc:
            records.append(
                Record(None, None, None, f"R0401:{cyc.group('cycle')}", line)
            )
            i += 1
            continue
        # R0801 similar-lines: gather ==file:[l:c] spans
        is_banner = "Similar lines in" in line or _PYLINT_R0801_SPAN_RE.search(line)
        if is_banner:
            collected: list[tuple[str, str, str]] = list(
                _PYLINT_R0801_SPAN_RE.findall(line)
            )
            j = i + 1
            while j < n and len(collected) < 2:
                nxt = lines[j].rstrip()
                nxt_spans = _PYLINT_R0801_SPAN_RE.findall(nxt)
                if not nxt_spans:
                    break
                collected.extend(nxt_spans)
                j += 1
            if len(collected) >= 2:
                spans = sorted(
                    [
                        f"{collected[0][0]}:{collected[0][1]}-{collected[0][2]}",
                        f"{collected[1][0]}:{collected[1][1]}-{collected[1][2]}",
                    ]
                )
                records.append(
                    Record(
                        None, None, None,
                        f"R0801:{spans[0]}<->{spans[1]}",
                        "Similar lines (R0801)",
                    )
                )
                i = j
                continue
        m = _PYLINT_LINE_RE.match(line)
        if m:
            rule = m.group("symbol") or m.group("code")
            records.append(
                Record(
                    m.group("file"),
                    _parse_int(m.group("line")),
                    _parse_int(m.group("col")),
                    rule,
                    m.group("msg").rstrip(),
                )
            )
        i += 1
    records.sort(key=_compare_records_key)
    return records


# Ruff: path:line:col: CODE  msg (col optional)
_RUFF_LINE_RE = re.compile(
    r"^(?P<file>\S+?):(?P<line>\d+):(?:(?P<col>\d+):)?\s*"
    r"(?P<code>[A-Z]\d+)\s+(?P<msg>.*?)\s*$"
)


def _parse_ruff_records(stdout: str) -> list[Record]:
    records: list[Record] = []
    for line in stdout.splitlines():
        m = _RUFF_LINE_RE.match(line.rstrip())
        if not m:
            continue
        records.append(
            Record(
                m.group("file"),
                _parse_int(m.group("line")),
                _parse_int(m.group("col")) if m.group("col") else None,
                m.group("code"),
                m.group("msg").rstrip(),
            )
        )
    records.sort(key=_compare_records_key)
    return records


# Mypy: path:line: error: msg  [code]
_MYPY_LINE_RE = re.compile(
    r"^(?P<file>\S+?):(?P<line>\d+): (?P<sev>error|note): (?P<msg>.*?)"
    r"(?:\s+\[(?P<code>[^\]]+)\])?\s*$"
)


def _parse_mypy_records(stdout: str) -> list[Record]:
    records: list[Record] = []
    for line in stdout.splitlines():
        m = _MYPY_LINE_RE.match(line.rstrip())
        if not m or not m.group("code") or m.group("sev") != "error":
            continue
        records.append(
            Record(
                m.group("file"),
                _parse_int(m.group("line")),
                None,
                m.group("code"),
                m.group("msg").rstrip(),
            )
        )
    records.sort(key=_compare_records_key)
    return records


# Ty: path:line:col: error_code msg OR error[code]: msg / --> path:line:col
_TY_LONG_RE = re.compile(r"^error\[(?P<code>[^\]]+)\]:\s*(?P<msg>.*?)\s*$")
_TY_ARROW_RE = re.compile(r"^\s*-->\s*(?P<file>\S+?):(?P<line>\d+):(?P<col>\d+)")
_TY_CONCISE_RE = re.compile(
    r"^(?P<file>\S+?):(?P<line>\d+):(?P<col>\d+):\s+(?P<code>\S+)\s+(?P<msg>.*?)\s*$"
)


def _parse_ty_records(stdout: str) -> list[Record]:
    records: list[Record] = []
    pending_code: str | None = None
    pending_msg: str | None = None
    for line in stdout.splitlines():
        line = line.rstrip()
        concise = _TY_CONCISE_RE.match(line)
        if concise:
            records.append(
                Record(
                    concise.group("file"),
                    _parse_int(concise.group("line")),
                    _parse_int(concise.group("col")),
                    concise.group("code"),
                    concise.group("msg").rstrip(),
                )
            )
            continue
        long_form = _TY_LONG_RE.match(line)
        if long_form:
            pending_code = long_form.group("code")
            pending_msg = long_form.group("msg").rstrip()
            continue
        arrow = _TY_ARROW_RE.match(line)
        if arrow and pending_code is not None:
            records.append(
                Record(
                    arrow.group("file"),
                    _parse_int(arrow.group("line")),
                    _parse_int(arrow.group("col")),
                    pending_code,
                    pending_msg or "",
                )
            )
            pending_code = None
            pending_msg = None
    records.sort(key=_compare_records_key)
    return records


# Yamllint: file:line:col:rule_id:message
_YAMLLINT_RE = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s*(?P<rule>[^:\s]+):(?P<msg>.*)$"
)


def _parse_yamllint_records(stdout: str) -> list[Record]:
    records: list[Record] = []
    for line in stdout.splitlines():
        m = _YAMLLINT_RE.match(line.rstrip())
        if not m:
            continue
        records.append(
            Record(
                m.group("file"),
                _parse_int(m.group("line")),
                _parse_int(m.group("col")),
                m.group("rule"),
                m.group("msg").strip(),
            )
        )
    records.sort(key=_compare_records_key)
    return records


# Rumdl: file:line:col: [RULE] msg
_RUMDL_LINE_RE = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s+\[(?P<rule>[^\]]+)\]\s+(?P<msg>.*?)\s*$"
)


def _parse_rumdl_records(stdout: str) -> list[Record]:
    records: list[Record] = []
    for line in stdout.splitlines():
        m = _RUMDL_LINE_RE.match(line.rstrip())
        if not m:
            continue
        records.append(
            Record(
                m.group("file"),
                _parse_int(m.group("line")),
                _parse_int(m.group("col")),
                m.group("rule"),
                m.group("msg").rstrip(),
            )
        )
    records.sort(key=_compare_records_key)
    return records


# Pyright --outputjson: {generalDiagnostics:[{file,rule,message,range:{start:{line,col}}}]}
# Pyright lines are 0-indexed; convert to 1-indexed.
def _parse_pyright_records(data: object) -> list[Record]:
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
        records.append(
            Record(
                file if isinstance(file, str) else None,
                (line_int + 1) if line_int is not None else None,
                (col_int + 1) if col_int is not None else None,
                rule,
                (d.get("message") or "").rstrip()
                if isinstance(d.get("message"), str)
                else "",
            )
        )
    records.sort(key=_compare_records_key)
    return records
