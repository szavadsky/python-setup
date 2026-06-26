"""Shared types for the runner module.

Contains :class:`Record` and related helpers used by both
:mod:`python_setup_lint.runner.parsers` and
:mod:`python_setup_lint.runner._record_parsers`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Record:
    file: str | None
    line: int | None
    col: int | None
    rule: str
    msg: str


def _compare_records_key(rec: Record) -> tuple[Any, Any, Any, str]:
    file_k: tuple[Any, ...] = () if rec.file is None else (rec.file,)
    line_k: tuple[Any, ...] = () if rec.line is None else (rec.line,)
    col_k: tuple[Any, ...] = () if rec.col is None else (rec.col,)
    return (file_k, line_k, col_k, rec.rule)


def _records_unchanged(a: list[Record], b: list[Record]) -> bool:
    return len(a) == len(b) and all(x == y for x, y in zip(a, b, strict=True))
