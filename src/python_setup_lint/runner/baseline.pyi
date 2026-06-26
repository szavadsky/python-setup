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
from collections.abc import Callable

from .parsers import Record
from .types import LintResult

def peek_fallback_tools() -> frozenset[str]:
    """Snapshot the per-run set of tools that took the legacy rstrip-set path.

    Returns a frozen copy taken at call time; subsequent
    :func:`_diff_baseline` invocations do NOT retroactively mutate a
    previously returned snapshot.  Tests / the pipeline should assert
    against this snapshot when a documented fallback is expected (T2 D1
    — the legacy mutation-only set was previously invisible).

    See :file:`decisions.md` D15 for the rationale + per-tool fallback list.
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

def _try_rumdl_json(stdout: str | None) -> dict | list | None:
    """Try to parse rumdl JSON output. Returns parsed dict/list or None."""

def _capture_records_or_output(r: LintResult, entry: dict[str, Any]) -> dict[str, Any]:
    """Decide whether to capture records or legacy output for a tool result."""
def _normalise_legacy_output(text: str, tool_name: str) -> str:
    """Normalise legacy tool output for comparison, applying tool-specific transforms."""

def _remove_stale_tools(
    saved: list[dict[str, Any]],
    saved_map: dict[str, dict[str, Any]],
    current_tool_names: set[str],
) -> bool:
    """Remove baseline entries for tools no longer in current results."""


def _write_baseline_if_modified(
    saved: list[dict[str, Any]],
    baseline_path: Path,
    baseline_modified: bool,
) -> list[str] | None:
    """Write baseline if modified. Returns violations on write error, None on success."""


def _build_saved_map(saved: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build a tool-name to entry map from the saved baseline list."""


def _check_exit_code(
    r: LintResult, saved_entry: dict[str, Any]
) -> tuple[list[str], bool | None]:
    """Check exit code changes. Returns (violations, modified|None) where None = fall through."""


def _legacy_to_records(
    saved_output: str, parser: Callable[[str], list[Record]]
) -> list[Record]:
    """Convert legacy output string to records via the given parser."""


def _compare_record_sets(
    current_records: list[Record],
    saved_records: list[Record],
    saved_entry: dict[str, Any],
    r: LintResult,
) -> tuple[list[str], bool]:
    """Compare current vs saved record sets. Returns (violations, modified)."""


def _resolve_saved_records(
    saved_entry: dict[str, Any],
    parser: Callable[[str], list[Record]] | None,
    tool_name: str,
) -> tuple[list[Record], bool]:
    """Resolve saved records from schema-v2 or legacy output. Returns (records, fallback)."""
