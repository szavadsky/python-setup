"""Sole owner of the lint golden snapshot: normalization, serialization, assertions.

The golden payload is a sorted ``Finding`` array.  A ``Finding`` is one lint
record reduced to ``(tool, file, line, col, rule)``: the volatile ``msg`` field
is dropped and file paths are normalized to relative POSIX form.  Comparison is
a multiset (``Counter``) diff, so duplicates, moved lines, new false positives
and dropped findings all fail precisely.

Regeneration is opt-in via ``PYTHON_SETUP_LINT_UPDATE_GOLDEN=1`` and is refused
under CI.  Regeneration rewrites the golden and its per-tool minimum counts
together so the two artifacts can never disagree.
"""

from __future__ import annotations

import json
import os
import warnings
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import TypedDict

import pytest

__all__ = [
    "SEMANTIC_ENV",
    "UPDATE_ENV",
    "Finding",
    "assert_matches_golden",
    "assert_oracle_coverage",
    "assert_tool_coverage",
    "finding_key",
    "normalize_record",
    "read_golden",
    "read_oracle_rules",
    "serialize_findings",
    "serialize_tool_minimums",
    "slice_tool_section",
    "tool_counts_path",
    "tool_minimums",
    "write_golden_files",
]

UPDATE_ENV = "PYTHON_SETUP_LINT_UPDATE_GOLDEN"
SEMANTIC_ENV = "PYTHON_SETUP_LINT_SEMANTIC"

_ORACLE_RULES_PATH = Path(__file__).resolve().parent / "data" / "minimal_sample_project" / "violations.txt"


class Finding(TypedDict):
    """One normalized finding pinned by the golden snapshot."""

    tool: str
    file: str | None
    line: int | None
    col: int | None
    rule: str


FindingKey = tuple[str, str, int, int, str]


def finding_key(finding: Finding) -> FindingKey:
    """Return the None-safe sort/diff key for *finding*.

    Mirrors ``runner.baseline._violation_sort_key``: a ``None`` file sorts as
    ``""`` and ``None`` line/col sort as ``-1``.

    Returns:
        A ``(tool, file, line, col, rule)`` tuple.
    """
    return (
        finding["tool"],
        finding["file"] or "",
        finding["line"] if isinstance(finding["line"], int) else -1,
        finding["col"] if isinstance(finding["col"], int) else -1,
        finding["rule"],
    )


def _normalize_path(value: object, project: Path) -> str | None:
    """Return *value* as a project-relative POSIX path (``None`` passes through)."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"expected file path str or None, got {type(value).__name__}")
    posix = PurePosixPath(value.replace("\\", "/"))
    if posix.is_absolute():
        try:
            posix = posix.relative_to(PurePosixPath(project.as_posix()))
        except ValueError as exc:
            raise AssertionError(f"absolute finding path outside project: {value!r}") from exc
    parts = tuple(part for part in posix.parts if part not in (".", ""))
    if not parts:
        return ""
    out = PurePosixPath(*parts).as_posix()
    assert not PurePosixPath(out).is_absolute(), f"expected a relative POSIX path, got {out!r}"
    return out


def normalize_record(record: Mapping[str, object], project: Path) -> Finding:
    """Reduce one capture record to a golden ``Finding``.

    Drops ``msg``, relativizes absolute file paths against *project*, strips
    ``./``, converts backslashes to ``/`` and returns a POSIX path.

    Args:
        record: Capture record with ``tool``, ``file``, ``line``, ``col``,
            ``rule`` (and possibly ``msg``) keys.
        project: Project root absolute paths are relativized against.

    Returns:
        A ``Finding`` with exactly the five golden keys.
    """
    tool = record.get("tool")
    rule = record.get("rule")
    if not isinstance(tool, str) or not isinstance(rule, str):
        raise TypeError(f"record tool/rule must be strings, got tool={tool!r} rule={rule!r}")
    line = record.get("line")
    col = record.get("col")
    if line is not None and not isinstance(line, int):
        raise TypeError(f"record line must be int or None, got {line!r}")
    if col is not None and not isinstance(col, int):
        raise TypeError(f"record col must be int or None, got {col!r}")
    return Finding(
        tool=tool,
        file=_normalize_path(record.get("file"), project),
        line=line,
        col=col,
        rule=rule,
    )


def _finding_row(finding: Finding) -> dict[str, object]:
    """Project a finding onto the five golden fields (dropping any extras)."""
    return {
        "tool": finding["tool"],
        "file": finding["file"],
        "line": finding["line"],
        "col": finding["col"],
        "rule": finding["rule"],
    }


def serialize_findings(findings: Iterable[Finding]) -> str:
    """Serialize findings as canonical JSON text: sorted, indent=2, trailing newline.

    Returns:
        The JSON text with ``sort_keys=True`` and exactly one trailing newline.
    """
    rows = [_finding_row(finding) for finding in sorted(findings, key=finding_key)]
    return json.dumps(rows, indent=2, sort_keys=True) + "\n"


def serialize_tool_minimums(minimums: Mapping[str, int]) -> str:
    """Serialize per-tool minimum counts with the same canonical JSON format.

    Returns:
        The JSON text with ``sort_keys=True`` and exactly one trailing newline.
    """
    return json.dumps(dict(minimums), indent=2, sort_keys=True) + "\n"


def tool_minimums(findings: Iterable[Finding]) -> dict[str, int]:
    """Return ``{tool: min_count}`` covering every registered tool.

    Tools with no captured findings get a minimum of ``0``; their coverage
    remains guarded by the first-run tool-section assertions.

    Returns:
        Sorted ``{tool_name: observed_finding_count}`` mapping.
    """
    from python_setup_lint.runner import TOOLS  # local import keeps synthetic tests free of runner setup

    counts = Counter(finding["tool"] for finding in findings)
    names = {spec.name for spec in TOOLS} | set(counts)
    return {name: counts.get(name, 0) for name in sorted(names)}


def tool_counts_path(golden_path: Path) -> Path:
    """Return the sibling counts path for *golden_path*.

    ``..._findings.json`` maps to ``..._tool_counts.json``; any other name gets
    a ``_tool_counts.json`` suffix.

    Returns:
        Sibling path for the per-tool minimum counts artifact.
    """
    base = golden_path.name.removesuffix("_findings.json") if golden_path.name.endswith("_findings.json") else golden_path.stem
    return golden_path.with_name(f"{base}_tool_counts.json")


def write_golden_files(golden_path: Path, findings: Iterable[Finding]) -> None:
    """Write the golden and its per-tool counts together.

    Both files use the canonical JSON serialization so repeated runs are
    byte-identical.
    """
    materialized = list(findings)
    golden_path.parent.mkdir(parents=True, exist_ok=True)
    golden_path.write_text(serialize_findings(materialized), encoding="utf-8")
    counts_path = tool_counts_path(golden_path)
    counts_path.write_text(serialize_tool_minimums(tool_minimums(materialized)), encoding="utf-8")


def _coerce_finding(value: object, golden_path: Path) -> Finding:
    """Validate one JSON element read from a golden file."""
    if not isinstance(value, Mapping):
        pytest.fail(f"golden entry must be a JSON object in {golden_path}: {value!r}")
    tool = value.get("tool")
    file = value.get("file")
    line = value.get("line")
    col = value.get("col")
    rule = value.get("rule")
    if not isinstance(tool, str) or not isinstance(rule, str):
        pytest.fail(f"golden entry must have string tool/rule in {golden_path}: {value!r}")
    if file is not None and not isinstance(file, str):
        pytest.fail(f"golden entry must have str/None file in {golden_path}: {value!r}")
    if line is not None and not isinstance(line, int):
        pytest.fail(f"golden entry must have int/None line in {golden_path}: {value!r}")
    if col is not None and not isinstance(col, int):
        pytest.fail(f"golden entry must have int/None col in {golden_path}: {value!r}")
    return Finding(tool=tool, file=file, line=line, col=col, rule=rule)


def read_golden(golden_path: Path) -> list[Finding]:
    """Read and validate a committed golden file.

    Returns:
        The golden findings in file order.
    """
    if not golden_path.is_file():
        pytest.fail(f"golden file not found: {golden_path}; run with {UPDATE_ENV}=1 to create it")
    raw: object = json.loads(golden_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        pytest.fail(f"golden file must contain a JSON array: {golden_path}")
    return [_coerce_finding(entry, golden_path) for entry in raw]


def _diff_keys(actual: Sequence[Finding], golden: Sequence[Finding]) -> tuple[list[FindingKey], list[FindingKey]]:
    """Return sorted ``(added, removed)`` key lists for the two multisets."""
    actual_counts = Counter(finding_key(finding) for finding in actual)
    golden_counts = Counter(finding_key(finding) for finding in golden)
    added = sorted((actual_counts - golden_counts).elements())
    removed = sorted((golden_counts - actual_counts).elements())
    return added, removed


def _format_drift(added: Sequence[FindingKey], removed: Sequence[FindingKey], golden_path: Path) -> str:
    """Build the failure message naming every added and removed key."""
    lines = [f"golden mismatch for {golden_path}"]
    if added:
        lines.append(f"added ({len(added)}):")
        lines.extend(f"  {key!r}" for key in added)
    if removed:
        lines.append(f"removed ({len(removed)}):")
        lines.extend(f"  {key!r}" for key in removed)
    return "\n".join(lines)


def assert_matches_golden(findings: Sequence[Finding], *, golden_path: Path) -> None:
    """Assert *findings* equal the committed golden as a multiset.

    With ``PYTHON_SETUP_LINT_UPDATE_GOLDEN=1`` this rewrites the golden and its
    counts instead of comparing.  Under CI it fails rather than rewriting.
    """
    if os.environ.get(UPDATE_ENV) == "1":
        if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
            pytest.fail(f"refusing to rewrite golden under CI; unset {UPDATE_ENV} or run locally to regenerate {golden_path}")
        warnings.warn(f"updating golden files for {golden_path}", stacklevel=2)
        write_golden_files(golden_path, findings)
        return
    committed = read_golden(golden_path)
    added, removed = _diff_keys(findings, committed)
    if added or removed:
        pytest.fail(_format_drift(added, removed, golden_path))


def read_oracle_rules() -> list[str]:
    """Read planted violation rule names from the retained ``violations.txt`` oracle.

    Returns:
        Non-comment, non-blank rule symbols in file order.
    """
    lines = _ORACLE_RULES_PATH.read_text(encoding="utf-8").splitlines()
    return [stripped for line in lines if (stripped := line.strip()) and not stripped.startswith("#")]


def slice_tool_section(output: str, start: str, end: str) -> str:
    """Return the text from *start* (inclusive) up to *end* (exclusive).

    Both markers are literal strings; *end* is searched only after *start*.
    """
    begin = output.find(start)
    assert begin != -1, f"section start marker not found: {start!r}"
    finish = output.find(end, begin + len(start))
    assert finish != -1, f"section end marker not found after {start!r}: {end!r}"
    return output[begin:finish]


def assert_oracle_coverage(findings: Iterable[Finding], rules: Iterable[str]) -> None:
    """Assert every oracle rule appears among *findings*."""
    present = {finding["rule"] for finding in findings}
    missing = sorted(set(rules) - present)
    assert not missing, f"oracle rules missing from golden findings: {missing}"


def assert_tool_coverage(findings: Iterable[Finding], minimums: Mapping[str, int]) -> None:
    """Assert each tool in *minimums* produced at least its minimum finding count."""
    counts = Counter(finding["tool"] for finding in findings)
    below = [(tool, minimums[tool], counts.get(tool, 0)) for tool in sorted(minimums) if counts.get(tool, 0) < minimums[tool]]
    assert not below, f"tool finding counts below minimum: {below}"
