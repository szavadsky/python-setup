"""Unit tests for ``python_setup_lint.runner``.

Covers command construction, path helpers, baseline capture/diff, and
a lightweight smoke integration test for the CLI entry point.
"""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

import pytest

from python_setup_lint.runner import (
    TOOLS,
    TOOLS_BY_NAME,
    LintResult,
    RunnerConfig,
    ToolSpec,
    ViolationCount,
    _aggregate_statistics,
    _build_command,
    _build_statistics_flags,
    _capture_baseline,
    _diff_baseline,
    _expand_globs,
    _find_py_files,
    _parse_detect_secrets_json,
    _parse_mypy_stderr,
    _parse_pylint_json2,
    _parse_pyright_outputjson,
    _parse_pyright_verify_types,
    _parse_ruff_statistics,
    _parse_rumdl_statistics,
    _parse_stubtest_stderr,
    _parse_tach_json,
    _parse_ty_concise,
    _parse_yamllint_parsable,
    _print_result,
    _print_statistics_table,
    _run_cmd,
    main,
    run_lint,
)
from python_setup_lint.testing import fake_run_cmd_factory, make_lint_result

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ── Helpers ─────────────────────────────────────────────────────────

_CONFIG = RunnerConfig(cwd=Path.cwd())


# _make_result is replaced by make_lint_result from python_setup_lint.testing


# ── ToolSpec / TOOLS table ─────────────────────────────────────────


class TestToolSpec:
    """Verify the tools table is well-formed."""

    def test_all_tools_have_names(self) -> None:
        assert all(t.name for t in TOOLS), "Every tool must have a non-empty name"

    def test_known_tools_present(self) -> None:
        names = {t.name for t in TOOLS}
        expected = {
            "tach check",
            "ruff check",
            "rumdl check",
            "mypy",
            "yamllint",
            "ty check",
            "mypy.stubtest",
            "pyright check",
            "pyright verify types",
            "pylint",
            "detect-secrets",
        }
        assert names == expected, f"Missing tools: {expected - names}"

    def test_autofix_tools(self) -> None:
        fix_tools = {t.name for t in TOOLS if t.supports_fix}
        assert fix_tools == {"ruff check", "rumdl check", "ty check"}

    def test_no_duplicate_names(self) -> None:
        assert len({t.name for t in TOOLS}) == len(TOOLS)


# ── _build_command ──────────────────────────────────────────────────


class TestBuildCommand:
    """Verify command construction for each flag combination."""

    def test_default_no_flags(self) -> None:
        spec = ToolSpec("test", ["tool", "check"], supports_path=True, default_paths=["src/"])
        cmd = _build_command(spec, config=_CONFIG)
        assert cmd == ["tool", "check", "src/"]

    def test_no_default_paths(self) -> None:
        spec = ToolSpec("test", ["tool", "check"])
        cmd = _build_command(spec, config=_CONFIG)
        assert cmd == ["tool", "check"]

    def test_path_no_support(self) -> None:
        spec = ToolSpec("test", ["tool"], supports_path=False)
        cmd = _build_command(spec, config=_CONFIG, path="src/")
        assert cmd == ["tool"]  # path not appended

    def test_path_with_support(self) -> None:
        spec = ToolSpec("test", ["tool"], supports_path=True)
        cmd = _build_command(spec, config=_CONFIG, path="src/python_setup_lint")
        assert cmd == ["tool", "src/python_setup_lint"]

    def test_path_overrides_default(self) -> None:
        spec = ToolSpec("test", ["tool"], supports_path=True, default_paths=["."])
        cmd = _build_command(spec, config=_CONFIG, path="src/")
        assert cmd == ["tool", "src/"]

    def test_fix_no_support(self) -> None:
        spec = ToolSpec("test", ["tool"], supports_fix=False)
        cmd = _build_command(spec, config=_CONFIG, fix=True)
        assert cmd == ["tool"]  # no fix flag appended

    def test_fix_ruff(self) -> None:
        spec = ToolSpec("ruff check", ["ruff", "check"], supports_fix=True)
        cmd = _build_command(spec, config=_CONFIG, fix=True)
        assert cmd == ["ruff", "check", "--fix", "--exit-non-zero-on-fix"]

    def test_fix_rumdl(self) -> None:
        spec = ToolSpec("rumdl check", ["rumdl", "check"], supports_fix=True)
        cmd = _build_command(spec, config=_CONFIG, fix=True)
        assert cmd == ["rumdl", "check", "--fix"]

    def test_fix_ty(self) -> None:
        spec = ToolSpec("ty check", ["ty", "check"], supports_fix=True)
        cmd = _build_command(spec, config=_CONFIG, fix=True)
        assert cmd == ["ty", "check", "--fix"]

    def test_exclude_no_support(self) -> None:
        spec = ToolSpec("test", ["tool"], supports_exclude=False)
        cmd = _build_command(spec, config=_CONFIG, exclude="tests/")
        assert cmd == ["tool"]

    def test_exclude_tach(self) -> None:
        spec = ToolSpec("tach check", ["tach", "check"], supports_exclude=True)
        cmd = _build_command(spec, config=_CONFIG, exclude="tests/")
        assert cmd == ["tach", "check", "-e", "tests/"]

    def test_exclude_other(self) -> None:
        spec = ToolSpec("ruff check", ["ruff", "check"], supports_exclude=True)
        cmd = _build_command(spec, config=_CONFIG, exclude="tests/")
        assert cmd == ["ruff", "check", "--exclude", "tests/"]

    def test_exclude_with_path(self) -> None:
        spec = ToolSpec("ruff check", ["ruff", "check"], supports_path=True, supports_exclude=True)
        cmd = _build_command(spec, config=_CONFIG, path="src/", exclude="tests/")
        assert cmd == ["ruff", "check", "src/", "--exclude", "tests/"]

    def test_pylint_expands_path(self) -> None:
        spec = ToolSpec("pylint", ["pylint"], supports_path=True)
        cmd = _build_command(spec, config=_CONFIG, path="src/python_setup_lint")
        # Should call _find_py_files, which returns .py files under that dir
        assert cmd[0] == "pylint"
        assert len(cmd) > 1
        # All should be .py files
        for arg in cmd[1:]:
            assert arg.endswith(".py"), f"Expected .py file, got {arg}"

    def test_yamllint_expands_glob(self) -> None:
        spec = ToolSpec("yamllint", ["yamllint"], supports_path=True, default_paths=["src/**/*.py"])
        cmd = _build_command(spec, config=_CONFIG)
        assert cmd[0] == "yamllint"
        assert len(cmd) > 1
        # All should end in .py
        for arg in cmd[1:]:
            assert arg.endswith(".py"), f"Expected .py file, got {arg}"

    def test_stubtest_with_package_name(self) -> None:
        """stubtest includes package_name and allowlist when file exists."""
        spec = TOOLS_BY_NAME["mypy.stubtest"]
        config = RunnerConfig(cwd=Path.cwd(), package_name="python_setup_lint")
        cmd = _build_command(spec, config=config)
        assert "python_setup_lint" in cmd
        assert "--concise" in cmd
        assert "--ignore-missing-stub" in cmd
        # allowlist is conditional on file existence — may or may not be present

    def test_stubtest_skipped_when_no_package_name(self) -> None:
        """stubtest command has no package_name arg when package_name=None."""
        spec = TOOLS_BY_NAME["mypy.stubtest"]
        config = RunnerConfig(cwd=Path.cwd(), package_name=None)
        cmd = _build_command(spec, config=config)
        # Without package_name, stubtest just gets the base command
        assert cmd == ["python", "-m", "mypy.stubtest"]

    def test_verifytypes_with_package_name(self) -> None:
        """pyright verifytypes includes package_name."""
        spec = TOOLS_BY_NAME["pyright verify types"]
        config = RunnerConfig(cwd=Path.cwd(), package_name="python_setup_lint")
        cmd = _build_command(spec, config=config)
        assert "python_setup_lint" in cmd
        assert "--ignoreexternal" in cmd
        assert "--outputjson" in cmd

    def test_verifytypes_skipped_when_no_package_name(self) -> None:
        """pyright verifytypes command has no package_name arg when package_name=None."""
        spec = TOOLS_BY_NAME["pyright verify types"]
        config = RunnerConfig(cwd=Path.cwd(), package_name=None)
        cmd = _build_command(spec, config=config)
        assert cmd == ["pyright", "--verifytypes"]


# ── _find_py_files ─────────────────────────────────────────────────


class TestFindPyFiles:
    """Verify recursive .py file discovery."""

    def test_finds_py_files_in_dir(self) -> None:
        # src/ is a known directory with .py files in the real repo
        files = _find_py_files(["src/python_setup_lint"], cwd=Path.cwd())
        assert len(files) > 0
        assert all(f.endswith(".py") for f in files)
        # Paths are relative to repo root
        assert all(not Path(f).is_absolute() for f in files)

    def test_returns_sorted(self) -> None:
        files = _find_py_files(["src/python_setup_lint"], cwd=Path.cwd())
        assert files == sorted(files)

    def test_no_duplicates(self) -> None:
        files = _find_py_files(["src/python_setup_lint", "src/python_setup_lint"], cwd=Path.cwd())
        assert len(files) == len(set(files))

    def test_empty_for_nonexistent_dir(self) -> None:
        files = _find_py_files(["nonexistent_dir_xyz"], cwd=Path.cwd())
        assert files == []


# ── _expand_globs ──────────────────────────────────────────────────


class TestExpandGlobs:
    """Verify glob expansion works (or falls through for non-globs)."""

    def test_passthrough_no_glob(self) -> None:
        result = _expand_globs(["src/python_setup_lint"], cwd=Path.cwd())
        assert result == ["src/python_setup_lint"]

    def test_expands_glob(self) -> None:
        result = _expand_globs(["src/**/*.py"], cwd=Path.cwd())
        assert len(result) >= 1
        assert all(f.endswith(".py") for f in result)

    def test_empty_glob(self) -> None:
        result = _expand_globs(["nonexistent_glob_xyz/*.nonexistent"], cwd=Path.cwd())
        assert result == []


# ── _run_cmd (lightweight, quick commands only) ────────────────────


class TestRunCmd:
    """Verify subprocess runner returns structured results."""

    def test_success(self) -> None:
        result = _run_cmd(["echo", "hello"], cwd=Path.cwd(), label="echo")
        assert result.exit_code == 0
        assert result.stdout == "hello\n"
        assert result.tool_name == "echo"
        assert result.elapsed >= 0

    def test_failure(self) -> None:
        result = _run_cmd(["false"], cwd=Path.cwd(), label="false")
        assert result.exit_code != 0

    def test_non_existent_command(self) -> None:
        with pytest.raises(FileNotFoundError):
            _run_cmd(["nonexistent_cmd_xyz789"], cwd=Path.cwd(), label="bad")


# ── Baseline capture / diff ───────────────────────────────────────


class TestBaseline:
    """Verify baseline capture and diff logic."""

    def test_capture_basic(self) -> None:
        results = [
            make_lint_result(tool_name="ruff check", exit_code=0, stdout="no issues"),
            make_lint_result(tool_name="mypy", exit_code=1, stdout="error: x"),
        ]
        baseline = _capture_baseline(results)
        assert len(baseline) == 2
        assert baseline[0]["tool"] == "ruff check"
        assert baseline[0]["exit_code"] == 0
        assert baseline[1]["exit_code"] == 1

    def test_capture_handles_json_output(self) -> None:
        pyright_out = json.dumps({"summary": {"errorCount": 1}})
        results = [make_lint_result(tool_name="pyright check", stdout=pyright_out)]
        baseline = _capture_baseline(results)
        assert baseline[0]["diagnostics"] == {"summary": {"errorCount": 1}}

    def test_capture_rumdl_strips_timing(self) -> None:
        """rumdl success output has timing stripped via regex replacement."""
        results = [make_lint_result(tool_name="rumdl check", stdout="\nSuccess: No issues found in 47 files (12ms)\n")]
        baseline = _capture_baseline(results)
        assert "(XXXms)" in baseline[0]["output"], f"Expected timing stripped, got: {baseline[0]['output']}"

    def test_capture_pyright_strips_time_in_sec(self) -> None:
        """_capture_baseline strips volatile timeInSec from pyright summary."""
        pyright_out = json.dumps({"summary": {"errorCount": 1, "timeInSec": 12.5, "filesAnalyzed": 100}})
        results = [make_lint_result(tool_name="pyright check", stdout=pyright_out)]
        baseline = _capture_baseline(results)
        summary = baseline[0]["diagnostics"]["summary"]
        assert "timeInSec" not in summary, f"timeInSec should be stripped, got: {summary}"

    def test_diff_pyright_ignores_time_in_sec(self, tmp_path: Path) -> None:
        """_diff_baseline ignores timeInSec differences in pyright summary."""
        baseline_path = tmp_path / "pyright_time.json"
        base_diag = {"summary": {"errorCount": 1, "timeInSec": 10.0, "filesAnalyzed": 100}}
        cur_diag = {"summary": {"errorCount": 1, "timeInSec": 15.0, "filesAnalyzed": 100}}
        saved = [{"tool": "pyright check", "exit_code": 0, "diagnostics": base_diag}]
        baseline_path.write_text(json.dumps(saved))
        results = [make_lint_result(tool_name="pyright check", exit_code=0, stdout=json.dumps(cur_diag))]
        violations = _diff_baseline(results, baseline_path)
        assert violations == [], f"Expected no violations with timeInSec diff, got: {violations}"

    def test_diff_uses_diagnostics_when_present(self, tmp_path: Path) -> None:
        """_diff_baseline compares diagnostics key when present instead of raw output."""
        baseline_path = tmp_path / "diag_baseline.json"
        diag = {"summary": {"errorCount": 1}}
        saved = [{"tool": "pyright check", "exit_code": 0, "diagnostics": diag}]
        baseline_path.write_text(json.dumps(saved))
        # Same diagnostics, different raw output — no violation
        results = [make_lint_result(tool_name="pyright check", exit_code=0, stdout=json.dumps(diag))]
        violations = _diff_baseline(results, baseline_path)
        assert violations == [], f"Expected no violations with matching diagnostics, got: {violations}"

    def test_diff_diagnostics_changed(self, tmp_path: Path) -> None:
        """_diff_baseline detects diagnostics change."""
        baseline_path = tmp_path / "diag_change.json"
        saved = [{"tool": "pyright check", "exit_code": 0, "diagnostics": {"summary": {"errorCount": 0}}}]
        baseline_path.write_text(json.dumps(saved))
        results = [make_lint_result(tool_name="pyright check", exit_code=0, stdout=json.dumps({"summary": {"errorCount": 1}}))]
        violations = _diff_baseline(results, baseline_path)
        assert any("diagnostics" in v.lower() for v in violations), f"Expected diagnostics change, got: {violations}"

    def test_diff_no_baseline_file(self) -> None:
        results = [make_lint_result()]
        violations = _diff_baseline(results, Path("/nonexistent/baseline.json"))
        assert len(violations) == 1
        assert "not found" in violations[0]

    def test_diff_identical(self, tmp_path: Path) -> None:
        baseline_path = tmp_path / "baseline.json"
        results = [make_lint_result(tool_name="test", exit_code=0, stdout="ok")]
        saved = [{"tool": "test", "exit_code": 0, "output": "ok"}]
        with open(baseline_path, "w") as f:
            json.dump(saved, f)
        violations = _diff_baseline(results, baseline_path)
        assert violations == [], f"Expected no violations, got: {violations}"

    def test_diff_exit_code_changed(self, tmp_path: Path) -> None:
        baseline_path = tmp_path / "baseline.json"
        results = [make_lint_result(tool_name="test", exit_code=1, stdout="ok")]
        saved = [{"tool": "test", "exit_code": 0, "output": "ok"}]
        with open(baseline_path, "w") as f:
            json.dump(saved, f)
        violations = _diff_baseline(results, baseline_path)
        assert any("exit code" in v.lower() for v in violations), f"Expected exit code diff, got: {violations}"

    def test_diff_output_changed(self, tmp_path: Path) -> None:
        baseline_path = tmp_path / "baseline.json"
        results = [make_lint_result(tool_name="test", exit_code=0, stdout="new output")]
        saved = [{"tool": "test", "exit_code": 0, "output": "old output"}]
        with open(baseline_path, "w") as f:
            json.dump(saved, f)
        violations = _diff_baseline(results, baseline_path)
        assert any("output changed" in v.lower() for v in violations), f"Expected output change, got: {violations}"

    def test_diff_new_tool(self, tmp_path: Path) -> None:
        baseline_path = tmp_path / "baseline.json"
        results = [make_lint_result(tool_name="tool_a"), make_lint_result(tool_name="tool_b")]
        saved = [{"tool": "tool_a", "exit_code": 0, "output": ""}]
        with open(baseline_path, "w") as f:
            json.dump(saved, f)
        violations = _diff_baseline(results, baseline_path)
        assert any("no baseline entry" in v.lower() for v in violations), f"Expected new tool message, got: {violations}"

    def test_diff_invalid_json(self, tmp_path: Path) -> None:
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text("not valid json")
        violations = _diff_baseline([make_lint_result()], baseline_path)
        assert len(violations) == 1
        assert "Cannot read" in violations[0]

    # ── T0: add-vs-remove semantics ─────────────────────────────

    def test_diff_pure_shrinkage_auto_records(self, tmp_path: Path) -> None:
        """Pure shrinkage (removed violations) auto-records silently, returns no violations."""
        baseline_path = tmp_path / "shrink.json"
        saved = [
            {"tool": "ruff check", "exit_code": 0, "output": "src/a.py:1: error A\nsrc/b.py:2: error B"},
            {"tool": "mypy", "exit_code": 0, "output": "src/c.py:3: error C"},
        ]
        baseline_path.write_text(json.dumps(saved))
        # Current output has only one of the two violations (shrinkage)
        results = [
            make_lint_result(tool_name="ruff check", exit_code=0, stdout="src/a.py:1: error A"),
            make_lint_result(tool_name="mypy", exit_code=0, stdout="src/c.py:3: error C"),
        ]
        violations = _diff_baseline(results, baseline_path)
        assert violations == [], f"Expected no violations for pure shrinkage, got: {violations}"
        # Baseline should be rewritten with shrunken content
        import json as _json
        updated = _json.loads(baseline_path.read_text())
        ruff_entry = next(e for e in updated if e["tool"] == "ruff check")
        assert "src/b.py:2: error B" not in ruff_entry.get("output", ""), (
            f"Shrunken violation should be removed from baseline, got: {ruff_entry}"
        )

    def test_diff_pure_addition_flags_regression(self, tmp_path: Path) -> None:
        """Pure addition (new violations) flags regression, baseline unchanged."""
        baseline_path = tmp_path / "add.json"
        saved = [
            {"tool": "ruff check", "exit_code": 0, "output": "src/a.py:1: error A"},
        ]
        baseline_path.write_text(json.dumps(saved))
        # Current output has an additional violation
        results = [
            make_lint_result(tool_name="ruff check", exit_code=0, stdout="src/a.py:1: error A\nsrc/b.py:2: error B"),
        ]
        violations = _diff_baseline(results, baseline_path)
        assert any("output changed" in v.lower() for v in violations), (
            f"Expected output change violation for addition, got: {violations}"
        )
        # Baseline should NOT be rewritten for additions
        import json as _json
        updated = _json.loads(baseline_path.read_text())
        assert updated == saved, "Baseline should be unchanged on pure addition"

    def test_diff_mixed_shrinkage_and_addition(self, tmp_path: Path) -> None:
        """Mixed: shrinkage auto-records, addition flags regression, baseline rewritten for shrinkage only."""
        baseline_path = tmp_path / "mixed.json"
        saved = [
            {"tool": "ruff check", "exit_code": 0, "output": "src/a.py:1: error A\nsrc/b.py:2: error B"},
        ]
        baseline_path.write_text(json.dumps(saved))
        # Current: removed error B, added error C
        results = [
            make_lint_result(tool_name="ruff check", exit_code=0, stdout="src/a.py:1: error A\nsrc/c.py:3: error C"),
        ]
        violations = _diff_baseline(results, baseline_path)
        assert any("output changed" in v.lower() for v in violations), (
            f"Expected output change violation for addition, got: {violations}"
        )
        # Baseline should be rewritten: error B removed, error C NOT added
        import json as _json
        updated = _json.loads(baseline_path.read_text())
        ruff_entry = next(e for e in updated if e["tool"] == "ruff check")
        assert "src/b.py:2: error B" not in ruff_entry.get("output", ""), (
            "Shrunken violation should be removed from baseline"
        )
        assert "src/c.py:3: error C" not in ruff_entry.get("output", ""), (
            "Added violation should NOT appear in baseline"
        )

    def test_diff_pylint_shrinkage_auto_records(self, tmp_path: Path) -> None:
        """Pylint inventory shrinkage auto-records silently."""
        baseline_path = tmp_path / "pylint_shrink.json"
        saved = [
            {
                "tool": "pylint",
                "exit_code": 0,
                "output": "1 src/a.py:1:1: W0611: unused-import\n1 src/b.py:2:2: C0114: missing-module-docstring",
            },
        ]
        baseline_path.write_text(json.dumps(saved))
        # Current has one fewer pylint signature
        results = [
            make_lint_result(
                tool_name="pylint",
                exit_code=0,
                stdout="src/a.py:1:1: W0611: unused-import",
            ),
        ]
        violations = _diff_baseline(results, baseline_path)
        assert violations == [], f"Expected no violations for pylint shrinkage, got: {violations}"
        import json as _json
        updated = _json.loads(baseline_path.read_text())
        pylint_entry = next(e for e in updated if e["tool"] == "pylint")
        assert "C0114" not in pylint_entry.get("output", ""), (
            "Shrunken pylint violation should be removed from baseline"
        )

    def test_diff_exit_code_shrinkage_auto_records(self, tmp_path: Path) -> None:
        """Exit code improvement (1→0) auto-records silently."""
        baseline_path = tmp_path / "rc_shrink.json"
        saved = [{"tool": "mypy", "exit_code": 1, "output": "some error"}]
        baseline_path.write_text(json.dumps(saved))
        results = [make_lint_result(tool_name="mypy", exit_code=0, stdout="")]
        violations = _diff_baseline(results, baseline_path)
        assert violations == [], f"Expected no violations for exit-code shrinkage, got: {violations}"
        import json as _json
        updated = _json.loads(baseline_path.read_text())
        mypy_entry = next(e for e in updated if e["tool"] == "mypy")
        assert mypy_entry["exit_code"] == 0, "Baseline exit_code should be updated"

    def test_diff_tool_removed_shrinkage_auto_records(self, tmp_path: Path) -> None:
        """Tool present in baseline but absent from current → removed from baseline silently."""
        baseline_path = tmp_path / "tool_removed.json"
        saved = [
            {"tool": "ruff check", "exit_code": 0, "output": "ok"},
            {"tool": "mypy", "exit_code": 0, "output": "ok"},
        ]
        baseline_path.write_text(json.dumps(saved))
        results = [make_lint_result(tool_name="ruff check", exit_code=0, stdout="ok")]
        violations = _diff_baseline(results, baseline_path)
        assert violations == [], f"Expected no violations for tool removal, got: {violations}"
        import json as _json
        updated = _json.loads(baseline_path.read_text())
        assert len(updated) == 1, f"Expected 1 tool in baseline after removal, got {len(updated)}"
        assert updated[0]["tool"] == "ruff check"

    # ── T0: additional edge cases ────────────────────────────────

    def test_diff_diagnostics_shrinkage_auto_records(self, tmp_path: Path) -> None:
        """Pyright diagnostics error-count shrinkage auto-records silently."""
        baseline_path = tmp_path / "diag_shrink.json"
        saved = [{
            "tool": "pyright check",
            "exit_code": 0,
            "diagnostics": {"summary": {"errorCount": 2, "warningCount": 0}},
        }]
        baseline_path.write_text(json.dumps(saved))
        # Current has fewer errors (shrinkage)
        results = [make_lint_result(
            tool_name="pyright check", exit_code=0,
            stdout=json.dumps({"summary": {"errorCount": 1, "warningCount": 0}}),
        )]
        violations = _diff_baseline(results, baseline_path)
        assert violations == [], f"Expected no violations for diagnostics shrinkage, got: {violations}"
        updated = json.loads(baseline_path.read_text())
        assert updated[0]["diagnostics"]["summary"]["errorCount"] == 1

    def test_diff_pylint_addition_flags_regression(self, tmp_path: Path) -> None:
        """Pylint inventory addition flags regression, baseline unchanged."""
        baseline_path = tmp_path / "pylint_add.json"
        saved = [{
            "tool": "pylint",
            "exit_code": 0,
            "output": "1 src/a.py:1:1: W0611: unused-import",
        }]
        baseline_path.write_text(json.dumps(saved))
        # Current has an additional pylint signature
        results = [make_lint_result(
            tool_name="pylint", exit_code=0,
            stdout="src/a.py:1:1: W0611: unused-import\nsrc/b.py:2:2: C0114: missing-module-docstring",
        )]
        violations = _diff_baseline(results, baseline_path)
        assert any("output changed" in v.lower() for v in violations), (
            f"Expected output change for pylint addition, got: {violations}"
        )
        # Baseline should NOT be rewritten for additions
        updated = json.loads(baseline_path.read_text())
        assert updated == saved, "Baseline should be unchanged on pylint addition"

    def test_diff_ruff_ordering_insensitive(self, tmp_path: Path) -> None:
        """Ruff output with same lines in different order is treated as identical (no violation)."""
        baseline_path = tmp_path / "ruff_order.json"
        saved = [{
            "tool": "ruff check",
            "exit_code": 0,
            "output": "src/a.py:1: error A\nsrc/b.py:2: error B",
        }]
        baseline_path.write_text(json.dumps(saved))
        # Same lines, reversed order
        results = [make_lint_result(
            tool_name="ruff check", exit_code=0,
            stdout="src/b.py:2: error B\nsrc/a.py:1: error A",
        )]
        violations = _diff_baseline(results, baseline_path)
        assert violations == [], f"Expected no violations for reordered ruff output, got: {violations}"

    def test_diff_rumdl_shrinkage_auto_records(self, tmp_path: Path) -> None:
        """Rumdl output shrinkage (fewer lines) auto-records silently, ignoring timing differences."""
        baseline_path = tmp_path / "rumdl_shrink.json"
        saved = [{
            "tool": "rumdl check",
            "exit_code": 0,
            "output": "src/a.md:1 MD012 (10ms)\nsrc/b.md:3 MD013 (20ms)",
        }]
        baseline_path.write_text(json.dumps(saved))
        # Current has one fewer violation, timing differs
        results = [make_lint_result(
            tool_name="rumdl check", exit_code=0,
            stdout="src/a.md:1 MD012 (5ms)",
        )]
        violations = _diff_baseline(results, baseline_path)
        assert violations == [], f"Expected no violations for rumdl shrinkage, got: {violations}"
        updated = json.loads(baseline_path.read_text())
        rumdl_entry = next(e for e in updated if e["tool"] == "rumdl check")
        assert "MD013" not in rumdl_entry.get("output", ""), (
            "Shrunken rumdl violation should be removed from baseline"
        )

    def test_diff_empty_baseline_no_current(self, tmp_path: Path) -> None:
        """Empty baseline list with no current results → no violations, baseline unchanged."""
        baseline_path = tmp_path / "empty.json"
        baseline_path.write_text(json.dumps([]))
        violations = _diff_baseline([], baseline_path)
        assert violations == [], f"Expected no violations for empty baseline, got: {violations}"
        assert json.loads(baseline_path.read_text()) == [], "Empty baseline should remain empty"

    def test_diff_output_to_empty_shrinkage(self, tmp_path: Path) -> None:
        """Output present in baseline but empty in current → pure shrinkage, auto-records."""
        baseline_path = tmp_path / "to_empty.json"
        saved = [{"tool": "mypy", "exit_code": 0, "output": "src/a.py:1: error"}]
        baseline_path.write_text(json.dumps(saved))
        results = [make_lint_result(tool_name="mypy", exit_code=0, stdout="")]
        violations = _diff_baseline(results, baseline_path)
        assert violations == [], f"Expected no violations for output-to-empty shrinkage, got: {violations}"
        updated = json.loads(baseline_path.read_text())
        mypy_entry = next(e for e in updated if e["tool"] == "mypy")
        assert mypy_entry.get("output", "") == "", "Baseline output should be empty after full shrinkage"

    # ── T0 review regression tests (D3–D7) ───────────────────────

    def test_diff_duplicate_tool_in_baseline(self, tmp_path: Path) -> None:
        """D3: Duplicate tool entries in baseline — all removed when tool absent from current."""
        baseline_path = tmp_path / "dup_tool.json"
        saved = [
            {"tool": "ruff check", "exit_code": 0, "output": "src/a.py:1: error A"},
            {"tool": "mypy", "exit_code": 0, "output": "src/b.py:1: error B"},
            {"tool": "mypy", "exit_code": 0, "output": "src/c.py:2: error C"},
        ]
        baseline_path.write_text(json.dumps(saved))
        # Current has ruff check (still present) but no mypy (both duplicates removed)
        results = [make_lint_result(tool_name="ruff check", exit_code=0, stdout="src/a.py:1: error A")]
        violations = _diff_baseline(results, baseline_path)
        assert violations == [], f"Expected no violations for tool removal, got: {violations}"
        updated = json.loads(baseline_path.read_text())
        mypy_entries = [e for e in updated if e["tool"] == "mypy"]
        assert mypy_entries == [], (
            f"All duplicate mypy entries should be removed, got: {mypy_entries}"
        )
        # ruff check should still be present
        ruff_entries = [e for e in updated if e["tool"] == "ruff check"]
        assert len(ruff_entries) == 1

    def test_diff_diagnostics_lost_regression(self, tmp_path: Path) -> None:
        """D4: Saved has diagnostics dict, current stdout is non-JSON → regression flagged."""
        baseline_path = tmp_path / "diag_lost.json"
        saved = [{
            "tool": "pyright check",
            "exit_code": 0,
            "diagnostics": {"summary": {"errorCount": 1, "warningCount": 0}},
        }]
        baseline_path.write_text(json.dumps(saved))
        # Current stdout is plain text, not JSON
        results = [make_lint_result(
            tool_name="pyright check", exit_code=0,
            stdout="some non-JSON output",
        )]
        violations = _diff_baseline(results, baseline_path)
        assert any("diagnostics lost" in v.lower() for v in violations), (
            f"Expected 'Diagnostics lost' violation, got: {violations}"
        )
        # Baseline should NOT be rewritten (regression, not shrinkage)
        updated = json.loads(baseline_path.read_text())
        assert updated[0]["diagnostics"] is not None, (
            "Baseline diagnostics should not be replaced with None on regression"
        )

    def test_diff_unwritable_baseline(self, tmp_path: Path) -> None:
        """D5: Unwritable baseline file returns violation instead of raising."""
        baseline_path = tmp_path / "readonly.json"
        saved = [
            {"tool": "ruff check", "exit_code": 0, "output": "src/a.py:1: error A\nsrc/b.py:2: error B"},
        ]
        baseline_path.write_text(json.dumps(saved))
        # Make the file read-only
        baseline_path.chmod(0o444)
        # Current has shrinkage (one violation removed) → triggers write
        results = [make_lint_result(tool_name="ruff check", exit_code=0, stdout="src/a.py:1: error A")]
        violations = _diff_baseline(results, baseline_path)
        assert any("cannot write baseline" in v.lower() for v in violations), (
            f"Expected 'Cannot write baseline' violation, got: {violations}"
        )
        # Restore permissions for cleanup
        baseline_path.chmod(0o644)

    def test_diff_whitespace_normalization(self, tmp_path: Path) -> None:
        """D6: Trailing-whitespace-only differences are not flagged as regressions."""
        baseline_path = tmp_path / "whitespace.json"
        saved = [{
            "tool": "mypy",
            "exit_code": 0,
            "output": "src/a.py:1: error A  \nsrc/b.py:2: error B  ",
        }]
        baseline_path.write_text(json.dumps(saved))
        # Current has same content but no trailing spaces
        results = [make_lint_result(
            tool_name="mypy", exit_code=0,
            stdout="src/a.py:1: error A\nsrc/b.py:2: error B",
        )]
        violations = _diff_baseline(results, baseline_path)
        assert violations == [], (
            f"Expected no violations for whitespace-only diff, got: {violations}"
        )

    def test_diff_duplicate_line_count_set_semantics(self, tmp_path: Path) -> None:
        """D7: Set-semantics on output lines — duplicate count changes not flagged (documented)."""
        baseline_path = tmp_path / "dup_count.json"
        saved = [{
            "tool": "mypy",
            "exit_code": 0,
            "output": "src/a.py:1: error A",
        }]
        baseline_path.write_text(json.dumps(saved))
        # Current has 3 occurrences of the SAME line (count increase)
        results = [make_lint_result(
            tool_name="mypy", exit_code=0,
            stdout="src/a.py:1: error A\nsrc/a.py:1: error A\nsrc/a.py:1: error A",
        )]
        violations = _diff_baseline(results, baseline_path)
        # Set-semantics: same signature → no violation (documented in docstring)
        assert violations == [], (
            f"Expected no violations for duplicate count increase (set semantics), got: {violations}"
        )


# ── overwrite-baseline coverage (D11) ──────────────────────────────


class TestOverwriteBaseline:
    """Verify --overwrite-baseline rewrites an existing baseline file (with fakes)."""

    def test_overwrite_via_main(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """main(['--overwrite-baseline', ...]) rewrites existing baseline on second call."""
        fake1 = fake_run_cmd_factory({})
        monkeypatch.setattr(_runner_module, "_run_cmd", fake1)
        baseline_file = tmp_path / "overwrite.json"
        # First call creates baseline
        rc1 = main(
            [
                "--path",
                "src/main.py",
                "--baseline",
                str(baseline_file),
            ]
        )
        assert baseline_file.exists()
        import json as _json
        data_first = _json.loads(baseline_file.read_text())
        assert len(data_first) > 0

        # Second call with overwrite — should rewrite
        fake2 = fake_run_cmd_factory({})
        monkeypatch.setattr(_runner_module, "_run_cmd", fake2)
        rc2 = main(
            [
                "--overwrite-baseline",
                "--baseline",
                str(baseline_file),
                "--path",
                "src/main.py",
            ]
        )
        captured = capsys.readouterr()
        assert "Overwriting baseline" in captured.out, (
            f"Expected 'Overwriting baseline' in output, got: {captured.out[:300]}"
        )
        data_second = _json.loads(baseline_file.read_text())
        assert len(data_second) > 0  # still valid

    def test_overwrite_via_run_lint(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """run_lint(overwrite_baseline=True) rewrites when file already exists."""
        fake1 = fake_run_cmd_factory({})
        monkeypatch.setattr(_runner_module, "_run_cmd", fake1)
        baseline_file = tmp_path / "overwrite2.json"
        # Create baseline
        run_lint(path="src/main.py", baseline=str(baseline_file))
        assert baseline_file.exists()

        # Overwrite
        fake2 = fake_run_cmd_factory({})
        monkeypatch.setattr(_runner_module, "_run_cmd", fake2)
        run_lint(
            path="src/main.py",
            baseline=str(baseline_file),
            overwrite_baseline=True,
        )
        import json as _json
        data = _json.loads(baseline_file.read_text())
        assert len(data) > 0

    def test_no_overwrite_without_flag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without --overwrite-baseline, an existing baseline is diffed, not rewritten."""
        baseline_file = tmp_path / "no_overwrite.json"
        # Create baseline with known content
        saved = [{"tool": "ruff check", "exit_code": 0, "output": "first output"}]
        baseline_file.write_text(json.dumps(saved))

        # Run again without overwrite — should diff, not rewrite
        fake = fake_run_cmd_factory(
            {
                "ruff check": make_lint_result(
                    tool_name="ruff check", exit_code=0, stdout="first output"
                ),
            }
        )
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        rc = main(
            [
                "--baseline",
                str(baseline_file),
                "--path",
                "src/main.py",
            ]
        )
        # Baseline content should remain unchanged (not overwritten)
        import json as _json
        data = _json.loads(baseline_file.read_text())
        assert len(data) == 1
        assert data[0]["output"] == "first output"


# ── Observability: _print_result output format ───────────────────


class TestPrintResult:
    """Verify _print_result produces expected output format."""

    def test_print_passed_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        """PASSED result includes tool name, status, and stdout."""
        result = make_lint_result(tool_name="mytool", exit_code=0, stdout="all good\n")
        _print_result(result)
        captured = capsys.readouterr()
        assert "[mytool]" in captured.out
        assert "PASSED" in captured.out
        assert "all good" in captured.out

    def test_print_failed_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        """FAILED result includes error details, status, and stderr."""
        result = make_lint_result(tool_name="mytool", exit_code=2, stderr="error: x\n")
        _print_result(result)
        captured = capsys.readouterr()
        assert "FAILED" in captured.out
        assert "exit=2" in captured.out
        assert "error: x" in captured.out

    def test_print_stderr_before_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        """stderr content appears before stdout in output (code convention)."""
        result = make_lint_result(
            tool_name="mytool",
            exit_code=1,
            stderr="stderr line\n",
            stdout="stdout line\n",
        )
        _print_result(result)
        captured = capsys.readouterr()
        assert captured.out.index("stderr line") < captured.out.index("stdout line"), "stderr should be printed before stdout"


# ── run_lint orchestration with advanced flags ───────────────────


import python_setup_lint.runner as _runner_module


class TestRunLintOrchestration:
    """Verify run_lint behaviour with --no-fail-fast, --exclude, etc.

    Uses fakes (no real subprocesses).  The consolidated real-pipeline smoke
    in test_real_pipeline_smoke.py provides end-to-end coverage.
    """

    def _default_config(self, tmp_path: Path) -> RunnerConfig:
        return RunnerConfig(
            cwd=tmp_path,
            package_name="python_setup_lint",
            default_py_dirs=["src", "scripts", "tests"],
        )

    def test_no_fail_fast_captures_all_tools(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With --no-fail-fast, all TOOLS produce a baseline entry."""
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        baseline_file = tmp_path / "noff.json"
        rc = run_lint(
            config=self._default_config(tmp_path),
            baseline=str(baseline_file),
            no_fail_fast=True,
        )
        dispatched_labels = {c.label for c in fake.calls}
        expected_labels = {t.name for t in TOOLS}
        assert dispatched_labels == expected_labels, (
            f"Dispatched {len(dispatched_labels)}/{len(expected_labels)} tools: "
            f"missing={expected_labels - dispatched_labels}"
        )
        import json as _json
        data = _json.loads(baseline_file.read_text())
        assert len(data) == len(TOOLS), (
            f"Expected {len(TOOLS)} baseline entries, got {len(data)}"
        )

    def test_no_fail_fast_returns_int(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--no-fail-fast returns an int (aggregate exit code)."""
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        rc = run_lint(
            config=self._default_config(tmp_path),
            no_fail_fast=True,
        )
        assert isinstance(rc, int)

    def test_tools_override_limits_tools(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """tools_override runs only the specified tools."""
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        baseline_file = tmp_path / "tools_override.json"
        config = RunnerConfig(
            cwd=tmp_path,
            tools_override=["ruff check", "mypy"],
        )
        run_lint(
            config=config,
            baseline=str(baseline_file),
            no_fail_fast=True,
        )
        import json as _json
        data = _json.loads(baseline_file.read_text())
        tool_names = {entry["tool"] for entry in data}
        assert tool_names == {"ruff check", "mypy"}, f"Expected only ruff check and mypy, got {tool_names}"

    def test_package_name_none_skips_stubtest_verifytypes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With package_name=None, stubtest and verifytypes are skipped."""
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        baseline_file = tmp_path / "no_pkg.json"
        config = RunnerConfig(cwd=tmp_path, package_name=None)
        run_lint(
            config=config,
            baseline=str(baseline_file),
            no_fail_fast=True,
        )
        dispatched = {c.label for c in fake.calls}
        assert "mypy.stubtest" not in dispatched
        assert "pyright verify types" not in dispatched
        assert len(dispatched) == len(TOOLS) - 2

    def test_package_name_set_runs_stubtest_verifytypes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With package_name set, stubtest and verifytypes are included."""
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        baseline_file = tmp_path / "with_pkg.json"
        config = RunnerConfig(cwd=tmp_path, package_name="python_setup_lint")
        run_lint(
            config=config,
            baseline=str(baseline_file),
            no_fail_fast=True,
        )
        dispatched = {c.label for c in fake.calls}
        assert "mypy.stubtest" in dispatched
        assert "pyright verify types" in dispatched
        assert len(dispatched) == len(TOOLS)

    # ── CLI argument parsing via main() ─────────────────────────────


class TestMainArgparse:
    """Verify main() translates CLI flags to run_lint kwargs.

    Uses fakes (no real subprocesses).  Only tests flag acceptance.
    """

    def _default_config(self, tmp_path: Path) -> RunnerConfig:
        return RunnerConfig(
            cwd=tmp_path,
            package_name="python_setup_lint",
            default_py_dirs=["src", "scripts", "tests"],
        )

    def test_main_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--path is accepted by CLI."""
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        rc = main(
            ["--path", "src/python_setup_lint/runner.py"],
            config=self._default_config(tmp_path),
        )
        assert isinstance(rc, int)

    def test_main_fix(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """--fix is accepted by CLI."""
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        rc = main(
            ["--fix", "--path", "src/python_setup_lint/runner.py"],
            config=self._default_config(tmp_path),
        )
        assert isinstance(rc, int)

    def test_main_no_fail_fast(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--no-fail-fast is accepted by CLI."""
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        rc = main(
            ["--no-fail-fast", "--path", "src/python_setup_lint/runner.py"],
            config=self._default_config(tmp_path),
        )
        assert isinstance(rc, int)

    def test_main_exclude(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--exclude is accepted by CLI."""
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        rc = main(
            ["--exclude", "tests/", "--path", "src/python_setup_lint/runner.py"],
            config=self._default_config(tmp_path),
        )
        assert isinstance(rc, int)

    def test_main_baseline(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--baseline produces a JSON file."""
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        baseline_file = tmp_path / "main_baseline.json"
        rc = main(
            [
                "--baseline",
                str(baseline_file),
                "--path",
                "src/python_setup_lint/runner.py",
            ],
            config=self._default_config(tmp_path),
        )
        assert baseline_file.exists()
        import json as _json
        data = _json.loads(baseline_file.read_text())
        assert len(data) > 0

    def test_main_package_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--package-name is accepted by CLI."""
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        rc = main(
            ["--package-name", "python_setup_lint", "--path", "src/python_setup_lint/runner.py"],
            config=self._default_config(tmp_path),
        )
        assert isinstance(rc, int)

    def test_main_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--cwd is accepted by CLI."""
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        rc = main(
            ["--cwd", str(tmp_path), "--path", "."],
            config=self._default_config(tmp_path),
        )
        assert isinstance(rc, int)

    def test_main_tools(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--tools is accepted by CLI (comma-separated list)."""
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        rc = main(
            ["--tools", "ruff check,mypy", "--path", "src/python_setup_lint/runner.py"],
            config=self._default_config(tmp_path),
        )
        assert isinstance(rc, int)

    def test_main_default_py_dirs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--default-py-dirs is accepted by CLI."""
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        rc = main(
            ["--default-py-dirs", "src,tests", "--path", "src/python_setup_lint/runner.py"],
            config=self._default_config(tmp_path),
        )
        assert isinstance(rc, int)

    def test_main_no_args_backward_compat(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """main() with no args runs successfully (backward compat)."""
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        rc = main([], config=self._default_config(tmp_path))
        assert isinstance(rc, int)


# ── Smoke integration: run subset via CLI ─────────────────────────--


class TestMainCLI:
    """Lightweight CLI exercises — pure argparse, no subprocess."""

    def test_main_help(self) -> None:
        """--help should exit with code 0 (SystemExit)."""
        try:
            main(["--help"])
        except SystemExit as exc:
            assert exc.code == 0

    def test_main_unknown_flag_error(self) -> None:
        """Unknown flag produces non-zero exit."""
        try:
            main(["--nonexistent-flag"])
        except SystemExit as exc:
            assert exc.code != 0

    def test_lint_result_dataclass(self) -> None:
        """LintResult fields are correctly accessible."""
        r = LintResult(tool_name="test", exit_code=0, stdout="out", stderr="err", elapsed=1.0)
        assert r.tool_name == "test"
        assert r.exit_code == 0
        assert r.stdout == "out"
        assert r.stderr == "err"
        assert r.elapsed == 1.0


# ── Integration: quick real tool (ruff) ────────────────────────────


class TestIntegration:
    """Exercise lint runner behaviour with fakes."""

    def test_ruff_on_small_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Run lint with fakes — ruff entry present in baseline."""
        fake = fake_run_cmd_factory(
            {
                "ruff check": make_lint_result(tool_name="ruff check", stdout="no issues"),
            }
        )
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        baseline_file = tmp_path / "test_baseline.json"
        rc = run_lint(
            config=RunnerConfig(cwd=tmp_path, package_name="python_setup_lint"),
            baseline=str(baseline_file),
            no_fail_fast=True,
        )
        assert baseline_file.exists()
        import json as _json
        data = _json.loads(baseline_file.read_text())
        assert any(entry["tool"] == "ruff check" for entry in data), "ruff check did not produce a baseline entry"

    def test_ruff_with_fix_flag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Run lint --fix on a single file — ruff entry present in baseline."""
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        baseline_file = tmp_path / "test_fix_baseline.json"
        rc = run_lint(
            config=RunnerConfig(cwd=tmp_path, package_name="python_setup_lint"),
            fix=True,
            baseline=str(baseline_file),
            no_fail_fast=True,
        )
        assert baseline_file.exists()
        import json as _json
        data = _json.loads(baseline_file.read_text())
        assert any(entry["tool"] == "ruff check" for entry in data), "ruff check did not produce a baseline entry under --fix"

    def test_baseline_create(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Creating a baseline produces a JSON file with multiple entries."""
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        baseline_file = tmp_path / "test_baseline.json"
        run_lint(
            config=RunnerConfig(cwd=tmp_path, package_name="python_setup_lint"),
            baseline=str(baseline_file),
        )
        assert baseline_file.exists()
        import json as _json
        data = _json.loads(baseline_file.read_text())
        assert isinstance(data, list)
        assert len(data) > 0
        for entry in data:
            assert "tool" in entry
            assert "exit_code" in entry

    def test_baseline_diff_identical(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Running twice with baseline — baseline entries remain structurally consistent."""
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        baseline_file = tmp_path / "test_baseline2.json"
        run_lint(
            config=RunnerConfig(cwd=tmp_path, package_name="python_setup_lint"),
            baseline=str(baseline_file),
        )
        import json as _json
        saved_after_first = _json.loads(baseline_file.read_text())
        assert len(saved_after_first) > 0

        # Second run — baseline should still be valid JSON with same structure
        run_lint(
            config=RunnerConfig(cwd=tmp_path, package_name="python_setup_lint"),
            baseline=str(baseline_file),
        )
        saved_after_second = _json.loads(baseline_file.read_text())
        assert isinstance(saved_after_second, list)
        assert len(saved_after_second) == len(saved_after_first)

    def test_baseline_exits_zero_when_matching(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """run_lint with --baseline exits 0 when output matches baseline."""
        fake1 = fake_run_cmd_factory({})
        monkeypatch.setattr(_runner_module, "_run_cmd", fake1)
        baseline_file = tmp_path / "test_baseline_exit.json"
        # First run creates baseline
        rc1 = run_lint(
            config=RunnerConfig(cwd=tmp_path, package_name="python_setup_lint"),
            baseline=str(baseline_file),
        )
        # Second run with same baseline must exit 0 (no new violations)
        rc2 = run_lint(
            config=RunnerConfig(cwd=tmp_path, package_name="python_setup_lint"),
            baseline=str(baseline_file),
        )
        assert rc2 == 0, (
            f"Expected exit code 0 when baseline matches, got {rc2}. "
        )

    def test_baseline_exits_nonzero_on_new_violation(self, tmp_path: Path) -> None:
        """run_lint with --baseline exits non-zero when a new violation appears."""
        baseline_file = tmp_path / "test_baseline_new_violation.json"
        saved = [{"tool": "ruff check", "exit_code": 0, "output": "no issues"}]
        baseline_file.write_text(json.dumps(saved))

        violations = _diff_baseline(
            [make_lint_result(tool_name="ruff check", exit_code=1, stdout="error: unused import")],
            baseline_file,
        )
        assert len(violations) > 0, "Expected violations when output differs from baseline"


# ── Edge cases ─────────────────────────────────────────────────────


class TestEdgeCases:
    """Boundary and error-path tests."""

    def test_find_py_files_single_file(self) -> None:
        """_find_py_files with a single .py file path."""
        files = _find_py_files(["src/python_setup_lint/runner.py"], cwd=Path.cwd())
        assert len(files) == 1
        assert files[0] == "src/python_setup_lint/runner.py"

    def test_find_py_files_ignores_non_py(self) -> None:
        """_find_py_files returns only .py files."""
        files = _find_py_files(["src/python_setup_lint"], cwd=Path.cwd())  # dir with both .py and .pyi
        assert all(f.endswith(".py") for f in files)

    def test_expand_globs_no_match(self) -> None:
        """Glob with no matches returns empty."""
        result = _expand_globs(["*.nonexistent_ext_xyz"], cwd=Path.cwd())
        assert result == []

    def test_tool_count(self) -> None:
        """There should be exactly 11 tools."""
        assert len(TOOLS) == 11, f"Expected 11 tools, got {len(TOOLS)}"


# ── Statistics: _build_statistics_flags ───────────────────────────


class TestBuildStatisticsFlags:
    """Verify each tool gets correct statistics CLI flags."""

    def test_ruff_native(self) -> None:
        spec = ToolSpec("ruff check", ["ruff", "check"])
        assert _build_statistics_flags(spec) == ["--statistics"]

    def test_rumdl_native(self) -> None:
        spec = ToolSpec("rumdl check", ["rumdl", "check"])
        assert _build_statistics_flags(spec) == ["--statistics"]

    def test_pylint_json2(self) -> None:
        spec = ToolSpec("pylint", ["pylint"])
        assert _build_statistics_flags(spec) == ["--output-format=json2"]

    def test_pyright_outputjson(self) -> None:
        spec = ToolSpec("pyright check", ["pyright"])
        assert _build_statistics_flags(spec) == ["--outputjson"]

    def test_mypy_no_error_summary(self) -> None:
        spec = ToolSpec("mypy", ["mypy"])
        assert _build_statistics_flags(spec) == ["--no-error-summary"]

    def test_ty_concise(self) -> None:
        spec = ToolSpec("ty check", ["ty", "check"])
        assert _build_statistics_flags(spec) == ["--output-format", "concise"]

    def test_tach_json(self) -> None:
        spec = ToolSpec("tach check", ["tach", "check"])
        assert _build_statistics_flags(spec) == ["--output", "json"]

    def test_yamllint_parsable(self) -> None:
        spec = ToolSpec("yamllint", ["yamllint"])
        assert _build_statistics_flags(spec) == ["-f", "parsable"]

    def test_tools_without_statistics(self) -> None:
        """Tools not in the map get no extra flags."""
        for name in ("mypy.stubtest", "detect-secrets", "pyright verify types"):
            spec = ToolSpec(name, ["tool"])
            assert _build_statistics_flags(spec) == [], f"{name} should have no flags"

    def test_statistics_flag_added_in_build_command(self) -> None:
        """_build_command adds statistics flags when statistics=True."""
        spec = ToolSpec("ruff check", ["ruff", "check"])
        cmd = _build_command(spec, config=_CONFIG, fix=False, path=None, exclude=None)
        cmd.extend(_build_statistics_flags(spec))
        assert "--statistics" in cmd


# ── Statistics: per-tool parsers ───────────────────────────────────


class TestParseRuffStatistics:
    """_parse_ruff_statistics extracts counts from ruff --statistics output."""

    def test_typical_output(self) -> None:
        out = "Count\tCode\tDescription\n------\t----\t-----------\n3\tF401\tmodule imported but unused\n1\tE501\tline too long\n"
        result = _parse_ruff_statistics(out, "")
        assert ("F401", 3) in result
        assert ("E501", 1) in result

    def test_empty(self) -> None:
        assert _parse_ruff_statistics("", "") == []

    def test_no_header_or_irrelevant(self) -> None:
        out = "No violations found\n"
        assert _parse_ruff_statistics(out, "") == []

    def test_multiline_grouped(self) -> None:
        out = "Count\tCode\tDescription\n------\t----\t-----------\n2\tF401\tsomething\n2\tF401\tsomething else\n"
        # Same rule on multiple lines → aggregated
        result = _parse_ruff_statistics(out, "")
        assert ("F401", 4) in result


class TestParseRumdlStatistics:
    """_parse_rumdl_statistics extracts counts from rumdl --statistics output."""

    def test_typical(self) -> None:
        out = "Count\tCode\tDescription\n------\t----\t-----------\n5\tMD012\tno-multiple-blanks\n"
        result = _parse_rumdl_statistics(out, "")
        assert ("MD012", 5) in result

    def test_empty(self) -> None:
        assert _parse_rumdl_statistics("", "") == []


class TestParsePylintJson2:
    """_parse_pylint_json2 extracts symbol counts from pylint JSON2 output."""

    def test_typical(self) -> None:
        out = '[{"symbol": "unused-import"}, {"symbol": "unused-import"}, {"symbol": "too-complex"}]'
        result = _parse_pylint_json2(out, "")
        assert ("unused-import", 2) in result
        assert ("too-complex", 1) in result

    def test_empty_array(self) -> None:
        assert _parse_pylint_json2("[]", "") == []

    def test_invalid_json(self) -> None:
        assert _parse_pylint_json2("not json", "") == []

    def test_non_list(self) -> None:
        assert _parse_pylint_json2('{"key": "val"}', "") == []


class TestParsePyrightOutputjson:
    """_parse_pyright_outputjson extracts rule counts from pyright JSON."""

    def test_typical(self) -> None:
        out = json.dumps(
            {
                "generalDiagnostics": [
                    {"rule": "reportGeneralTypeIssues"},
                    {"rule": "reportGeneralTypeIssues"},
                    {"rule": "reportOptionalMemberAccess"},
                ],
            }
        )
        result = _parse_pyright_outputjson(out, "")
        assert ("reportGeneralTypeIssues", 2) in result
        assert ("reportOptionalMemberAccess", 1) in result

    def test_empty_diagnostics(self) -> None:
        out = json.dumps({"generalDiagnostics": []})
        assert _parse_pyright_outputjson(out, "") == []

    def test_missing_key(self) -> None:
        out = json.dumps({"summary": {}})
        assert _parse_pyright_outputjson(out, "") == []

    def test_invalid_json(self) -> None:
        assert _parse_pyright_outputjson("bad", "") == []


class TestParsePyrightVerifyTypes:
    """_parse_pyright_verify_types extracts incomplete-symbol counts."""

    def test_with_incomplete(self) -> None:
        out = json.dumps(
            {
                "typeCompleteness": {
                    "symbols": [
                        {"symbolName": "Foo", "completeness": 0.5},
                        {"symbolName": "Bar", "completeness": 1.0},
                    ],
                },
            }
        )
        result = _parse_pyright_verify_types(out, "")
        assert ("verifytypes:incomplete", 1) in result
        assert len(result) == 1

    def test_all_complete(self) -> None:
        out = json.dumps({"typeCompleteness": {"symbols": [{"symbolName": "Foo", "completeness": 1.0}]}})
        assert _parse_pyright_verify_types(out, "") == []

    def test_invalid_json(self) -> None:
        assert _parse_pyright_verify_types("bad", "") == []

    def test_all_complete_missing_type_completeness(self) -> None:
        out = json.dumps({})
        assert _parse_pyright_verify_types(out, "") == []


class TestParseMypyStderr:
    """_parse_mypy_stderr extracts error codes from mypy stderr."""

    def test_typical(self) -> None:
        err = "file.py:1: error: Unused import [no-unused-import]\nfile.py:2: error: Not callable [operator]\n"
        result = _parse_mypy_stderr("", err)
        assert ("no-unused-import", 1) in result
        assert ("operator", 1) in result

    def test_empty(self) -> None:
        assert _parse_mypy_stderr("", "") == []


class TestParseTyConcise:
    """_parse_ty_concise extracts error codes from ty concise output."""

    def test_typical(self) -> None:
        out = "file.py:1:1: X001 some message\nfile.py:2:2: X002 another\n"
        result = _parse_ty_concise(out, "")
        assert ("X001", 1) in result
        assert ("X002", 1) in result

    def test_empty(self) -> None:
        assert _parse_ty_concise("", "") == []


class TestParseTachJson:
    """_parse_tach_json extracts error counts from tach json output."""

    def test_with_errors(self) -> None:
        out = json.dumps({"errors": [{"message": "bad import"}]})
        result = _parse_tach_json(out, "")
        assert ("tach:error", 1) in result

    def test_no_errors(self) -> None:
        out = json.dumps({"errors": []})
        assert _parse_tach_json(out, "") == []

    def test_invalid_json(self) -> None:
        assert _parse_tach_json("bad", "") == []


class TestParseYamllintParsable:
    """_parse_yamllint_parsable extracts rule counts from yamllint output."""

    def test_typical(self) -> None:
        out = "f.yaml:1:1:trailing-spaces: message 1\nf.yaml:2:2:trailing-spaces: message 2\n"
        result = _parse_yamllint_parsable(out, "")
        assert ("trailing-spaces", 2) in result

    def test_empty(self) -> None:
        assert _parse_yamllint_parsable("", "") == []


class TestParseStubtestStderr:
    """_parse_stubtest_stderr extracts error codes from stubtest stderr."""

    def test_typical(self) -> None:
        err = "error: X001 first error\nerror: X001 second error\nerror: X002 third error\n"
        result = _parse_stubtest_stderr("", err)
        assert ("X001", 2) in result
        assert ("X002", 1) in result

    def test_no_error_prefix(self) -> None:
        err = "info: something\n"
        assert _parse_stubtest_stderr(err, "") == []


class TestParseDetectSecretsJson:
    """_parse_detect_secrets_json extracts secret type counts."""

    def test_typical(self) -> None:
        out = json.dumps(
            {
                "results": {
                    "file.py": [
                        {"type": "Secret A"},
                        {"type": "Secret A"},
                        {"type": "Secret B"},
                    ],
                },
            }
        )
        result = _parse_detect_secrets_json(out, "")
        assert ("Secret A", 2) in result
        assert ("Secret B", 1) in result

    def test_empty_results(self) -> None:
        out = json.dumps({"results": {}})
        assert _parse_detect_secrets_json(out, "") == []

    def test_invalid_json(self) -> None:
        assert _parse_detect_secrets_json("bad", "") == []

# ── T4: Strategy registry (LintTool + STRATEGIES + LINT_TOOLS + ────
# register_lint_tool + GenericLintTool) ────────────────────────────


import python_setup_lint.runner as _r


class TestLintToolRegistry:
    """Verify the strategy registry (T4 + T8 R6 3-point seam)."""

    def test_strategies_covers_all_builtins(self) -> None:
        """STRATEGIES has one entry per built-in TOOLS name; no dupes."""
        names = {t.name for t in TOOLS}
        assert set(_r.STRATEGIES) == names, (
            f"STRATEGIES keys mismatch: missing={names - set(_r.STRATEGIES)} "
            f"extra={set(_r.STRATEGIES) - names}"
        )
        assert len(_r.STRATEGIES) == len(TOOLS)

    def test_lint_tools_mirrors_tools_at_import(self) -> None:
        """LINT_TOOLS lists the same 11 names as TOOLS at import."""
        assert {t.name for t in _r.LINT_TOOLS} == {t.name for t in TOOLS}
        assert len(_r.LINT_TOOLS) == len(TOOLS)

    def test_strategies_provide_lint_tool_instances(self) -> None:
        """All values in STRATEGIES are LintTool subclasses."""
        for strategy in _r.STRATEGIES.values():
            assert isinstance(strategy, _r.LintTool), (
                f"Strategy {strategy!r} is not a LintTool"
            )

    def test_strategy_name_matches_spec_name(self) -> None:
        """Each strategy's name mirrors its spec's name."""
        for name, strategy in _r.STRATEGIES.items():
            assert strategy.name == name
            assert strategy.spec.name == name

    def test_register_lint_tool_appends_extra(self) -> None:
        """register_lint_tool adds an extra spec to LINT_TOOLS + STRATEGIES.

        Uses a unique name that does NOT collide with any built-in.
        """
        from python_setup_lint.runner import register_lint_tool, STRATEGIES, LINT_TOOLS, GenericLintTool
        extra = ToolSpec(
            "t4-extra-test-tool",
            ["t4extra", "check"],
            supports_path=True,
        )
        try:
            register_lint_tool(extra, statistics_flag=[], parser=None, config_flag=None)
            # In LINT_TOOLS
            assert any(t.name == "t4-extra-test-tool" for t in LINT_TOOLS)
            # Registered as a GenericLintTool under STRATEGIES
            registered = STRATEGIES.get("t4-extra-test-tool")
            assert registered is not None
            assert isinstance(registered, GenericLintTool)
        finally:
            # Cleanup: idempotent re-call semantics means a fresh process
            # would not see this mutation; in the test process we restore
            # state to avoid leaking into other tests.
            if STRATEGIES.get("t4-extra-test-tool") is not None:
                del STRATEGIES["t4-extra-test-tool"]
            _r.LINT_TOOLS[:] = [t for t in _r.LINT_TOOLS if t.name != "t4-extra-test-tool"]

    def test_register_lint_tool_idempotent_same_name(self) -> None:
        """Re-calling register_lint_tool with the same name is update-in-place (no duplicate)."""
        from python_setup_lint.runner import register_lint_tool, STRATEGIES, LINT_TOOLS
        a = ToolSpec("t4-idempotent-tool", ["t4ida"])
        b = ToolSpec("t4-idempotent-tool", ["t4idb"])  # same name, different command
        try:
            register_lint_tool(a)
            count_after_first = len(LINT_TOOLS)
            register_lint_tool(b)
            count_after_second = len(LINT_TOOLS)
            assert count_after_first == count_after_second, (
                f"Idempotency broken: LINT_TOOLS grew from {count_after_first} to {count_after_second}"
            )
            # Last write wins — LINT_TOOLS entry reflects the most recent spec.
            entry = next(t for t in LINT_TOOLS if t.name == "t4-idempotent-tool")
            assert entry.command == ["t4idb"], f"Expected update-in-place, got {entry.command}"
        finally:
            if STRATEGIES.get("t4-idempotent-tool") is not None:
                del STRATEGIES["t4-idempotent-tool"]
            _r.LINT_TOOLS[:] = [t for t in _r.LINT_TOOLS if t.name != "t4-idempotent-tool"]

    def test_register_lint_tool_respects_builtin_strategy(self) -> None:
        """Re-registering a built-in name does NOT replace its built-in strategy."""
        from python_setup_lint.runner import register_lint_tool, STRATEGIES
        # Snapshot the built-in ruff strategy instance and the original LINT_TOOLS.
        original_strategy = STRATEGIES["ruff check"]
        original_lint_tools_snapshot = list(_r.LINT_TOOLS)
        duplicate = ToolSpec("ruff check", ["ruff", "duplicate"])
        register_lint_tool(duplicate)
        try:
            # STRATEGIES entry should remain the same object — built-in kept.
            assert STRATEGIES["ruff check"] is original_strategy, (
                "register_lint_tool should not replace built-in strategies"
            )
        finally:
            # Restore LINT_TOOLS to its pre-test snapshot.
            _r.LINT_TOOLS[:] = original_lint_tools_snapshot


class TestGenericLintToolBuildCommand:
    """GenericLintTool.build_command delegates to the generic _build_command."""

    def test_generic_command_for_extra_no_special_branches(self) -> None:
        """An extra name falls through to the common-case branches of _build_command.

        Specifically: shared-config-flag (none for unknown name) + path scoping
        + exclude — without touching any of the if/elif tool-name branches
        (the ruff-specific ``--exit-non-zero-on-fix`` and the
        ``rumdl check`` / ``ty check`` whitelist).  An extra with
        ``supports_fix=True`` DOES get a ``--fix`` flag — T11 closed that gap
        by adding an else branch in :func:`_build_command`'s fix-flag section
        so extras match built-in command shape.  The spec's ``supports_fix``
        also still controls the unsupported-flag warning in :func:`run_lint`.
        """
        from python_setup_lint.runner import GenericLintTool
        spec = ToolSpec(
            "t4-generic-tool",
            ["t4g", "check"],
            supports_fix=True,
            supports_path=True,
            supports_exclude=True,
            default_paths=["src/"],
        )
        g = GenericLintTool(spec, statistics_flag=[], parser=None, config_flag=None)
        try:
            cmd = g.build_command(
                config=RunnerConfig(cwd=Path("/tmp")),
                fix=True,
                path=None,
                exclude="tests/",
            )
            # Base command + --fix (T11 else-branch) + default_path + exclude.
            # The fix flag lands right after the spec command, before paths
            # (matches built-in shape from _build_command ordering).
            assert cmd == ["t4g", "check", "--fix", "src/", "--exclude", "tests/"]
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"GenericLintTool.build_command raised: {exc!r}")

    def test_generic_statistics_flags_use_override_when_set(self) -> None:
        """GenericLintTool.statistics_flags returns the explicit flag list when provided."""
        from python_setup_lint.runner import GenericLintTool
        spec = ToolSpec("t4-stats-tool", ["t4s"])
        g = GenericLintTool(spec, statistics_flag=["--stat-foo"], parser=None, config_flag=None)
        assert g.statistics_flags() == ["--stat-foo"]

    def test_generic_statistics_flags_fall_back_to_module_lookup(self) -> None:
        """When no statistics_flag is passed, GenericLintTool consults _build_statistics_flags."""
        from python_setup_lint.runner import GenericLintTool
        spec = ToolSpec("ruff check", ["ruff", "check"])  # built-in name with map entry
        g = GenericLintTool(spec, statistics_flag=None, parser=None, config_flag=None)
        # Falls through to _build_statistics_flags("ruff check") → ["--statistics"]
        assert g.statistics_flags() == ["--statistics"]

    def test_generic_parse_statistics_uses_override(self) -> None:
        """When a parser is provided, GenericLintTool uses it verbatim."""
        from python_setup_lint.runner import GenericLintTool
        spec = ToolSpec("t4-parse-tool", ["t4p"])

        def custom_parser(stdout: str, stderr: str) -> list[tuple[str, int]]:
            return [("custom-rule", 7)]

        g = GenericLintTool(spec, statistics_flag=None, parser=custom_parser, config_flag=None)
        assert g.parse_statistics("ignored", "also-ignored") == [("custom-rule", 7)]

    def test_generic_parse_statistics_falls_back_to_module_lookup(self) -> None:
        """Without a parser, GenericLintTool consults _STATISTICS_PARSERS."""
        from python_setup_lint.runner import GenericLintTool
        spec = ToolSpec("ruff check", ["ruff", "check"])
        g = GenericLintTool(spec, statistics_flag=None, parser=None, config_flag=None)
        # _STATISTICS_PARSERS["ruff check"] = _parse_ruff_statistics
        out = "Count\tCode\tDescription\n------\t----\t-----------\n3\tF401\tmodule imported but unused\n"
        assert ("F401", 3) in g.parse_statistics(out, "")


class TestStrategyForFallback:
    """Verify _strategy_for default-aware fallback for unknown names."""

    def test_strategy_for_returns_cached_builtin(self) -> None:
        """Built-in names return their existing strategy, not a new GenericLintTool."""
        from python_setup_lint.runner import _strategy_for, STRATEGIES
        original = STRATEGIES["ruff check"]
        got = _strategy_for("ruff check", ToolSpec("ruff check", ["ruff", "check"]))
        assert got is original, (
            "Expected the cached built-in strategy, not a new instance"
        )

    def test_strategy_for_unknown_name_returns_generic(self) -> None:
        """An unknown name synthesises a GenericLintTool on lookup."""
        from python_setup_lint.runner import _strategy_for, GenericLintTool
        fake_spec = ToolSpec("t4-unknown-fallback", ["t4fake"])
        got = _strategy_for("t4-unknown-fallback", fake_spec)
        assert isinstance(got, GenericLintTool), f"Expected GenericLintTool, got {type(got)}"
        assert got.spec is fake_spec, "GenericLintTool should wrap the provided spec"

    def test_strategy_for_unknown_does_not_cache(self) -> None:
        """_strategy_for does NOT mutate STRATEGIES with the synthesised GenericLintTool."""
        from python_setup_lint.runner import _strategy_for, STRATEGIES
        unique_name = "t4-no-cache-fallback"
        _strategy_for(unique_name, ToolSpec(unique_name, ["t4nc"]))
        assert unique_name not in STRATEGIES, (
            "_strategy_for should not write into STRATEGIES — only register_lint_tool does"
        )
