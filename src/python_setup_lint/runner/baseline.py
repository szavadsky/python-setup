"""Baseline capture + diff with silent shrinkage auto-record (T0 / D9).

``_capture_baseline`` snapshots a run's results as JSON.  ``_diff_baseline``
compares the current run against a saved baseline and rewrites the baseline
in-place when output shrinks — additions ONLY are flagged as regressions
(ANALYSIS-1 / decisions.md D9 / user override).  Pylint counts are folded
via :func:`_pylint_inventory` so a count change on the SAME signature is
detected (set-diff alone would collapse it).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .types import LintResult

__all__ = ["_capture_baseline", "_diff_baseline"]


def _capture_baseline(results: list[LintResult]) -> list[dict[str, Any]]:
    """Capture structured baseline data from tool results.

    Each entry contains the tool name, exit code, and one of:
    - ``output`` (raw stdout) for non-JSON tools
    - ``diagnostics`` (parsed JSON) for pyright and rumdl check.

    Ruff output is line-sorted to make the baseline stable across runs.
    Rumdl success output includes timing that changes per run — stripped to
    ``(XXXms)``.
    """
    baseline: list[dict[str, Any]] = []
    for r in results:
        entry: dict[str, Any] = {
            "tool": r.tool_name,
            "exit_code": r.exit_code,
        }
        if r.tool_name in ("pyright check", "pyright verify types") and r.stdout:
            try:
                diag = json.loads(r.stdout)
                if isinstance(diag, dict):
                    diag.pop("time", None)
                    diag.pop("version", None)
                    summary = diag.get("summary")
                    if isinstance(summary, dict):
                        summary.pop("timeInSec", None)
                entry["diagnostics"] = diag
            except json.JSONDecodeError, ValueError:
                entry["output"] = r.stdout
        elif r.tool_name == "rumdl check" and r.stdout:
            try:
                entry["diagnostics"] = json.loads(r.stdout)
            except json.JSONDecodeError, ValueError:
                entry["output"] = re.sub(r"\(\d+ms\)", "(XXXms)", r.stdout)
        elif r.tool_name == "ruff check" and r.stdout:
            # Sort ruff violations to make baseline stable across runs
            entry["output"] = "\n".join(sorted(r.stdout.splitlines()))
        else:
            entry["output"] = r.stdout
        baseline.append(entry)
    return baseline


def _diff_baseline(
    current: list[LintResult],
    baseline_path: Path,
) -> list[str]:
    """Compare current results against saved baseline.

    Returns a list of human-readable violation descriptions for any
    NEW or CHANGED issues (additions only).  Removals (shrinkage) are
    silently auto-recorded by rewriting the baseline in-place.

    .. note::

        Set-diff on output lines collapses duplicate counts; a count
        increase on the SAME signature is not flagged.  Pylint uses
        ``_pylint_inventory`` to fold counts before set-diff, so pylint
        count changes are detected.

    Args:
        current: :class:`LintResult` list from current run.
        baseline_path: Path to a JSON file previously written by
            :func:`_capture_baseline`.
    """
    if not baseline_path.exists():
        return [f"Baseline file not found: {baseline_path}"]

    try:
        with open(baseline_path) as f:
            raw: list[dict[str, Any]] = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        return [f"Cannot read baseline: {exc}"]
    saved: list[dict[str, Any]] = raw

    # Normalise saved diagnostics: strip volatile fields (timeInSec) that
    # change between runs so baseline comparison is stable.
    for entry in saved:
        saved_diag = entry.get("diagnostics")
        if isinstance(saved_diag, dict):
            saved_summary = saved_diag.get("summary")
            if isinstance(saved_summary, dict):
                saved_summary.pop("timeInSec", None)

    saved_map: dict[str, dict[str, Any]] = {}
    for entry in saved:
        tool_name = entry.get("tool", "")
        if isinstance(tool_name, str):
            saved_map[tool_name] = entry

    violations: list[str] = []
    baseline_modified = False
    current_tool_names = {r.tool_name for r in current}

    # Tools in saved but absent from current → shrinkage (remove from baseline)
    # Remove ALL entries with the same tool name (not just the last one),
    # preventing stale duplicate entries from leaking into the rewritten baseline.
    for tool_name in list(saved_map.keys()):
        if tool_name not in current_tool_names:
            for entry in saved[:]:
                if entry.get("tool") == tool_name:
                    saved.remove(entry)
                    baseline_modified = True
            del saved_map[tool_name]

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

    for r in current:
        saved_entry = saved_map.get(r.tool_name)
        if saved_entry is None:
            violations.append(f"[{r.tool_name}] New tool result — no baseline entry")
            continue

        # ── Exit code check ──────────────────────────────────────
        saved_rc = saved_entry.get("exit_code", -1)
        if r.exit_code != saved_rc:
            if r.exit_code == 0 and saved_rc != 0:
                # Tool now passes → pure shrinkage
                saved_entry["exit_code"] = 0
                saved_entry.pop("output", None)
                saved_entry.pop("diagnostics", None)
                baseline_modified = True
                continue
            if saved_rc == 0 and r.exit_code != 0:
                violations.append(f"[{r.tool_name}] Exit code changed: 0 → {r.exit_code}")
            # else: both non-zero but different → fall through to output comparison

        # ── Diagnostics comparison (pyright) ────────────────────
        saved_diag = saved_entry.get("diagnostics")
        if saved_diag is not None:
            try:
                current_diag = json.loads(r.stdout) if r.stdout else None
            except json.JSONDecodeError, ValueError:
                current_diag = None

            # D4: When saved has diagnostics (dict) but current stdout is
            # non-JSON (current_diag is None), treat as a REGRESSION — the
            # tool that used to emit JSON no longer does.  Do NOT treat as
            # shrinkage.
            if isinstance(saved_diag, dict) and current_diag is None:
                violations.append(f"[{r.tool_name}] Diagnostics lost: current output is not valid JSON")
                continue

            if isinstance(current_diag, dict):
                current_diag.pop("time", None)
                current_diag.pop("version", None)
                current_summary = current_diag.get("summary")
                if isinstance(current_summary, dict):
                    current_summary.pop("timeInSec", None)
            if current_diag != saved_diag:

                def _diag_error_count(d: Any) -> int:
                    if isinstance(d, dict):
                        s = d.get("summary", {})
                        if isinstance(s, dict):
                            return s.get("errorCount", 0) + s.get("warningCount", 0)
                    return 0

                saved_errors = _diag_error_count(saved_diag)
                current_errors = _diag_error_count(current_diag)
                if current_errors < saved_errors:
                    # Shrinkage: update baseline
                    saved_entry["diagnostics"] = current_diag
                    baseline_modified = True
                if current_errors > saved_errors:
                    violations.append(f"[{r.tool_name}] Diagnostics changed (new/different violations)")
                if current_errors == saved_errors and current_diag != saved_diag:
                    violations.append(f"[{r.tool_name}] Diagnostics changed (new/different violations)")
            continue

        # ── Output comparison ────────────────────────────────────
        saved_output = saved_entry.get("output") or ""

        # Normalise both outputs using the same per-tool logic
        if r.tool_name == "ruff check":
            current_output = "\n".join(sorted((r.stdout or "").splitlines()))
            saved_output_norm = "\n".join(sorted(saved_output.splitlines()))
        elif r.tool_name == "rumdl check":
            current_output = re.sub(r"\(\d+ms\)", "(XXXms)", r.stdout or "")
            saved_output_norm = re.sub(r"\(\d+ms\)", "(XXXms)", saved_output)
        elif r.tool_name == "pylint":
            current_output = _pylint_inventory(r.stdout or "")
            saved_output_norm = _pylint_inventory(saved_output)
        else:
            current_output = r.stdout or ""
            saved_output_norm = saved_output

        if current_output == saved_output_norm:
            continue

        # Line-by-line set diff to distinguish add vs remove
        # D6: rstrip each line so trailing-whitespace-only differences are
        # not flagged as regressions.
        saved_lines = {l.rstrip() for l in saved_output_norm.splitlines()}
        current_lines = {l.rstrip() for l in current_output.splitlines()}
        removed_lines = saved_lines - current_lines
        added_lines = current_lines - saved_lines

        if removed_lines:
            # Shrinkage: update baseline entry to only keep remaining lines
            remaining = sorted(saved_lines & current_lines)
            saved_entry["output"] = "\n".join(remaining)
            baseline_modified = True

        if added_lines:
            violations.append(f"[{r.tool_name}] Output changed (new/different violations)")

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
