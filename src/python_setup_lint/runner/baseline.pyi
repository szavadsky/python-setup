"""Stub for :mod:`python_setup_lint.runner.baseline`.

Drift-resistant baseline capture + diff with silent shrinkage (T2).
Additions ONLY are flagged as regressions; removals rewrite the baseline
in-place.  New entries use the schema-v2 ``records`` form (order-tolerant
sorted record list, multiset-accurate).  Legacy ``output``-string entries
load on read and are upgraded in-memory when a per-tool records parser
exists; tools without a parser keep the legacy rstrip-set path (recorded
in ``decisions.md`` per fallback).
"""

from pathlib import Path
from typing import Any

from .parsers import Record
from .types import LintResult

def _compare_sorted(a: list[Record], b: list[Record]) -> tuple[list[Record], list[Record]]:
    """Walk-merge two pre-sorted record lists → ``(added, removed)``.

    Both inputs MUST be sorted by ``_compare_records_key``.  Multiset-aware:
    a duplicate record on one side consumes a matching record on the other
    before being reported.  Order-tolerant by construction (sort key
    discards order).  ``added`` = records in *a* not in *b* (regressions);
    ``removed`` = records in *b* not in *a* (baseline silently shrinks).
    """

def _capture_baseline(results: list[LintResult]) -> list[dict[str, Any]]:
    """Capture structured baseline data from tool results.

    Each entry is the schema-v2 ``records`` form when a per-tool record
    parser exists; otherwise the legacy ``output`` string (rumdl timing
    collapsed to ``(XXXms)``).  JSON-native tools (pyright,
    rumdl-when-JSON) use the ``diagnostics`` slot with volatile fields
    (``time``, ``version``, ``summary.timeInSec``) stripped.

    Args:
        results: :class:`LintResult` list from one ``run_lint`` invocation.
    """

def _diff_baseline(current: list[LintResult], baseline_path: Path) -> list[str]:
    """Compare current results against saved baseline.

    Returns empty list when current output fully matches baseline.  Each
    returned string describes a specific regression (additions only).
    Removals (shrinkage) are silently auto-recorded by rewriting the
    baseline in-place; if the write fails the function returns a single
    ``"Cannot write baseline: ..."`` message.

    Schema handling: ``schema:"v2"`` entries → record walk-merge; legacy
    ``output``-string entries → parsed into records on read when a parser
    exists (in-memory upgrade), else the legacy rstrip-set path with the
    tool recorded in the per-run fallback set (T2 D3 → ``decisions.md``).
    Exit-code ``0 → nonzero`` flagged as a regression; ``nonzero → 0``
    silently auto-records.

    Args:
        current: :class:`LintResult` list from current run.
        baseline_path: Path to a JSON file previously written by
            :func:`_capture_baseline`.
    """
