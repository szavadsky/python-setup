from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Record:
    file: str | None
    line: int | None
    col: int | None
    rule: str
    msg: str


def _compare_records_key(rec: Record) -> tuple[tuple[str, ...], tuple[int, ...], tuple[int, ...], str]:
    file_k: tuple[str, ...] = (rec.file,) if rec.file is not None else ("",)
    line_k: tuple[int, ...] = (rec.line,) if rec.line is not None else (-1,)
    col_k: tuple[int, ...] = (rec.col,) if rec.col is not None else (-1,)
    return (file_k, line_k, col_k, rec.rule)
