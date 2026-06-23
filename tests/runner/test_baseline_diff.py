"""T2 — drift-resistant baseline diff tests.

Covers the schema-v2 records path: order-tolerant, multiset-accurate,
O(n log n) walk-merge.  Exercises :func:`_compare_sorted` directly
(surface-unit) PLUS per-tool record-parser edge cases (private-complex),
the live mixed-schema load (downstream-integration), and a 50k-line
synthetic benchmark (perf-benchmark) — the envelope's named coverage
categories.

Why a separate file (vs. extending ``test_lint_runner.py``):
the T2 surface is the schema-v2 records path + the ``_compare_sorted``
pure-fn integration seam — both consumed downstream by A8 / T10.
Keeping these rows in their own file makes the seam discoverable for
cross-task reuse and keeps the file LOC within CodingRules budget.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from python_setup_lint.runner import (
    Record,
    _capture_baseline,
    _compare_records_key,
    _compare_sorted,
    _diff_baseline,
    _parse_mypy_records,
    _parse_pylint_records,
    _parse_pyright_records,
    _parse_ruff_records,
    _parse_rumdl_records,
    _parse_ty_records,
    _parse_yamllint_records,
)
from python_setup_lint.testing import make_lint_result

from tests.runner._factories import diff_baseline_with


# ── Surface unit: _compare_sorted pure-fn ────────────────────────


def _sorted(records: list[Record]) -> list[Record]:
    return sorted(records, key=_compare_records_key)


class TestCompareSorted:
    """``_compare_sorted`` — the O(n) walk-merge over two sorted lists."""

    def test_identical_returns_empty(self) -> None:
        a = _sorted([Record("a.py", 1, 1, "E1", "m"), Record("b.py", 2, 1, "E2", "m")])
        added, removed = _compare_sorted(a, list(a))
        assert added == [] and removed == []

    def test_pure_addition(self) -> None:
        a = _sorted([Record("a.py", 1, 1, "E1", "m"), Record("b.py", 2, 1, "E2", "m")])
        b = _sorted([Record("a.py", 1, 1, "E1", "m")])
        added, removed = _compare_sorted(a, b)
        assert [r.rule for r in added] == ["E2"]
        assert removed == []

    def test_pure_removal(self) -> None:
        a = _sorted([Record("a.py", 1, 1, "E1", "m")])
        b = _sorted([Record("a.py", 1, 1, "E1", "m"), Record("b.py", 2, 1, "E2", "m")])
        added, removed = _compare_sorted(a, b)
        assert added == []
        assert [r.rule for r in removed] == ["E2"]

    def test_multiset_count_increase_flagged_as_addition(self) -> None:
        """The G2 fix: a count increase on a duplicate line is NOT swallowed."""
        a = _sorted([
            Record("a.py", 1, 1, "E1", "m"),
            Record("a.py", 1, 1, "E1", "m"),  # one more occurrence
            Record("a.py", 1, 1, "E1", "m"),
        ])
        b = _sorted([Record("a.py", 1, 1, "E1", "m")])
        added, removed = _compare_sorted(a, b)
        assert len(added) == 2 and removed == []  # the 2 surplus records

    def test_multiset_count_decrease_recorded_as_removal(self) -> None:
        a = _sorted([Record("a.py", 1, 1, "E1", "m")])
        b = _sorted([
            Record("a.py", 1, 1, "E1", "m"),
            Record("a.py", 1, 1, "E1", "m"),
            Record("a.py", 1, 1, "E1", "m"),
        ])
        added, removed = _compare_sorted(a, b)
        assert added == []
        assert len(removed) == 2

    def test_msg_change_on_same_key_flagged_as_addition(self) -> None:
        """A same-key message rewrite is a regression, not a no-op."""
        a = _sorted([Record("a.py", 1, 1, "E1", "new msg")])
        b = _sorted([Record("a.py", 1, 1, "E1", "old msg")])
        added, removed = _compare_sorted(a, b)
        assert len(added) == 1 and len(removed) == 1
        assert added[0].msg == "new msg" and removed[0].msg == "old msg"

    def test_order_tolerant_two_equal_blocks_reordered(self) -> None:
        """G2 core invariant: reordered equal blocks → no spurious diff."""
        a = _sorted([Record("a.py", 1, 1, "E1", "m"), Record("b.py", 2, 1, "E2", "m")])
        b = _sorted([Record("b.py", 2, 1, "E2", "m"), Record("a.py", 1, 1, "E1", "m")])
        added, removed = _compare_sorted(a, b)
        assert added == [] and removed == []

    def test_block_insertion_plus_later_reorder_no_spurious_diff(self) -> None:
        """G2 anchor: a inserted block + a reordered later block → only real diffs."""
        # Saved: A, B, C  (sorted)
        saved = _sorted([
            Record("a.py", 1, 1, "A", "m"),
            Record("b.py", 2, 1, "B", "m"),
            Record("c.py", 3, 1, "C", "m"),
        ])
        # Current: A, B, C, D, E (D/E inserted) AND C was moved — but
        # after sorting both sides the only real adds are D, E.
        current = _sorted([
            Record("a.py", 1, 1, "A", "m"),
            Record("b.py", 2, 1, "B", "m"),
            Record("c.py", 3, 1, "C", "m"),
            Record("d.py", 4, 1, "D", "m"),
            Record("e.py", 5, 1, "E", "m"),
        ])
        added, removed = _compare_sorted(current, saved)
        assert {r.rule for r in added} == {"D", "E"}
        assert removed == []

    def test_none_position_records_sort_below_real(self) -> None:
        """R0801/R0401 collapse records (None file) cluster together below str files."""
        recs = _sorted([
            Record("z.py", 9, 9, "Z", "m"),
            Record(None, None, None, "R0801:x<->y", "dup"),
            Record("a.py", 1, 1, "A", "m"),
        ])
        assert recs[0].rule.startswith("R0801")
        assert recs[1].file == "a.py"
        assert recs[2].file == "z.py"


# ── Private-complex unit: per-tool record parsers ────────────────


class TestRecordParsers:
    """Per-tool line→record parser edge cases."""

    def test_ruff_parses_path_line_col_code_msg(self) -> None:
        recs = _parse_ruff_records("src/a.py:1:3: E501 line too long\n")
        assert recs == [Record("src/a.py", 1, 3, "E501", "line too long")]

    def test_ruff_col_optional(self) -> None:
        """Ruff may drop the col on some rules — parser tolerates it."""
        recs = _parse_ruff_records("src/a.py:1: E501 line too long\n")
        assert recs == [Record("src/a.py", 1, None, "E501", "line too long")]

    def test_ruff_skips_non_match_lines(self) -> None:
        recs = _parse_ruff_records("warning: something\nsrc/a.py:1:3: E501 msg\nFound 1 error.\n")
        assert recs == [Record("src/a.py", 1, 3, "E501", "msg")]

    def test_mypy_skips_notes_and_codeless_lines(self) -> None:
        stdout = (
            'src/a.py:1: error: Bad type [arg-type]\n'
            'src/a.py:2: note: see docs\n'
            'src/a.py:3: error: No code here\n'
        )
        recs = _parse_mypy_records(stdout)
        assert recs == [Record("src/a.py", 1, None, "arg-type", "Bad type")]

    def test_mypy_records_sorted_by_file_line(self) -> None:
        stdout = (
            'src/b.py:5: error: X [code-b]\n'
            'src/a.py:1: error: Y [code-a]\n'
        )
        recs = _parse_mypy_records(stdout)
        assert [r.file for r in recs] == ["src/a.py", "src/b.py"]

    def test_pylint_r0801_collapses_to_one_record(self) -> None:
        """R0801 duplicate-region header → ONE record with canonical sorted-span rule."""
        # Real pylint renders the spans on dedicated lines; the duplicated
        # source body that follows is NOT ``==``-prefixed.
        stdout = (
            "************* Module foo\n"
            "src/foo.py:1:1: W0611: Unused import (unused-import)\n"
            "Similar lines in 2 files\n"
            "==src/a.py:[1:5]\n"
            "==src/b.py:[10:15]\n"
            "def foo():\n"
            "    return 1\n"
        )
        recs = _parse_pylint_records(stdout)
        rules = [r.rule for r in recs]
        assert "R0801:src/a.py:1-5<->src/b.py:10-15" in rules  # spans sorted canonically
        assert "unused-import" in rules
        # The duplicated body / header lines do NOT produce extra records.
        assert len(recs) == 2

    def test_pylint_r0801_reorder_produces_identical_record(self) -> None:
        """G2 anchor: reordering the two file-spans of an R0801 dup-region → same record."""
        a = _parse_pylint_records("Similar lines in 2 files\n==src/a.py:[1:5]\n==src/b.py:[10:15]\n")
        b = _parse_pylint_records("Similar lines in 2 files\n==src/b.py:[10:15]\n==src/a.py:[1:5]\n")
        assert a == b
        assert a[0].rule == "R0801:src/a.py:1-5<->src/b.py:10-15"

    def test_pylint_r0401_cyclic_import_collapses(self) -> None:
        recs = _parse_pylint_records("Cyclic import (foo → bar → foo)\n")
        assert recs == [Record(None, None, None, "R0401:foo → bar → foo",
                               "Cyclic import (foo → bar → foo)")]

    def test_pylint_rule_prefers_symbol_over_code(self) -> None:
        """Post-fix rule rename (W0611 → unused-import) does not cause a spurious diff."""
        recs = _parse_pylint_records("src/a.py:1:1: W0611: Unused import (unused-import)\n")
        assert recs[0].rule == "unused-import"

    def test_pylint_falls_back_to_code_when_no_symbol(self) -> None:
        recs = _parse_pylint_records("src/a.py:1:1: W0611: Unused import\n")
        assert recs[0].rule == "W0611"

    def test_ty_concise_form(self) -> None:
        recs = _parse_ty_records("src/a.py:1:3: invalid-argument-type foo\n")
        assert recs == [Record("src/a.py", 1, 3, "invalid-argument-type", "foo")]

    def test_ty_multiline_arrow_form(self) -> None:
        stdout = (
            "error[invalid-argument-type]: Bad arg\n"
            "  --> src/a.py:1:3\n"
            "   |\n"
            " 1 | code\n"
        )
        recs = _parse_ty_records(stdout)
        assert recs == [Record("src/a.py", 1, 3, "invalid-argument-type", "Bad arg")]

    def test_yamllint_parsable(self) -> None:
        recs = _parse_yamllint_records("config/a.yaml:1:3: indentation: msg with: colons\n")
        assert recs == [Record("config/a.yaml", 1, 3, "indentation", "msg with: colons")]

    def test_rumdl_text_strips_footer(self) -> None:
        stdout = (
            "README.md:8:1: [MD013] Line length 200 exceeds 80 characters\n"
            "README.md:73:1: [MD032] List should be preceded by blank line [*]\n"
            "\nIssues: Found 2 issues in 1 file (XXXms)\n"
            "Run `rumdl fmt` to automatically fix 1 of the 2 issues\n"
        )
        recs = _parse_rumdl_records(stdout)
        assert [r.rule for r in recs] == ["MD013", "MD032"]

    def test_pyright_zero_indexed_line_col_plus_one(self) -> None:
        """Pyright lines/cols are 0-indexed → records store 1-indexed (matches other tools)."""
        data = {
            "generalDiagnostics": [
                {"file": "a.py", "rule": "X", "message": "m",
                 "range": {"start": {"line": 5, "character": 10}}},
            ]
        }
        recs = _parse_pyright_records(data)
        assert recs == [Record("a.py", 6, 11, "X", "m")]

    def test_pyright_records_sorted_by_file_line_col_rule(self) -> None:
        data = {"generalDiagnostics": [
            {"file": "b.py", "rule": "Z", "message": "m", "range": {"start": {"line": 2, "character": 0}}},
            {"file": "a.py", "rule": "A", "message": "m", "range": {"start": {"line": 1, "character": 0}}},
        ]}
        recs = _parse_pyright_records(data)
        assert [(r.file, r.line) for r in recs] == [("a.py", 2), ("b.py", 3)]

    def test_pyright_malformed_returns_empty(self) -> None:
        assert _parse_pyright_records({"generalDiagnostics": "not a list"}) == []
        assert _parse_pyright_records([]) == []
        assert _parse_pyright_records({"generalDiagnostics": [42]}) == []


# ── _capture_baseline schema-v2 surface ───────────────────────────


class TestCaptureSchemaV2:
    """``_capture_baseline`` emits schema-v2 records entries for parsers-known tools."""

    def test_pylint_captured_as_schema_v2_records(self) -> None:
        cap = _capture_baseline([make_lint_result(tool_name="pylint", stdout="src/a.py:1:1: W0611: x (unused-import)\n")])
        assert cap[0]["schema"] == "v2"
        assert cap[0]["records"] == [
            {"file": "src/a.py", "line": 1, "col": 1, "rule": "unused-import", "msg": "x"}
        ]

    def test_ruff_captured_as_schema_v2_records(self) -> None:
        cap = _capture_baseline([make_lint_result(tool_name="ruff check", stdout="src/a.py:1:3: E501 msg\n")])
        assert cap[0]["schema"] == "v2"
        assert cap[0]["records"] == [
            {"file": "src/a.py", "line": 1, "col": 3, "rule": "E501", "msg": "msg"}
        ]

    def test_mypy_captured_as_schema_v2_records(self) -> None:
        cap = _capture_baseline([make_lint_result(tool_name="mypy", stdout="src/a.py:1: error: Bad [arg-type]\n")])
        assert cap[0]["schema"] == "v2"
        assert cap[0]["records"][0]["rule"] == "arg-type"

    def test_unknown_tool_keeps_legacy_output(self) -> None:
        cap = _capture_baseline([make_lint_result(tool_name="strange-tool", stdout="noise\n")])
        assert "schema" not in cap[0]
        # Raw stdout is preserved verbatim (trailing newline kept — matches
        # the pre-T2 implementation's behaviour for tools without a parser).
        assert cap[0]["output"] == "noise\n"

    def test_pylint_empty_records_nonempty_stdout_falls_back_to_output(self) -> None:
        """When the records parser matches NOTHING but stdout is non-empty,
        the capture keeps the legacy ``output`` (so absence of records is
        NOT mistaken for a clean pass)."""
        cap = _capture_baseline([make_lint_result(tool_name="pylint", stdout="************* Module banner only\n")])
        assert "schema" not in cap[0]
        assert cap[0]["output"] == "************* Module banner only\n"


# ── Downstream integration: drift-resistant diff semantics ────────


class TestDriftResistantDiff:
    """``_diff_baseline`` against schema-v2 saved entries — the G2 win."""

    def test_pure_insertion_no_spurious_diff(self, tmp_path: Path) -> None:
        """G2 win: a new violation appears → flagged; existing ones unchanged → no spurious diff."""
        saved = [{
            "tool": "pylint", "exit_code": 0, "schema": "v2",
            "records": [{"file": "a.py", "line": 1, "col": 1, "rule": "unused-import", "msg": "x"}],
        }]
        # Same record + one NEW record.
        current = [make_lint_result(
            tool_name="pylint", stdout="a.py:1:1: W0611: x (unused-import)\nb.py:2:2: C0114: y (missing-module-docstring)\n"
        )]
        violations, reloaded = diff_baseline_with(tmp_path, saved, current)
        assert any("pylint" in v for v in violations)
        # Existing record still in the baseline (not spuriously removed by the addition).
        saved_records = reloaded[0]["records"]
        assert {"file": "a.py", "line": 1, "col": 1, "rule": "unused-import", "msg": "x"} in saved_records

    def test_pure_deletion_shrinkage_silently_recorded(self, tmp_path: Path) -> None:
        saved = [{
            "tool": "pylint", "exit_code": 0, "schema": "v2",
            "records": [
                {"file": "a.py", "line": 1, "col": 1, "rule": "unused-import", "msg": "x"},
                {"file": "b.py", "line": 2, "col": 2, "rule": "missing-module-docstring", "msg": "y"},
            ],
        }]
        current = [make_lint_result(tool_name="pylint", stdout="a.py:1:1: W0611: x (unused-import)\n")]
        violations, reloaded = diff_baseline_with(tmp_path, saved, current)
        assert violations == []
        assert reloaded[0]["records"] == [
            {"file": "a.py", "line": 1, "col": 1, "rule": "unused-import", "msg": "x"}
        ]

    def test_reorder_only_no_spurious_diff(self, tmp_path: Path) -> None:
        """Two equal blocks reordered → no spurious diff (the G2 invariant)."""
        saved = [{
            "tool": "pylint", "exit_code": 0, "schema": "v2",
            "records": [
                {"file": "a.py", "line": 1, "col": 1, "rule": "unused-import", "msg": "x"},
                {"file": "b.py", "line": 2, "col": 2, "rule": "missing-module-docstring", "msg": "y"},
            ],
        }]
        # Same record set, reordered in the stdout (b before a).
        current = [make_lint_result(
            tool_name="pylint",
            stdout="b.py:2:2: C0114: y (missing-module-docstring)\na.py:1:1: W0611: x (unused-import)\n"
        )]
        violations, reloaded = diff_baseline_with(tmp_path, saved, current)
        assert violations == []
        # Baseline unchanged.
        assert {tuple(sorted(r.items())) for r in reloaded[0]["records"]} == {
            tuple(sorted(r.items())) for r in saved[0]["records"]
        }

    def test_count_change_on_duplicate_line_detected(self, tmp_path: Path) -> None:
        """G2 win: a duplicate-line count INCREASE is flagged as an addition (not swallowed by set)."""
        saved = [{
            "tool": "mypy", "exit_code": 0, "schema": "v2",
            "records": [{"file": "a.py", "line": 1, "col": None, "rule": "arg-type", "msg": "m"}],
        }]
        # Same file:line:rule appears TWICE now → 1 addition (the surplus).
        current = [make_lint_result(
            tool_name="mypy",
            stdout="a.py:1: error: m [arg-type]\na.py:1: error: m [arg-type]\n"
        )]
        violations, _ = diff_baseline_with(tmp_path, saved, current)
        assert any("mypy" in v for v in violations)

    def test_r0801_reorder_no_spurious_diff(self, tmp_path: Path) -> None:
        """G2 anchor: R0801 duplicate-region span reorder → no spurious diff."""
        saved = [{
            "tool": "pylint", "exit_code": 0, "schema": "v2",
            "records": [{"file": None, "line": None, "col": None,
                         "rule": "R0801:src/a.py:1-5<->src/b.py:10-15",
                         "msg": "Similar lines (R0801)"}],
        }]
        # New current run: file B appears FIRST in the dup-region spans.
        current = [make_lint_result(
            tool_name="pylint",
            stdout="Similar lines in 2 files\n==src/b.py:[10:15]\n==src/a.py:[1:5]\n"
        )]
        violations, _ = diff_baseline_with(tmp_path, saved, current)
        assert violations == []  # canonical-sorted R0801 rule matches the saved one

    def test_exit_code_0_to_nonzero_flagged(self, tmp_path: Path) -> None:
        saved = [{"tool": "mypy", "exit_code": 0, "schema": "v2", "records": []}]
        current = [make_lint_result(tool_name="mypy", exit_code=1, stdout="x.py:1: error: m [code]\n")]
        violations, _ = diff_baseline_with(tmp_path, saved, current)
        assert any("Exit code changed: 0 → 1" in v for v in violations)

    def test_exit_code_nonzero_to_0_shrinkage(self, tmp_path: Path) -> None:
        saved = [{"tool": "mypy", "exit_code": 1, "schema": "v2",
                  "records": [{"file": "a.py", "line": 1, "col": None, "rule": "code", "msg": "m"}]}]
        current = [make_lint_result(tool_name="mypy", exit_code=0, stdout="")]
        violations, reloaded = diff_baseline_with(tmp_path, saved, current)
        assert violations == []
        assert reloaded[0]["exit_code"] == 0
        assert "records" not in reloaded[0]


class TestMixedSchemaLoad:
    """Old ``output``-string entries load alongside schema-v2 entries.

    The envelope's load-bearing backward-compat: a pre-T2 baseline
    (legacy ``output`` form for every tool) MUST load without crash.
    Tools whose stdout a records parser recognises are upgraded in-memory;
    the rest keep the rstrip-set fallback path.
    """

    def test_legacy_pylint_output_upgraded_to_records_on_diff(self, tmp_path: Path) -> None:
        """Pre-T2 pylint stored as raw text → in-memory upgrade on read."""
        # Legacy pylint output — records parser WILL match these lines.
        saved = [{"tool": "pylint", "exit_code": 0,
                  "output": "src/a.py:1:1: W0611: x (unused-import)\nsrc/b.py:2:2: C0114: y (missing-module-docstring)\n"}]
        current = [make_lint_result(
            tool_name="pylint", stdout="src/a.py:1:1: W0611: x (unused-import)\n"
        )]
        violations, reloaded = diff_baseline_with(tmp_path, saved, current)
        assert violations == []
        # The legacy ``output`` is upgraded to schema-v2 records on shrinkage.
        assert reloaded[0]["schema"] == "v2"
        assert "output" not in reloaded[0]
        assert reloaded[0]["records"] == [
            {"file": "src/a.py", "line": 1, "col": 1, "rule": "unused-import", "msg": "x"}
        ]

    def test_legacy_unknown_tool_keeps_rstrip_set_path(self, tmp_path: Path) -> None:
        """A tool with no records parser keeps the legacy rstrip-set diff path."""
        saved = [{"tool": "strange-tool", "exit_code": 0, "output": "line A\nline B\n"}]
        # Current removes line B → shrinkage, no violation.
        current = [make_lint_result(tool_name="strange-tool", stdout="line A\n")]
        violations, reloaded = diff_baseline_with(tmp_path, saved, current)
        assert violations == []
        assert reloaded[0]["output"] == "line A"

    def test_full_pre_t2_baseline_loads_all_tools(self, tmp_path: Path) -> None:
        """A fully-legacy 11-tool baseline loads without crash on every tool.

        Each tool exercises one of the three paths: (a) records-parser
        upgrade (ruff/mypy/pylint/ty/yamllint/rumdl), (b) JSON diagnostics
        (pyright + rumdl-when-JSON), (c) legacy rstrip-set fallback
        (the remainder).  No tool must crash on load OR on the empty-current
        shrinkage path.
        """
        legacy_tools = [
            "tach check", "ruff check", "rumdl check", "mypy", "yamllint",
            "ty check", "pyright verify types", "pylint", "detect-secrets",
        ]
        # Every tool stored as a legacy ``output`` string (pre-T2 form);
        # pyright is a separate diagnostics-form entry in the SAME saved
        # list (one entry per tool name, matching the real schema).
        saved = [{"tool": t, "exit_code": 0, "output": ""} for t in legacy_tools]
        saved.append({
            "tool": "pyright check", "exit_code": 0,
            "diagnostics": {"summary": {"errorCount": 0, "warningCount": 0}},
        })
        # Current: identical legacy tools (all empty) + a pyright stdout
        # that JSON-parses to the same clean summary.
        current = [
            make_lint_result(tool_name=t, exit_code=0, stdout="")
            for t in legacy_tools
        ]
        current.append(make_lint_result(
            tool_name="pyright check",
            stdout=json.dumps({"summary": {"errorCount": 0, "warningCount": 0}}),
        ))
        violations, _ = diff_baseline_with(tmp_path, saved, current)
        assert violations == []  # all-empty current vs all-empty saved → no diff


# ── Performance benchmark: 50k-line baseline < 200ms ─────────────


class TestPerfBenchmark:
    """``_compare_sorted`` scales O(n log n) — the named 50k-line envelope target."""

    def test_50k_line_baseline_compares_under_200ms(self, tmp_path: Path) -> None:
        """50k-record baseline vs 50k-record current compares in <200ms.

        Synthetic fixtures: each side has 50,000 records across 1,000 files.
        ~1% of records differ (500 additions + 500 removals) so the
        walk-merge exercises both branches.  Measured with
        :func:`time.perf_counter` — the assertion is a hard ceiling on
        the named envelope target.
        """
        # Build 50k records: 1000 files × 50 records each.
        records_saved: list[Record] = []
        for f in range(1000):
            file = f"src/file_{f:04d}.py"
            for line in range(1, 51):
                records_saved.append(Record(file, line, 1, "E001", "m"))
        # Current: keep every saved record except the last 500 of file_0999
        # (lines 6..50), then add 500 brand-new files that sort AFTER all
        # file_XXXX entries — a clean 500-removals / 500-additions delta.
        records_current = [
            r for r in records_saved
            if not (r.file == "src/file_0999.py" and r.line and r.line > 5)
        ]
        for f in range(5000, 5500):
            records_current.append(Record(f"src/new_{f:04d}.py", 1, 1, "E001", "m"))
        records_saved.sort(key=_compare_records_key)
        records_current.sort(key=_compare_records_key)

        t0 = time.perf_counter()
        added, removed = _compare_sorted(records_current, records_saved)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert len(added) == 500
        assert len(removed) == 45  # file_0999 lines 6..50 (45 records)
        # 200ms ceiling — generous to absorb CI jitter while still
        # demonstrating O(n log n) (a quadratic impl would be ~seconds).
        assert elapsed_ms < 200.0, f"_compare_sorted took {elapsed_ms:.1f}ms (>200ms ceiling)"

    def test_diff_baseline_50k_end_to_end_under_1s(self, tmp_path: Path) -> None:
        """Full ``_diff_baseline`` round-trip on a 50k-record baseline stays tractable.

        Adds the I/O + parse cost on top of the walk-merge — sanity-bound
        under 1s so production baselines (python-setup's is ~3k records
        in lint.baseline today, with head-room to ~50k for consultant.mcp
        post-baseline-regen) compare without pipeline stalls.
        """
        records: list[dict[str, Any]] = []
        for f in range(1000):
            file = f"src/file_{f:04d}.py"
            for line in range(1, 51):
                records.append({"file": file, "line": line, "col": 1, "rule": "E001", "msg": "m"})
        saved = [{"tool": "ruff check", "exit_code": 0, "schema": "v2", "records": records}]
        baseline_path = tmp_path / "big.json"
        baseline_path.write_text(json.dumps(saved))
        # Identical current → no-delta path returns immediately after parse.
        stdout = "\n".join(
            f"src/file_{f:04d}.py:{line}:1: E001 m"
            for f in range(1000)
            for line in range(1, 51)
        )
        current = [make_lint_result(tool_name="ruff check", stdout=stdout)]
        t0 = time.perf_counter()
        violations = _diff_baseline(current, baseline_path)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert violations == []
        assert elapsed_ms < 1000.0, f"_diff_baseline 50k took {elapsed_ms:.1f}ms (>1s ceiling)"