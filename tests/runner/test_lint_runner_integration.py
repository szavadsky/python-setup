# pylint: disable=too-many-lines  # integration test suite; splitting would lose shared fixture context
"""Unit tests for baseline/diff/overwrite/print/orchestration/CLI/integration in ``python_setup_lint.runner``.

Splitting would lose context.
"""

# pylint: disable=too-many-positional-arguments  # parametrized test with 6 args; pylint default is 5
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import python_setup_lint.runner.output as _output_module
from python_setup_lint.runner import (
    LINT_TOOLS,
    LintResult,
    RunnerConfig,
    main,
    run_lint,
)
from python_setup_lint.runner.baseline import _capture_baseline, _diff_baseline
from python_setup_lint.runner.output import _run_cmd
from python_setup_lint.testing import fake_run_cmd_factory, make_lint_result
from tests.runner._factories import (
    diff_baseline_with,
    install_fake_runner,
    tmp_config,
)
from tests.runner._factories_baseline import (
    DIFF_BASELINE_CASES,
    DIFF_BASELINE_PATH_ERRORS,
    DIFF_BASELINE_POST_ASSERTS,
    DIFF_EDGE_CASES,
    DIFF_EDGE_INVARIANTS,
    build_current_results,
    diff_violation_kind,
)
from tests.runner._factories_extras import (
    MAIN_EXIT_CODE_CASES,
    PACKAGE_NAME_STUBTEST_CASES,
    RUFF_BASELINE_FIX_CASES,
    RUN_CMD_CASES,
)
from tests.runner._factories_tables import MAIN_ARGPARSE_CASES

# ── Baseline capture / diff ───────────────────────────────────────


class TestCaptureBaseline:
    """``_capture_baseline`` snapshot serialisation."""

    def test_capture_baseline_given_tool_output_then_captures(self) -> None:
        """ruff check with no issues produces 0 records; mypy with error produces 1 record."""
        baseline = _capture_baseline(
            [
                make_lint_result(tool_name="ruff check", exit_code=0, stdout="no issues"),
                make_lint_result(
                    tool_name="mypy",
                    exit_code=1,
                    stdout="src/a.py:1: error: x [some-code]",
                ),
            ]
        )
        assert len(baseline) == 1
        assert baseline[0]["tool"] == "mypy"
        assert baseline[0]["file"] == "src/a.py"
        assert baseline[0]["line"] == 1
        assert baseline[0]["col"] is None
        assert baseline[0]["rule"] == "some-code"
        assert baseline[0]["msg"] == "x"


# ── _diff_baseline parametrised shrinkage/addition/mixed matrix ───


@pytest.mark.parametrize(
    ("saved", "current", "want_kind", "post_assert_id"),
    DIFF_BASELINE_CASES,
)
def test_diff_baseline_matrix(
    tmp_path: Path,
    saved: dict[str, Any] | list[dict[str, Any]],
    current: dict[str, Any],
    want_kind: str,
    post_assert_id: str,
) -> None:
    """Row ``DIFF_BASELINE_CASES`` dispatch — write/diff/reload; assert via dispatch table."""
    current_results = build_current_results(saved, current)
    violations, reloaded = diff_baseline_with(tmp_path, saved, current_results)

    if want_kind == "no_violations":
        assert violations == [], f"Expected no violations, got {violations!r}"
    else:
        diff_violation_kind(violations, want_kind)

    assert_fn = DIFF_BASELINE_POST_ASSERTS[post_assert_id]
    assert_fn(reloaded)


class TestDiffBaselineEdgeCases:
    """Baseline diff boundary cases that don't fit the matrix rows."""

    @pytest.mark.parametrize(("saved", "current", "want_kind"), DIFF_EDGE_CASES)
    def test_diff_edge_case_matrix(
        self,
        tmp_path: Path,
        saved: list[dict[str, Any]],
        current: dict[str, Any],
        want_kind: str,
    ) -> None:
        """Identical saved=current -> no violation."""
        results = build_current_results(saved, current)
        violations, _ = diff_baseline_with(tmp_path, saved, results)
        if want_kind == "no_violations":
            assert violations == [], f"Expected no violations, got {violations!r}"
        else:
            diff_violation_kind(violations, want_kind)

    @pytest.mark.parametrize(("saved", "results", "want_kind"), DIFF_EDGE_INVARIANTS)
    def test_diff_edge_invariants(
        self,
        tmp_path: Path,
        saved: list[dict[str, Any]],
        results: list[LintResult],
        want_kind: str,
    ) -> None:
        """New-tool rows -- needs direct LintResult construction."""
        violations, reloaded = diff_baseline_with(tmp_path, saved, results)
        if want_kind == "no_violations":
            assert violations == [], f"Expected no violations, got {violations!r}"
        else:
            diff_violation_kind(violations, want_kind)

    @pytest.mark.parametrize(("kind", "body", "want_substr"), DIFF_BASELINE_PATH_ERRORS)
    def test_diff_baseline_path_errors(  # type: ignore[no-untyped-def]  # test function; signature varies by parametrize
        self, tmp_path: Path, kind: str, body, want_substr
    ) -> None:
        """Missing baseline -> 'not found'; invalid JSON -> 'Cannot read'; empty + empty -> no violation."""
        if kind == "missing":
            violations = _diff_baseline([make_lint_result()], Path("/nonexistent/baseline.json"))
            assert len(violations) == 1 and want_substr in violations[0]
        elif kind == "invalid":
            baseline_path = tmp_path / "baseline.json"
            baseline_path.write_text(body)
            violations = _diff_baseline([make_lint_result()], baseline_path)
            assert len(violations) == 1 and want_substr in violations[0]
        else:  # empty baseline + no current -> no violations, baseline stays empty
            violations, reloaded = diff_baseline_with(tmp_path, [], [])
            assert violations == [] and reloaded == []


# ── overwrite-baseline coverage (D11) ──────────────────────────────


class TestOverwriteBaseline:
    """``--overwrite-baseline`` rewrites an existing baseline file (with fakes)."""

    def test_overwrite_baseline_given_main_and_run_lint_then_overwrites(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``main --overwrite-baseline`` rewrites an existing baseline + emits banner; ``run_lint`` does the same."""
        baseline_file = tmp_path / "overwrite.json"
        _, cfg = install_fake_runner(monkeypatch, default_py_dirs=None)
        main(["--path", "src/main.py", "--baseline", str(baseline_file)], config=cfg)
        install_fake_runner(monkeypatch)
        main(
            [
                "--overwrite-baseline",
                "--baseline",
                str(baseline_file),
                "--path",
                "src/main.py",
            ],
            config=cfg,
        )
        assert "Overwriting baseline" in capsys.readouterr().out
        baseline_file2 = tmp_path / "overwrite2.json"
        install_fake_runner(monkeypatch)
        run_lint(path="src/main.py", baseline=str(baseline_file2))
        install_fake_runner(monkeypatch)
        run_lint(path="src/main.py", baseline=str(baseline_file2), overwrite_baseline=True)
        assert json.loads(baseline_file2.read_text()) is not None
        assert json.loads(baseline_file.read_text()) is not None

    def test_overwrite_baseline_given_no_flag_then_no_overwrite(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without ``--overwrite-baseline``, an existing baseline is diffed, not rewritten."""
        baseline_file = tmp_path / "no_overwrite.json"

        # Use a recorded stdout that will produce matching flat records.
        recorded_stdout = "src/main.py:1:1: F001 first output"
        saved = [
            {
                "tool": "ruff check",
                "file": "src/main.py",
                "line": 1,
                "col": 1,
                "rule": "F001",
                "msg": "first output",
            }
        ]
        baseline_file.write_text(json.dumps(saved))
        fake = fake_run_cmd_factory(
            {
                "ruff check": make_lint_result(
                    tool_name="ruff check",
                    exit_code=0,
                    stdout=recorded_stdout,
                ),
            }
        )
        monkeypatch.setattr(_output_module, "_run_cmd", fake)
        main(
            ["--baseline", str(baseline_file), "--path", "src/main.py"],
            config=RunnerConfig(cwd=tmp_path, package_name="python_setup_lint"),
        )
        data = json.loads(baseline_file.read_text())
        assert len(data) == 1
        assert data[0]["rule"] == "F001"
        assert data[0]["msg"] == "first output"


# ── Observability: _print_result output format ───────────────────


# ── run_lint orchestration ────────────────────────────────────────


class TestRunLintOrchestration:
    """Fake-driven ``run_lint``: tools_override, package_name."""

    def test_run_lint_captures_all_tools_and_returns_int(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        isolated_runner_registries: None,
    ) -> None:
        fake, _ = install_fake_runner(monkeypatch)
        baseline_file = tmp_path / "noff.json"
        rc = run_lint(config=tmp_config(tmp_path), baseline=str(baseline_file))
        assert isinstance(rc, int)
        assert {c.label for c in fake.calls} == {t.name for t in LINT_TOOLS}

    def test_run_lint_orchestration_given_tools_override_then_limits_tools(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        install_fake_runner(monkeypatch)
        baseline_file = tmp_path / "tools_override.json"
        run_lint(
            config=tmp_config(tmp_path, tools_override=["ruff check", "mypy"]),
            baseline=str(baseline_file),
        )
        data = json.loads(baseline_file.read_text())
        assert isinstance(data, list)

    @pytest.mark.parametrize(("package_name", "want_stubtest", "want_count_delta"), PACKAGE_NAME_STUBTEST_CASES)
    def test_package_name_governs_stubtest_verifytypes(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        isolated_runner_registries: None,
        package_name: str | None,
        want_stubtest: bool,
        want_count_delta: int,
    ) -> None:
        fake, _ = install_fake_runner(monkeypatch, package_name=package_name)
        run_lint(
            config=RunnerConfig(cwd=tmp_path, package_name=package_name),
            baseline=str(tmp_path / "pkg.json"),
        )
        dispatched = {c.label for c in fake.calls}
        assert ("mypy.stubtest" in dispatched) == want_stubtest
        assert ("pyright verify types" in dispatched) == want_stubtest
        assert len(dispatched) == len(LINT_TOOLS) + want_count_delta


# ── CLI argument parsing via main() (parametrised) ────────────────


@pytest.mark.parametrize("args", MAIN_ARGPARSE_CASES)
def test_main_argparse_given_flag_then_accepts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
) -> None:
    """One row per CLI flag — ``main(args, config=...)`` returns int (parsing succeeds)."""
    cfg = install_fake_runner(monkeypatch)[1]
    assert isinstance(main(args, config=cfg), int), f"main({args!r}) returned non-int"


class TestMainCLI:
    """argparse SystemExit boundary tests: --help exits 0, unknown flag non-zero."""

    @pytest.mark.parametrize(("args", "want_code_zero"), MAIN_EXIT_CODE_CASES)
    def test_main_exit_codes(self, args: list[str], want_code_zero: bool) -> None:
        """argparse exits 0 on --help, non-zero on unknown flag (CLI smoke)."""
        with pytest.raises(SystemExit) as exc_info:
            main(args)
        if want_code_zero:
            assert exc_info.value.code == 0
        else:
            assert exc_info.value.code != 0


# ── Integration: quick real tool with fakes ──────────────────────


class TestRunLintIntegration:
    """End-to-end ``run_lint`` with the fake ``_run_cmd`` installed."""

    @pytest.mark.parametrize(("fix", "override_stdout"), RUFF_BASELINE_FIX_CASES)
    def test_run_lint_baseline_capture_with_ruff(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        fix: bool,
        override_stdout: str | None,
    ) -> None:
        """Baseline capture path: optional --fix; ruff check entry present in baseline JSON."""
        ruff_result = (
            None if override_stdout is None else make_lint_result(tool_name="ruff check", exit_code=0, stdout=override_stdout)
        )
        if ruff_result is not None:
            fake = fake_run_cmd_factory({"ruff check": ruff_result})
            monkeypatch.setattr(_output_module, "_run_cmd", fake)
        else:
            install_fake_runner(monkeypatch)
        baseline_file = tmp_path / "test_baseline.json"
        run_lint(
            config=tmp_config(tmp_path),
            fix=fix,
            baseline=str(baseline_file),
        )
        data = json.loads(baseline_file.read_text())
        assert isinstance(data, list)

    def test_run_lint_integration_given_baseline_then_create_and_diff_paths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Baseline create -> diff round-trip: entries have flat-record keys; second run matches -> exit 0."""
        # Use stdout that produces at least some records so baseline is non-empty.
        install_fake_runner(
            monkeypatch,
            overrides={
                "ruff check": make_lint_result(
                    tool_name="ruff check",
                    exit_code=0,
                    stdout="src/main.py:1:1: F001 error msg",
                ),
            },
        )
        baseline_file = tmp_path / "test_baseline.json"
        run_lint(config=tmp_config(tmp_path), baseline=str(baseline_file))  # create
        data = json.loads(baseline_file.read_text())
        assert isinstance(data, list)
        assert all("tool" in e and "file" in e and "line" in e and "col" in e and "rule" in e and "msg" in e for e in data), (
            f"Flat record keys missing: {data!r}"
        )
        assert run_lint(config=tmp_config(tmp_path), baseline=str(baseline_file)) == 0  # re-diff matches

    def test_run_lint_integration_given_new_violation_then_exits_nonzero(self, tmp_path: Path) -> None:
        """Stored baseline with no issues + current new ruff issue -> ``_diff_baseline`` returns truthy."""
        baseline_file = tmp_path / "test_baseline_new_violation.json"
        baseline_file.write_text("[]")
        results = [
            make_lint_result(
                tool_name="ruff check",
                exit_code=1,
                stdout="src/main.py:1:1: F401 unused-import",
            )
        ]
        assert _diff_baseline(results, baseline_file)


# ── _run_cmd ───────────────────────────────────────────────────────


class TestRunCmd:
    """Subprocess runner returns structured results (quick commands only)."""

    @pytest.mark.parametrize(("cmd", "label", "exit_pred", "stdout_want"), RUN_CMD_CASES)
    def test_run_cmd_success_and_failure(  # type: ignore[no-untyped-def]  # test function; signature varies by parametrize
        self, cmd, label, exit_pred, stdout_want
    ) -> None:
        r = _run_cmd(cmd, cwd=Path.cwd(), label=label)
        assert exit_pred(r.exit_code) and r.tool_name == label and r.elapsed >= 0
        if stdout_want is not None:
            assert r.stdout == stdout_want

    def test_non_existent_command_returns_127(self) -> None:
        r = _run_cmd(["nonexistent_cmd_xyz789"], cwd=Path.cwd(), label="bad")
        assert r.exit_code == 127
        assert r.stderr == "Tool not found: nonexistent_cmd_xyz789"
        assert r.elapsed >= 0

    def test_run_cmd_timeout_returns_124(self) -> None:
        """A command that exceeds the timeout returns exit code 124."""
        r = _run_cmd(["sleep", "5"], cwd=Path.cwd(), label="sleeper", timeout=1)
        assert r.exit_code == 124
        assert "timed out" in r.stderr
        assert r.elapsed >= 0

    @pytest.mark.slow
    def test_run_cmd_memory_limit_kills_oom(self) -> None:
        """A command that exceeds RLIMIT_AS returns non-zero exit code."""
        r = _run_cmd(
            ["python", "-c", "x = [0] * (512 * 1024 * 1024)"],
            cwd=Path.cwd(),
            label="oom",
            memory_limit_mb=64,
        )
        assert r.exit_code != 0
        assert r.elapsed >= 0
