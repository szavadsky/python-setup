"""Helper functions for baseline comparison (extracted to reduce module size)."""

from __future__ import annotations

from typing import Any, cast

from ._record_types import Record, _compare_records_key


def _compare_sorted(
    a: list[Record], b: list[Record]
) -> tuple[list[Record], list[Record]]:
    added: list[Record] = []
    removed: list[Record] = []
    i = j = 0
    len_a, len_b = len(a), len(b)
    while i < len_a and j < len_b:
        ra, rb = a[i], b[j]
        ka = _compare_records_key(ra)
        kb = _compare_records_key(rb)
        if ra == rb:
            # Identical multiset member → consume one on each side.
            i += 1
            j += 1
        elif (ka, ra.msg) < (kb, rb.msg):
            added.append(ra)
            i += 1
        else:
            removed.append(rb)
            j += 1
    if i < len_a:
        added.extend(a[i:])
    if j < len_b:
        removed.extend(b[j:])
    return added, removed


def _record_to_dict(rec: Record) -> dict[str, Any]:
    return {
        "file": rec.file,
        "line": rec.line,
        "col": rec.col,
        "rule": rec.rule,
        "msg": rec.msg,
    }


def _dict_to_record(d: object) -> Record | None:
    if not isinstance(d, dict):
        return None
    rule = d.get("rule")
    if not isinstance(rule, str):
        return None
    file = d.get("file")
    line = d.get("line")
    col = d.get("col")
    msg = d.get("msg")
    return Record(
        file if isinstance(file, str) else None,
        line if isinstance(line, int) else None,
        col if isinstance(col, int) else None,
        rule,
        msg if isinstance(msg, str) else "",
    )


def _records_to_dicts(records: list[Record]) -> list[dict[str, Any]]:
    return [_record_to_dict(r) for r in records]


def _dicts_to_records(payload: object) -> list[Record]:
    out: list[Record] = []
    if not isinstance(payload, list):
        return out
    for d in payload:
        rec = _dict_to_record(d)
        if rec is not None:
            out.append(rec)
    out.sort(key=_compare_records_key)
    return out


def _strip_pyright_volatile(diag: object) -> None:
    if not isinstance(diag, dict):
        return
    d = cast("dict[str, Any]", diag)
    d.pop("time", None)
    d.pop("version", None)
    summary = d.get("summary")
    if isinstance(summary, dict):
        cast("dict[str, Any]", summary).pop("timeInSec", None)


def _diag_error_count(d: object) -> int:
    if isinstance(d, dict):
        s = cast("dict[str, Any]", d).get("summary", {})
        if isinstance(s, dict):
            sd = cast("dict[str, Any]", s)
            return int(sd.get("errorCount", 0)) + int(sd.get("warningCount", 0))
    return 0
