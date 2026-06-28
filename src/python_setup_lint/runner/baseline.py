"""Drift-resistant baseline capture + diff with silent shrinkage (T2)."""
# consolidated import with pylint disable for mypy re-export
from __future__ import annotations

import json
import re
from collections.abc import Callable  # TYPE_CHECKING-only import; not available at runtime
from typing import TYPE_CHECKING

import beartype

from ._baseline_helpers import (  # pylint: disable=useless-import-alias  # as-alias needed for mypy strict re-export
    _compare_sorted as _compare_sorted,
)
from ._baseline_helpers import (
    _diag_error_count as _diag_error_count,
)
from ._baseline_helpers import (
    _dicts_to_records as _dicts_to_records,
)
from ._baseline_helpers import (
    _records_to_dicts as _records_to_dicts,
)
from ._baseline_helpers import (
    _strip_pyright_volatile as _strip_pyright_volatile,
)
from ._record_types import Record, _records_unchanged
from .parsers import _RECORD_PARSERS
from .types import LintResult  # TYPE_CHECKING-only import; not available at runtime

if TYPE_CHECKING:
    from pathlib import Path

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
def peek_fallback_tools() -> frozenset[str]:  # pylint: disable=missing-beartype  # trivial getter; beartype overhead unnecessary
    return frozenset(_FALLBACK_TOOLS)


def _normalise_rumdl_timing(text: str) -> str:
    return re.sub(r"\(\d+ms\)", "(XXXms)", text)

def _normalise_pyright_verifytypes_output(text: str) -> str:
    result = re.sub(r'"time":\s*"?\d+"?', "", text)
    return re.sub(r'"timeInSec":\s*[0-9.]+', "", result)


def _try_rumdl_json(stdout: str | None) -> dict[str, object] | list[dict[str, object]] | None:
    if not stdout:
        return None
    try:
        diag = json.loads(stdout)
    except json.JSONDecodeError, ValueError:  # pylint: disable=W9740  # best-effort rumdl JSON parse fallback; logging would noise unavoidable parse degrade
        return None
    if isinstance(diag, (dict, list)):
        return diag
    return None


def _capture_records_or_output(r: LintResult, entry: dict[str, object]) -> dict[str, object]:
    parser = _RECORD_PARSERS.get(r.tool_name)
    if parser is not None:
        records = parser(r.stdout or "")
        entry["schema"] = _SCHEMA_V2
        entry["records"] = _records_to_dicts(records)
        if not records and (r.stdout or "").strip():
            if r.tool_name == "rumdl check":
                entry["output"] = _normalise_rumdl_timing(r.stdout or "")
            else:
                entry["output"] = r.stdout
            entry.pop("records", None)
            entry.pop("schema", None)
        return entry
    if r.tool_name == "pyright verify types":
        entry["output"] = _normalise_pyright_verifytypes_output(r.stdout or "")
    elif r.tool_name == "rumdl check":
        entry["output"] = _normalise_rumdl_timing(r.stdout or "")
    else:
        entry["output"] = r.stdout
    return entry


def _capture_one(r: LintResult) -> dict[str, object]:
    entry: dict[str, object] = {"tool": r.tool_name, "exit_code": r.exit_code}
    # JSON-native tools: pyright + rumdl-when-JSON.
    if r.tool_name in _JSON_DIAGNOSTIC_TOOLS and r.stdout:
        try:
            diag = json.loads(r.stdout)
        except json.JSONDecodeError, ValueError:  # pylint: disable=W9740  # best-effort JSON diagnostics parse fallback; logging would noise unavoidable parse degrade
            diag = None
        if isinstance(diag, dict):
            _strip_pyright_volatile(diag)
            entry["diagnostics"] = diag
            return entry
    # rumdl: try JSON first, fall through to records/output.
    rumdl_json = _try_rumdl_json(r.stdout) if r.tool_name == "rumdl check" else None
    if rumdl_json is not None:
        entry["diagnostics"] = rumdl_json
        return entry
    # Records parser or legacy output.
    return _capture_records_or_output(r, entry)


@beartype.beartype
def _capture_baseline(results: list[LintResult]) -> list[dict[str, object]]:
    return [_capture_one(r) for r in results]


def _remove_stale_tools(
    saved: list[dict[str, object]],
    saved_map: dict[str, dict[str, object]],
    current_tool_names: set[str],
) -> bool:
    modified = False
    for tool_name in list(saved_map.keys()):
        if tool_name not in current_tool_names:
            for entry in saved[:]:
                if entry.get("tool") == tool_name:
                    saved.remove(entry)
                    modified = True
            del saved_map[tool_name]
    return modified


def _write_baseline_if_modified(
    saved: list[dict[str, object]],
    baseline_path: Path,
    baseline_modified: bool,
) -> list[str] | None:
    if not baseline_modified:
        return None
    try:
        with open(baseline_path, "w") as f:
            json.dump(saved, f, indent=2, sort_keys=True)
    except OSError as exc:  # pylint: disable=W9740  # best-effort baseline write fallback; logging would noise unavoidable IO degrade
        return [f"Cannot write baseline: {exc}"]
    return None


def _build_saved_map(saved: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    saved_map: dict[str, dict[str, object]] = {}
    for entry in saved:
        tool_name = entry.get("tool", "")
        if isinstance(tool_name, str):
            saved_map[tool_name] = entry
    return saved_map


def _diff_baseline(
    current: list[LintResult],
    baseline_path: Path,
) -> list[str]:
    if not baseline_path.exists():
        return [f"Baseline file not found: {baseline_path}"]

    try:
        with open(baseline_path) as f:
            raw: list[dict[str, object]] = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:  # pylint: disable=W9740  # best-effort baseline read fallback; logging would noise unavoidable parse/IO degrade
        return [f"Cannot read baseline: {exc}"]
    saved: list[dict[str, object]] = raw

    _FALLBACK_TOOLS.clear()

    for entry in saved:
        _strip_pyright_volatile(entry.get("diagnostics"))

    saved_map = _build_saved_map(saved)
    violations: list[str] = []
    baseline_modified = False
    current_tool_names = {r.tool_name for r in current}

    baseline_modified = (
        _remove_stale_tools(saved, saved_map, current_tool_names) or baseline_modified
    )

    for r in current:
        saved_entry = saved_map.get(r.tool_name)
        if saved_entry is None:
            violations.append(f"[{r.tool_name}] New tool result — no baseline entry")
            continue

        v, m = _compare_one_tool(r, saved_entry)
        violations.extend(v)
        if m:
            baseline_modified = True

    write_violations = _write_baseline_if_modified(
        saved, baseline_path, baseline_modified
    )
    if write_violations is not None:
        return write_violations

    return violations


def _check_exit_code(
    r: LintResult, saved_entry: dict[str, object]
) -> tuple[list[str], bool | None]:
    saved_rc = saved_entry.get("exit_code", -1)
    if r.exit_code == saved_rc:
        return [], None
    if r.exit_code == 0 and saved_rc != 0:
        saved_entry["exit_code"] = 0
        saved_entry.pop("output", None)
        saved_entry.pop("diagnostics", None)
        saved_entry.pop("records", None)
        saved_entry.pop("schema", None)
        return [], True
    if saved_rc == 0 and r.exit_code != 0:
        return [f"[{r.tool_name}] Exit code changed: 0 → {r.exit_code}"], False
    return [], None


def _compare_one_tool(
    r: LintResult,
    saved_entry: dict[str, object],
) -> tuple[list[str], bool]:
    violations: list[str] = []

    # ── Exit code check ──────────────────────────────────────
    v, m = _check_exit_code(r, saved_entry)
    violations.extend(v)
    if m is not None:
        return violations, m

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
    saved_entry: dict[str, object],
    saved_diag: object,
) -> tuple[list[str], bool]:
    violations: list[str] = []
    try:
        current_diag = json.loads(r.stdout) if r.stdout else None
    except json.JSONDecodeError, ValueError:  # pylint: disable=W9740  # best-effort diagnostics JSON parse fallback; logging would noise unavoidable parse degrade
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


def _legacy_to_records(
    saved_output: str, parser: Callable[[str], list[Record]]
) -> list[Record]:
    return parser(saved_output)


def _compare_record_sets(
    current_records: list[Record],
    saved_records: list[Record],
    saved_entry: dict[str, object],
    r: LintResult,
) -> tuple[list[str], bool]:
    violations: list[str] = []
    baseline_modified = False
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


def _resolve_saved_records(
    saved_entry: dict[str, object],
    parser: Callable[[str], list[Record]] | None,
    tool_name: str,
) -> tuple[list[Record], bool]:
    saved_schema = saved_entry.get("schema")
    if saved_schema == _SCHEMA_V2:
        return _dicts_to_records(saved_entry.get("records")), False
    if parser is not None and isinstance(saved_entry.get("output"), str):
        saved_output = str(saved_entry["output"])
        saved_records = _legacy_to_records(saved_output, parser)
        if saved_output.strip():
            nonblank_saved_lines = sum(
                1 for ln in saved_output.splitlines() if ln.strip()
            )
            partial_parse = saved_records and len(saved_records) < nonblank_saved_lines
            if not saved_records or partial_parse:
                _FALLBACK_TOOLS.add(tool_name)
                return saved_records, True
        return saved_records, False
    if parser is None:
        _FALLBACK_TOOLS.add(tool_name)
    return [], True


def _compare_records_path(
    r: LintResult,
    saved_entry: dict[str, object],
) -> tuple[list[str], bool]:
    violations: list[str] = []
    baseline_modified = False

    parser = _RECORD_PARSERS.get(r.tool_name)
    current_records: list[Record] = parser(r.stdout or "") if parser is not None else []

    saved_records, legacy_save_fallback = _resolve_saved_records(
        saved_entry, parser, r.tool_name
    )

    if legacy_save_fallback:
        if _diff_legacy_output(r, saved_entry):
            baseline_modified = True
        if _legacy_has_additions(r, saved_entry):
            violations.append(
                f"[{r.tool_name}] Output changed (new/different violations)"
            )
        return violations, baseline_modified

    v, m = _compare_record_sets(current_records, saved_records, saved_entry, r)
    violations.extend(v)
    if m:
        baseline_modified = True
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


def _normalise_legacy_output(text: str, tool_name: str) -> str:
    if tool_name == "ruff check":
        return "\n".join(sorted(text.splitlines()))
    if tool_name == "rumdl check":
        return _normalise_rumdl_timing(text)
    if tool_name == "pylint":
        return _pylint_inventory(text)
    if tool_name == "pyright verify types":
        return _normalise_pyright_verifytypes_output(text)
    return text


def _legacy_current_output(r: LintResult) -> str:
    return _normalise_legacy_output(r.stdout or "", r.tool_name)


def _legacy_saved_output(saved_entry: dict[str, object], tool_name: str) -> str:
    return _normalise_legacy_output(str(saved_entry.get("output") or ""), tool_name)


def _diff_legacy_output(r: LintResult, saved_entry: dict[str, object]) -> bool:
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


def _legacy_has_additions(r: LintResult, saved_entry: dict[str, object]) -> bool:
    saved_norm = _legacy_saved_output(saved_entry, r.tool_name)
    current_norm = _legacy_current_output(r)
    saved_lines = {line.rstrip() for line in saved_norm.splitlines()}
    current_lines = {line.rstrip() for line in current_norm.splitlines()}
    return bool(current_lines - saved_lines)
