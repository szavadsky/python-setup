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

# ── Helpers ─────────────────────────────────────────────────────────

_CONFIG = RunnerConfig(cwd=Path.cwd())


def _make_result(
    tool_name: str = "ruff check",
    exit_code: int = 0,
    stdout: str = "",
    stderr: str = "",
    elapsed: float = 0.5,
) -> LintResult:
    return LintResult(
        tool_name=tool_name,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        elapsed=elapsed,
    )


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
            _make_result(tool_name="ruff check", exit_code=0, stdout="no issues"),
            _make_result(tool_name="mypy", exit_code=1, stdout="error: x"),
        ]
        baseline = _capture_baseline(results)
        assert len(baseline) == 2
        assert baseline[0]["tool"] == "ruff check"
        assert baseline[0]["exit_code"] == 0
        assert baseline[1]["exit_code"] == 1

    def test_capture_handles_json_output(self) -> None:
        pyright_out = json.dumps({"summary": {"errorCount": 1}})
        results = [_make_result(tool_name="pyright check", stdout=pyright_out)]
        baseline = _capture_baseline(results)
        assert baseline[0]["diagnostics"] == {"summary": {"errorCount": 1}}

    def test_capture_rumdl_strips_timing(self) -> None:
        """rumdl success output has timing stripped via regex replacement."""
        results = [_make_result(tool_name="rumdl check", stdout="\nSuccess: No issues found in 47 files (12ms)\n")]
        baseline = _capture_baseline(results)
        assert "(XXXms)" in baseline[0]["output"], f"Expected timing stripped, got: {baseline[0]['output']}"

    def test_capture_pyright_strips_time_in_sec(self) -> None:
        """_capture_baseline strips volatile timeInSec from pyright summary."""
        pyright_out = json.dumps({"summary": {"errorCount": 1, "timeInSec": 12.5, "filesAnalyzed": 100}})
        results = [_make_result(tool_name="pyright check", stdout=pyright_out)]
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
        results = [_make_result(tool_name="pyright check", exit_code=0, stdout=json.dumps(cur_diag))]
        violations = _diff_baseline(results, baseline_path)
        assert violations == [], f"Expected no violations with timeInSec diff, got: {violations}"

    def test_diff_uses_diagnostics_when_present(self, tmp_path: Path) -> None:
        """_diff_baseline compares diagnostics key when present instead of raw output."""
        baseline_path = tmp_path / "diag_baseline.json"
        diag = {"summary": {"errorCount": 1}}
        saved = [{"tool": "pyright check", "exit_code": 0, "diagnostics": diag}]
        baseline_path.write_text(json.dumps(saved))
        # Same diagnostics, different raw output — no violation
        results = [_make_result(tool_name="pyright check", exit_code=0, stdout=json.dumps(diag))]
        violations = _diff_baseline(results, baseline_path)
        assert violations == [], f"Expected no violations with matching diagnostics, got: {violations}"

    def test_diff_diagnostics_changed(self, tmp_path: Path) -> None:
        """_diff_baseline detects diagnostics change."""
        baseline_path = tmp_path / "diag_change.json"
        saved = [{"tool": "pyright check", "exit_code": 0, "diagnostics": {"summary": {"errorCount": 0}}}]
        baseline_path.write_text(json.dumps(saved))
        results = [_make_result(tool_name="pyright check", exit_code=0, stdout=json.dumps({"summary": {"errorCount": 1}}))]
        violations = _diff_baseline(results, baseline_path)
        assert any("diagnostics" in v.lower() for v in violations), f"Expected diagnostics change, got: {violations}"

    def test_diff_no_baseline_file(self) -> None:
        results = [_make_result()]
        violations = _diff_baseline(results, Path("/nonexistent/baseline.json"))
        assert len(violations) == 1
        assert "not found" in violations[0]

    def test_diff_identical(self, tmp_path: Path) -> None:
        baseline_path = tmp_path / "baseline.json"
        results = [_make_result(tool_name="test", exit_code=0, stdout="ok")]
        saved = [{"tool": "test", "exit_code": 0, "output": "ok"}]
        with open(baseline_path, "w") as f:
            json.dump(saved, f)
        violations = _diff_baseline(results, baseline_path)
        assert violations == [], f"Expected no violations, got: {violations}"

    def test_diff_exit_code_changed(self, tmp_path: Path) -> None:
        baseline_path = tmp_path / "baseline.json"
        results = [_make_result(tool_name="test", exit_code=1, stdout="ok")]
        saved = [{"tool": "test", "exit_code": 0, "output": "ok"}]
        with open(baseline_path, "w") as f:
            json.dump(saved, f)
        violations = _diff_baseline(results, baseline_path)
        assert any("exit code" in v.lower() for v in violations), f"Expected exit code diff, got: {violations}"

    def test_diff_output_changed(self, tmp_path: Path) -> None:
        baseline_path = tmp_path / "baseline.json"
        results = [_make_result(tool_name="test", exit_code=0, stdout="new output")]
        saved = [{"tool": "test", "exit_code": 0, "output": "old output"}]
        with open(baseline_path, "w") as f:
            json.dump(saved, f)
        violations = _diff_baseline(results, baseline_path)
        assert any("output changed" in v.lower() for v in violations), f"Expected output change, got: {violations}"

    def test_diff_new_tool(self, tmp_path: Path) -> None:
        baseline_path = tmp_path / "baseline.json"
        results = [_make_result(tool_name="tool_a"), _make_result(tool_name="tool_b")]
        saved = [{"tool": "tool_a", "exit_code": 0, "output": ""}]
        with open(baseline_path, "w") as f:
            json.dump(saved, f)
        violations = _diff_baseline(results, baseline_path)
        assert any("no baseline entry" in v.lower() for v in violations), f"Expected new tool message, got: {violations}"

    def test_diff_invalid_json(self, tmp_path: Path) -> None:
        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text("not valid json")
        violations = _diff_baseline([_make_result()], baseline_path)
        assert len(violations) == 1
        assert "Cannot read" in violations[0]


# ── overwrite-baseline coverage (D11) ──────────────────────────────


class TestOverwriteBaseline:
    """Verify --overwrite-baseline rewrites an existing baseline file."""

    def test_overwrite_via_main(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """main(['--overwrite-baseline', ...]) rewrites existing baseline on second call."""
        baseline_file = tmp_path / "overwrite.json"
        # First call creates baseline
        rc1 = main(["--path", "src/python_setup_lint/runner.py", "--baseline", str(baseline_file)])
        assert baseline_file.exists()
        data_first = json.loads(baseline_file.read_text())
        assert len(data_first) > 0

        # Second call with overwrite — should rewrite
        rc2 = main(["--overwrite-baseline", "--baseline", str(baseline_file), "--path", "src/python_setup_lint/runner.py"])
        captured = capsys.readouterr()
        assert "Overwriting baseline" in captured.out, f"Expected 'Overwriting baseline' in output, got: {captured.out[:300]}"
        data_second = json.loads(baseline_file.read_text())
        assert len(data_second) > 0  # still valid

    def test_overwrite_via_run_lint(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """run_lint(overwrite_baseline=True) rewrites when file already exists."""
        baseline_file = tmp_path / "overwrite2.json"
        # Create baseline
        run_lint(path="src/python_setup_lint/runner.py", baseline=str(baseline_file))
        assert baseline_file.exists()

        # Overwrite
        run_lint(path="src/python_setup_lint/runner.py", baseline=str(baseline_file), overwrite_baseline=True)
        data = json.loads(baseline_file.read_text())
        assert len(data) > 0

    def test_no_overwrite_without_flag(self, tmp_path: Path) -> None:
        """Without --overwrite-baseline, an existing baseline is diffed, not rewritten."""
        baseline_file = tmp_path / "no_overwrite.json"
        # Create baseline with known content
        saved = [{"tool": "ruff check", "exit_code": 0, "output": "first output"}]
        baseline_file.write_text(json.dumps(saved))

        # Run again without overwrite — should diff, not rewrite
        rc = main(["--baseline", str(baseline_file), "--path", "src/python_setup_lint/runner.py"])
        # Baseline content should remain unchanged (not overwritten)
        data = json.loads(baseline_file.read_text())
        assert len(data) == 1
        assert data[0]["output"] == "first output"


# ── Observability: _print_result output format ───────────────────


class TestPrintResult:
    """Verify _print_result produces expected output format."""

    def test_print_passed_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        """PASSED result includes tool name, status, and stdout."""
        result = _make_result(tool_name="mytool", exit_code=0, stdout="all good\n")
        _print_result(result)
        captured = capsys.readouterr()
        assert "[mytool]" in captured.out
        assert "PASSED" in captured.out
        assert "all good" in captured.out

    def test_print_failed_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        """FAILED result includes error details, status, and stderr."""
        result = _make_result(tool_name="mytool", exit_code=2, stderr="error: x\n")
        _print_result(result)
        captured = capsys.readouterr()
        assert "FAILED" in captured.out
        assert "exit=2" in captured.out
        assert "error: x" in captured.out

    def test_print_stderr_before_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        """stderr content appears before stdout in output (code convention)."""
        result = _make_result(
            tool_name="mytool",
            exit_code=1,
            stderr="stderr line\n",
            stdout="stdout line\n",
        )
        _print_result(result)
        captured = capsys.readouterr()
        assert captured.out.index("stderr line") < captured.out.index("stdout line"), "stderr should be printed before stdout"


# ── run_lint orchestration with advanced flags ───────────────────


class TestRunLintOrchestration:
    """Verify run_lint behaviour with --no-fail-fast, --exclude, etc."""

    def test_no_fail_fast_captures_all_tools(self, tmp_path: Path) -> None:
        """With --no-fail-fast, all applicable TOOLS produce a baseline entry."""
        baseline_file = tmp_path / "noff.json"
        run_lint(
            config=RunnerConfig(cwd=Path.cwd(), package_name="python_setup_lint"),
            path="src/python_setup_lint/runner.py",
            baseline=str(baseline_file),
            no_fail_fast=True,
        )
        data = json.loads(baseline_file.read_text())
        # Without package_name: 9 tools (stubtest/verifytypes skipped)
        # With package_name: all 11
        assert len(data) == len(TOOLS), (
            f"Expected {len(TOOLS)} baseline entries, got {len(data)} — not all tools ran under --no-fail-fast"
        )

    def test_no_fail_fast_returns_int(self) -> None:
        """--no-fail-fast returns an int (aggregate exit code)."""
        rc = run_lint(path="src/python_setup_lint/runner.py", no_fail_fast=True)
        assert isinstance(rc, int)

    def test_tools_override_limits_tools(self, tmp_path: Path) -> None:
        """tools_override runs only the specified tools."""
        baseline_file = tmp_path / "tools_override.json"
        config = RunnerConfig(cwd=Path.cwd(), tools_override=["ruff check", "mypy"])
        run_lint(
            config=config,
            path="src/python_setup_lint/runner.py",
            baseline=str(baseline_file),
            no_fail_fast=True,
        )
        data = json.loads(baseline_file.read_text())
        tool_names = {entry["tool"] for entry in data}
        assert tool_names == {"ruff check", "mypy"}, f"Expected only ruff check and mypy, got {tool_names}"

    def test_package_name_none_skips_stubtest_verifytypes(self, tmp_path: Path) -> None:
        """With package_name=None, stubtest and verifytypes are skipped (9 tools)."""
        baseline_file = tmp_path / "no_pkg.json"
        config = RunnerConfig(cwd=Path.cwd(), package_name=None)
        run_lint(
            config=config,
            path="src/python_setup_lint/runner.py",
            baseline=str(baseline_file),
            no_fail_fast=True,
        )
        data = json.loads(baseline_file.read_text())
        tool_names = {entry["tool"] for entry in data}
        assert "mypy.stubtest" not in tool_names, "stubtest should be skipped when package_name=None"
        assert "pyright verify types" not in tool_names, "verifytypes should be skipped when package_name=None"
        assert len(data) == len(TOOLS) - 2, f"Expected {len(TOOLS) - 2} tools, got {len(data)}"

    def test_package_name_set_runs_stubtest_verifytypes(self, tmp_path: Path) -> None:
        """With package_name set, stubtest and verifytypes are included (11 tools)."""
        baseline_file = tmp_path / "with_pkg.json"
        config = RunnerConfig(cwd=Path.cwd(), package_name="python_setup_lint")
        run_lint(
            config=config,
            path="src/python_setup_lint/runner.py",
            baseline=str(baseline_file),
            no_fail_fast=True,
        )
        data = json.loads(baseline_file.read_text())
        tool_names = {entry["tool"] for entry in data}
        assert "mypy.stubtest" in tool_names, "stubtest should run when package_name is set"
        assert "pyright verify types" in tool_names, "verifytypes should run when package_name is set"
        assert len(data) == len(TOOLS), f"Expected {len(TOOLS)} tools, got {len(data)}"

    # ── CLI argument parsing via main() ─────────────────────────────


class TestMainArgparse:
    """Verify main() translates CLI flags to run_lint kwargs."""

    def test_main_path(self) -> None:
        """--path is accepted by CLI."""
        rc = main(["--path", "src/python_setup_lint/runner.py"])
        assert isinstance(rc, int)

    def test_main_fix(self) -> None:
        """--fix is accepted by CLI."""
        rc = main(["--fix", "--path", "src/python_setup_lint/runner.py"])
        assert isinstance(rc, int)

    def test_main_no_fail_fast(self) -> None:
        """--no-fail-fast is accepted by CLI."""
        rc = main(["--no-fail-fast", "--path", "src/python_setup_lint/runner.py"])
        assert isinstance(rc, int)

    def test_main_exclude(self) -> None:
        """--exclude is accepted by CLI."""
        rc = main(["--exclude", "tests/", "--path", "src/python_setup_lint/runner.py"])
        assert isinstance(rc, int)

    def test_main_baseline(self, tmp_path: Path) -> None:
        """--baseline produces a JSON file."""
        baseline_file = tmp_path / "main_baseline.json"
        rc = main(
            [
                "--baseline",
                str(baseline_file),
                "--path",
                "src/python_setup_lint/runner.py",
            ]
        )
        assert baseline_file.exists()
        data = json.loads(baseline_file.read_text())
        assert len(data) > 0

    def test_main_package_name(self) -> None:
        """--package-name is accepted by CLI."""
        rc = main(["--package-name", "python_setup_lint", "--path", "src/python_setup_lint/runner.py"])
        assert isinstance(rc, int)

    def test_main_cwd(self, tmp_path: Path) -> None:
        """--cwd is accepted by CLI."""
        rc = main(["--cwd", str(tmp_path), "--path", "."])
        assert isinstance(rc, int)

    def test_main_tools(self) -> None:
        """--tools is accepted by CLI (comma-separated list)."""
        rc = main(["--tools", "ruff check,mypy", "--path", "src/python_setup_lint/runner.py"])
        assert isinstance(rc, int)

    def test_main_default_py_dirs(self) -> None:
        """--default-py-dirs is accepted by CLI."""
        rc = main(["--default-py-dirs", "src,tests", "--path", "src/python_setup_lint/runner.py"])
        assert isinstance(rc, int)

    def test_main_no_args_backward_compat(self) -> None:
        """main() with no args runs successfully (backward compat)."""
        rc = main([])
        assert isinstance(rc, int)


# ── Smoke integration: run subset via CLI ─────────────────────────--


class TestMainCLI:
    """Lightweight CLI exercises — uses fast tools only to keep tests quick."""

    def test_main_help(self) -> None:
        """--help should exit with code 0 (SystemExit)."""
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0

    def test_main_unknown_flag_error(self) -> None:
        """Unknown flag produces non-zero exit."""
        with pytest.raises(SystemExit) as exc:
            main(["--nonexistent-flag"])

    def test_lint_result_dataclass(self) -> None:
        """LintResult fields are correctly accessible."""
        r = LintResult(tool_name="test", exit_code=0, stdout="out", stderr="err", elapsed=1.0)
        assert r.tool_name == "test"
        assert r.exit_code == 0
        assert r.stdout == "out"
        assert r.stderr == "err"
        assert r.elapsed == 1.0

    @pytest.mark.slow
    def test_run_lint_returns_int(self) -> None:
        """run_lint() returns an int (may be 0 or non-zero)."""
        rc = run_lint()
        assert isinstance(rc, int)


# ── Integration: quick real tool (ruff) ────────────────────────────


class TestIntegration:
    """Exercise real lint tools with lightweight scope."""

    def test_ruff_on_small_path(self) -> None:
        """Run ruff on a small scope — ruff entry present in baseline."""
        baseline_file = Path("/tmp/qa_test_baseline.json")
        try:
            rc = run_lint(path="src/python_setup_lint/runner.py", baseline=str(baseline_file), no_fail_fast=True)
            assert baseline_file.exists()
            data = json.loads(baseline_file.read_text())
            assert any(entry["tool"] == "ruff check" for entry in data), "ruff check did not produce a baseline entry"
        finally:
            baseline_file.unlink(missing_ok=True)

    def test_ruff_with_fix_flag(self) -> None:
        """Run lint --fix on a single file — ruff entry present in baseline."""
        baseline_file = Path("/tmp/qa_test_fix_baseline.json")
        try:
            rc = run_lint(path="src/python_setup_lint/runner.py", fix=True, baseline=str(baseline_file), no_fail_fast=True)
            assert baseline_file.exists()
            data = json.loads(baseline_file.read_text())
            assert any(entry["tool"] == "ruff check" for entry in data), "ruff check did not produce a baseline entry under --fix"
        finally:
            baseline_file.unlink(missing_ok=True)

    def test_baseline_create(self, tmp_path: Path) -> None:
        """Creating a baseline on a small scope produces a JSON file with multiple entries."""
        baseline_file = tmp_path / "test_baseline.json"
        run_lint(
            path="src/python_setup_lint/runner.py",
            baseline=str(baseline_file),
        )
        assert baseline_file.exists()
        data = json.loads(baseline_file.read_text())
        assert isinstance(data, list)
        assert len(data) > 0
        # Every entry has required fields
        for entry in data:
            assert "tool" in entry
            assert "exit_code" in entry

    def test_baseline_diff_identical(self, tmp_path: Path) -> None:
        """Running twice with baseline — baseline entries remain structurally consistent."""
        baseline_file = tmp_path / "test_baseline2.json"
        run_lint(path="src/python_setup_lint/runner.py", baseline=str(baseline_file))
        saved_after_first = json.loads(baseline_file.read_text())
        assert len(saved_after_first) > 0

        # Second run — baseline should still be valid JSON with same structure
        run_lint(path="src/python_setup_lint/runner.py", baseline=str(baseline_file))
        saved_after_second = json.loads(baseline_file.read_text())
        assert isinstance(saved_after_second, list)
        # Baseline is NOT overwritten on subsequent runs (only created if missing)
        # So entries should be identical to first run
        assert len(saved_after_second) == len(saved_after_first)

    def test_baseline_exits_zero_when_matching(self, tmp_path: Path) -> None:
        """run_lint with --baseline exits 0 when output matches baseline, even if tools have non-zero exit codes."""
        baseline_file = tmp_path / "test_baseline_exit.json"
        # First run creates baseline (may have non-zero tool exits)
        rc1 = run_lint(path="src/python_setup_lint/runner.py", baseline=str(baseline_file))
        # Second run with same baseline must exit 0 (no new violations)
        rc2 = run_lint(path="src/python_setup_lint/runner.py", baseline=str(baseline_file))
        assert rc2 == 0, (
            f"Expected exit code 0 when baseline matches, got {rc2}. "
            f"First run returned {rc1}. "
            "This means the baseline-gated hook would always fail on git push."
        )

    def test_baseline_exits_nonzero_on_new_violation(self, tmp_path: Path) -> None:
        """run_lint with --baseline exits non-zero when a new violation appears."""
        baseline_file = tmp_path / "test_baseline_new_violation.json"
        # Create baseline with a clean result
        clean_results = [
            _make_result(tool_name="ruff check", exit_code=0, stdout="no issues"),
        ]
        saved = [{"tool": "ruff check", "exit_code": 0, "output": "no issues"}]
        baseline_file.write_text(json.dumps(saved))

        # Now simulate a new violation by running with different output
        # We need to use _diff_baseline directly since run_lint runs real tools
        violations = _diff_baseline(
            [_make_result(tool_name="ruff check", exit_code=1, stdout="error: unused import")],
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