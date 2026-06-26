"""Stub for :mod:`python_setup_lint.runner._baseline_helpers`.

Helper functions for baseline comparison (extracted to reduce module size).
"""


from typing import Any

from ._record_types import Record

    a: list[Record], b: list[Record]
) -> tuple[list[Record], list[Record]]:
    """Walk-merge two pre-sorted record lists → ``(added, removed)``.

    Both inputs MUST be sorted by ``_compare_records_key``.  Multiset-aware:
    a duplicate record on one side consumes a matching record on the other
    before being reported.  Order-tolerant by construction (sort key
    discards order).  ``added`` = records in *a* not in *b* (regressions);
    ``removed`` = records in *b* not in *a* (baseline silently shrinks).
    """


    """Convert a Record to a plain dict for JSON serialisation."""


    """Convert a plain dict back to a Record (or None on invalid input)."""


    """Convert a list of Records to a list of plain dicts."""


    """Convert a list of plain dicts back to a sorted list of Records."""


    """Strip volatile fields (time, version, summary.timeInSec) from a pyright diagnostics dict."""


    """Count total errors + warnings from a pyright diagnostics summary."""
