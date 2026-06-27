"""Stub for :mod:`python_setup_lint.runner._baseline_helpers`.

Helper functions for baseline comparison (extracted to reduce module size).
"""


from typing import Any

from ._record_types import Record

def _compare_sorted(
    a: list[Record], b: list[Record]
) -> tuple[list[Record], list[Record]]:
    """Walk-merge two pre-sorted record lists → ``(added, removed)``.

    Both inputs MUST be sorted by ``_compare_records_key``.  Multiset-aware:
    a duplicate record on one side consumes a matching record on the other
    before being reported.  Order-tolerant by construction (sort key
    discards order).  ``added`` = records in *a* not in *b* (regressions);
    ``removed`` = records in *b* not in *a* (baseline silently shrinks).
    """


def _record_to_dict(rec: Record) -> dict[str, Any]:
    """Convert a Record to a plain dict for JSON serialisation."""


def _dict_to_record(d: object) -> Record | None:
    """Convert a plain dict back to a Record (or None on invalid input)."""


def _records_to_dicts(records: list[Record]) -> list[dict[str, Any]]:
    """Convert a list of Records to a list of plain dicts."""


def _dicts_to_records(payload: object) -> list[Record]:
    """Convert a list of plain dicts back to a sorted list of Records."""


def _strip_pyright_volatile(diag: object) -> None:
    """Strip volatile fields (time, version, summary.timeInSec) from a pyright diagnostics dict."""


def _diag_error_count(d: object) -> int:
    """Count total errors + warnings from a pyright diagnostics summary."""