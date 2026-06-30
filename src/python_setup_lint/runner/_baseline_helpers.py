"""Helper functions for baseline comparison (extracted to reduce module size)."""

from __future__ import annotations

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


def _record_to_dict(rec: Record) -> dict[str, object]:
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


def _records_to_dicts(records: list[Record]) -> list[dict[str, object]]:
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
    d = diag
    d.pop("time", None)  # type: ignore[arg-type]  # dict value is object; pop expects _VT  # ty:ignore[no-matching-overload]
    d.pop("version", None)  # type: ignore[arg-type]  # dict value is object; pop expects _VT  # ty:ignore[no-matching-overload]
    d.pop("timeInSec", None)  # type: ignore[arg-type]  # dict value is object; pop expects _VT  # ty:ignore[no-matching-overload]
    summary = d.get("summary")
    if isinstance(summary, dict):
        summary.pop("timeInSec", None)  # type: ignore[arg-type]  # dict value is object; pop expects _VT  # ty:ignore[no-matching-overload]
    # pyright verify-types embeds absolute machine paths in typeCompleteness
    # that differ across checkouts — strip them to avoid false drift.
    tc = d.get("typeCompleteness")
    if isinstance(tc, dict):
        tc.pop("moduleRootDirectory", None)  # type: ignore[arg-type]  # dict value is object; pop expects _VT  # ty:ignore[no-matching-overload]
        tc.pop("packageRootDirectory", None)  # type: ignore[arg-type]  # dict value is object; pop expects _VT  # ty:ignore[no-matching-overload]
        tc.pop("pyTypedPath", None)  # type: ignore[arg-type]  # dict value is object; pop expects _VT  # ty:ignore[no-matching-overload]


def _diag_error_count(d: object) -> int:
    if isinstance(d, dict):
        s = d.get("summary", {})
        if isinstance(s, dict):
            return int(s.get("errorCount", 0)) + int(s.get("warningCount", 0))  # type: ignore[arg-type]  # dict value is object; int() expects str | Buffer | SupportsInt  # ty:ignore[invalid-argument-type]
    return 0
