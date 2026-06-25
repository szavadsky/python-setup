"""Drift-resistant baseline capture + diff with silent shrinkage (T2)."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, cast

import beartype

from .parsers import (
    _RECORD_PARSERS,
    Record,
    _compare_records_key,
    _records_unchanged,
)

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any

    from .types import LintResult

__all__ = ["_capture_baseline", "_compare_sorted", "_diff_baseline"]

# New schema entries carry this marker so downstream consumers (T10 regen,
# A8 drift analysis) can distinguish them from legacy ``output``-string
# entries loaded from a pre-T2 baseline.
_SCHEMA_V2 = "v2"

# Tools with JSON-native diagnostics go through the ``diagnostics`` path
# rather than the records path.  pyright always emits JSON; rumdl may emit
# JSON OR text (its JSON form is consumed as diagnostics when ``stdout``
# parses cleanly).
_JSON_DIAGNOSTIC_TOOLS: frozenset[str] = frozenset({"pyright check"})

# Tools whose stdout we currently do NOT parse into records — they keep
# the legacy rstrip-set path AND are recorded in ``decisions.md`` (D3).
# Populated lazily inside ``_diff_baseline`` per run; reset each call.
# D1: exposed read-only via :func:`peek_fallback_tools` so tests / the
# pipeline can observe WHICH tools fell back (the previous invisible
# module-level set meant a tool could silently land in fallback with no
# log line or assertion catching it).  The set is ``set[str]`` (not a
# frozenset) because :func:`_diff_baseline` mutates it in place per run;
# callers MUST treat the returned value as a snapshot (copy it before
# mutating or asserting across calls).
_FALLBACK_TOOLS: set[str] = set()


@beartype.beartype
def peek_fallback_tools() -> frozenset[str]:
    return frozenset(_FALLBACK_TOOLS)


def _compare_sorted(a: list[Record], b: list[Record]) -> tuple[list[Record], list[Record]]:
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


def _normalise_rumdl_timing(text: str) -> str:
    return re.sub(r"\(\d+ms\)", "(XXXms)", text)


def _strip_pyright_volatile(diag: object) -> None:
    if not isinstance(diag, dict):
        return
    d = cast("dict[str, Any]", diag)
    d.pop("time", None)
    d.pop("version", None)
    summary = d.get("summary")
    if isinstance(summary, dict):
        cast("dict[str, Any]", summary).pop("timeInSec", None)


def _capture_one(r: LintResult) -> dict[str, Any]:
    entry: dict[str, Any] = {"tool": r.tool_name, "exit_code": r.exit_code}
    # JSON-native tools: pyright + rumdl-when-JSON.
    if r.tool_name in _JSON_DIAGNOSTIC_TOOLS and r.stdout:
        try:
            diag = json.loads(r.stdout)
        except (json.JSONDecodeError, ValueError):
            diag = None
        if isinstance(diag, dict):
            _strip_pyright_volatile(diag)
            entry["diagnostics"] = diag
            return entry
        # JSON expected but not parseable → fall back to records/output path.
    if r.tool_name == "rumdl check" and r.stdout:
        # rumdl prefers JSON when its stdout parses cleanly.
        try:
            diag = json.loads(r.stdout)
        except (json.JSONDecodeError, ValueError):
            diag = None
        if isinstance(diag, (dict, list)):
            entry["diagnostics"] = diag
            return entry
        # Text path → records (rumdl text parser strips the footer).
    parser = _RECORD_PARSERS.get(r.tool_name)
    if parser is not None:
        records = parser(r.stdout or "")
        entry["schema"] = _SCHEMA_V2
        entry["records"] = _records_to_dicts(records)
        # When records is empty but stdout was non-empty, stash a
        # normalised ``output`` so (a) the absence of records is NOT
        # mistaken for a clean pass and (b) legacy diff fallback can
        # still compare.  Rumdl timing is collapsed here so a success
        # banner with ``(Nms)`` is byte-stable across runs.
        if not records and (r.stdout or "").strip():
            if r.tool_name == "rumdl check":
                entry["output"] = _normalise_rumdl_timing(r.stdout or "")
            else:
                entry["output"] = r.stdout
            entry.pop("records", None)
            entry.pop("schema", None)
        return entry
    # Tools without a records parser: keep the legacy ``output`` string.
    if r.tool_name == "rumdl check":
        entry["output"] = _normalise_rumdl_timing(r.stdout or "")
    else:
        entry["output"] = r.stdout
    return entry


def _capture_baseline(results: list[LintResult]) -> list[dict[str, Any]]:
    return [_capture_one(r) for r in results]


def _diag_error_count(d: object) -> int:
    if isinstance(d, dict):
        s = cast("dict[str, Any]", d).get("summary", {})
        if isinstance(s, dict):
            sd = cast("dict[str, Any]", s)
            return int(sd.get("errorCount", 0)) + int(sd.get("warningCount", 0))
    return 0


def _diff_baseline(
    current: list[LintResult],
    baseline_path: Path,
) -> list[str]:
    if not baseline_path.exists():
        return [f"Baseline file not found: {baseline_path}"]

    try:
        with open(baseline_path) as f:
            raw: list[dict[str, Any]] = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        return [f"Cannot read baseline: {exc}"]
    saved: list[dict[str, Any]] = raw

    # Per-run fallback reset (each diff invocation records its own fallbacks).
    _FALLBACK_TOOLS.clear()

    # Normalise volatile fields on saved diagnostics: strip timeInSec so
    # baseline comparison is stable across runs.
    for entry in saved:
        _strip_pyright_volatile(entry.get("diagnostics"))

    saved_map: dict[str, dict[str, Any]] = {}
    for entry in saved:
        tool_name = entry.get("tool", "")
        if isinstance(tool_name, str):
            saved_map[tool_name] = entry

    violations: list[str] = []
    baseline_modified = False
    current_tool_names = {r.tool_name for r in current}

    # Tools in saved but absent from current → shrinkage (remove from baseline).
    # Remove ALL entries with the same tool name (not just the last one),
    # preventing stale duplicate entries from leaking into the rewritten baseline.
    for tool_name in list(saved_map.keys()):
        if tool_name not in current_tool_names:
            for entry in saved[:]:
                if entry.get("tool") == tool_name:
                    saved.remove(entry)
                    baseline_modified = True
            del saved_map[tool_name]

    for r in current:
        saved_entry = saved_map.get(r.tool_name)
        if saved_entry is None:
            violations.append(f"[{r.tool_name}] New tool result — no baseline entry")
            continue

        v, m = _compare_one_tool(r, saved_entry)
        violations.extend(v)
        if m:
            baseline_modified = True

    if baseline_modified:
        # D5: wrap write in try/except OSError so an unwritable baseline
        # degrades gracefully with a violation message (matching the
        # read-path handling above), rather than crashing the pipeline.
        try:
            with open(baseline_path, "w") as f:
                json.dump(saved, f, indent=2, sort_keys=True)
        except OSError as exc:
            return [f"Cannot write baseline: {exc}"]

    return violations


def _compare_one_tool(
    r: LintResult,
    saved_entry: dict[str, Any],
) -> tuple[list[str], bool]:
    violations: list[str] = []

    # ── Exit code check ──────────────────────────────────────
    saved_rc = saved_entry.get("exit_code", -1)
    if r.exit_code != saved_rc:
        if r.exit_code == 0 and saved_rc != 0:
            # Tool now passes → pure shrinkage; clear all content slots.
            saved_entry["exit_code"] = 0
            saved_entry.pop("output", None)
            saved_entry.pop("diagnostics", None)
            saved_entry.pop("records", None)
            saved_entry.pop("schema", None)
            return violations, True
        if saved_rc == 0 and r.exit_code != 0:
            violations.append(f"[{r.tool_name}] Exit code changed: 0 → {r.exit_code}")
        # else: both non-zero but different → fall through to content compare.

    # ── Diagnostics comparison (pyright + rumdl-when-JSON) ──
    saved_diag = saved_entry.get("diagnostics")
    if saved_diag is not None:
        v, m = _compare_diagnostics(r, saved_entry, saved_diag)
        violations.extend(v)
        return violations, m

    # ── Records path (schema-v2 or legacy output → records) ─
    v, m = _compare_records_path(r, saved_entry)
    violations.extend(v)
    return violations, m


def _compare_diagnostics(
    r: LintResult,
    saved_entry: dict[str, Any],
    saved_diag: object,
) -> tuple[list[str], bool]:
    violations: list[str] = []
    try:
        current_diag = json.loads(r.stdout) if r.stdout else None
    except (json.JSONDecodeError, ValueError):
        current_diag = None

    # D4: saved has diagnostics (dict) but current stdout is
    # non-JSON → REGRESSION (the tool that used to emit JSON no
    # longer does).  Do NOT treat as shrinkage.
    if isinstance(saved_diag, dict) and current_diag is None:
        violations.append(
            f"[{r.tool_name}] Diagnostics lost: current output is not valid JSON"
        )
        return violations, False

    if isinstance(current_diag, dict):
        _strip_pyright_volatile(current_diag)
    if current_diag != saved_diag:
        saved_errors = _diag_error_count(saved_diag)
        current_errors = _diag_error_count(current_diag)
        if current_errors < saved_errors:
            saved_entry["diagnostics"] = current_diag
            return violations, True
        if current_errors > saved_errors or (
            current_errors == saved_errors and current_diag != saved_diag
        ):
            violations.append(
                f"[{r.tool_name}] Diagnostics changed (new/different violations)"
            )
    return violations, False


def _compare_records_path(
    r: LintResult,
    saved_entry: dict[str, Any],
) -> tuple[list[str], bool]:
    violations: list[str] = []
    baseline_modified = False

    parser = _RECORD_PARSERS.get(r.tool_name)
    current_records: list[Record] = parser(r.stdout or "") if parser is not None else []

    saved_schema = saved_entry.get("schema")
    saved_records: list[Record] = []
    legacy_save_fallback = False
    if saved_schema == _SCHEMA_V2:
        saved_records = _dicts_to_records(saved_entry.get("records"))
    elif parser is not None and isinstance(saved_entry.get("output"), str):
        saved_output = saved_entry["output"]
        saved_records = parser(saved_output)
        if saved_output.strip():
            nonblank_saved_lines = sum(
                1 for ln in saved_output.splitlines() if ln.strip()
            )
            partial_parse = (
                saved_records
                and len(saved_records) < nonblank_saved_lines
            )
            if not saved_records or partial_parse:
                legacy_save_fallback = True
                _FALLBACK_TOOLS.add(r.tool_name)

    if parser is None:
        _FALLBACK_TOOLS.add(r.tool_name)
        legacy_save_fallback = True

    if legacy_save_fallback:
        if _diff_legacy_output(r, saved_entry):
            baseline_modified = True
        if _legacy_has_additions(r, saved_entry):
            violations.append(
                f"[{r.tool_name}] Output changed (new/different violations)"
            )
        return violations, baseline_modified

    # ── Records walk-merge (the hot path, O(n) after sort) ──
    if _records_unchanged(saved_records, current_records):
        return violations, baseline_modified
    added, removed = _compare_sorted(current_records, saved_records)
    if removed:
        saved_entry["records"] = _records_to_dicts(current_records)
        saved_entry["schema"] = _SCHEMA_V2
        saved_entry.pop("output", None)
        baseline_modified = True
    if added:
        violations.append(f"[{r.tool_name}] Output changed (new/different violations)")

    return violations, baseline_modified


def _pylint_signature(line: str) -> str | None:
    dup = re.search(
        r"Similar lines in 2 files\s*==(\S+):\[(\d+):(\d+)\]\s*==(\S+):\[(\d+):(\d+)\]",
        line,
    )
    if dup:
        parts = sorted(
            [
                f"{dup.group(1)}:{dup.group(2)}-{dup.group(3)}",
                f"{dup.group(4)}:{dup.group(5)}-{dup.group(6)}",
            ]
        )
        return f"R0801:{parts[0]}<->{parts[1]}"
    cyc = re.search(r"Cyclic import \(([^)]+)\)", line)
    if cyc:
        return f"R0401:{cyc.group(1)}"
    msg = re.search(r"(\S+\.py:\d+:\d+:\s*[A-Z]\d+:)", line)
    if msg:
        return msg.group(1)
    return None


def _pylint_inventory(output: str) -> str:
    sigs: dict[str, int] = {}
    for line in output.splitlines():
        sig = _pylint_signature(line)
        if sig is not None:
            sigs[sig] = sigs.get(sig, 0) + 1
    return "\n".join(sorted(f"{count} {sig}" for sig, count in sigs.items()))


def _legacy_current_output(r: LintResult) -> str:
    if r.tool_name == "ruff check":
        return "\n".join(sorted((r.stdout or "").splitlines()))
    if r.tool_name == "rumdl check":
        return _normalise_rumdl_timing(r.stdout or "")
    if r.tool_name == "pylint":
        return _pylint_inventory(r.stdout or "")
    return r.stdout or ""


def _legacy_saved_output(saved_entry: dict[str, Any], tool_name: str) -> str:
    saved_output = saved_entry.get("output") or ""
    if tool_name == "ruff check":
        return "\n".join(sorted(saved_output.splitlines()))
    if tool_name == "rumdl check":
        return _normalise_rumdl_timing(saved_output)
    if tool_name == "pylint":
        return _pylint_inventory(saved_output)
    return saved_output


def _diff_legacy_output(r: LintResult, saved_entry: dict[str, Any]) -> bool:
    saved_norm = _legacy_saved_output(saved_entry, r.tool_name)
    current_norm = _legacy_current_output(r)
    if current_norm == saved_norm:
        return False
    saved_lines = {line.rstrip() for line in saved_norm.splitlines()}
    current_lines = {line.rstrip() for line in current_norm.splitlines()}
    removed_lines = saved_lines - current_lines
    if removed_lines:
        remaining = sorted(saved_lines & current_lines)
        saved_entry["output"] = "\n".join(remaining)
        return True
    return False


def _legacy_has_additions(r: LintResult, saved_entry: dict[str, Any]) -> bool:
    saved_norm = _legacy_saved_output(saved_entry, r.tool_name)
    current_norm = _legacy_current_output(r)
    saved_lines = {line.rstrip() for line in saved_norm.splitlines()}
    current_lines = {line.rstrip() for line in current_norm.splitlines()}
    return bool(current_lines - saved_lines)
