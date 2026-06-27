"""Unit tests for baseline/diff/overwrite/print/orchestration/CLI/integration in ``python_setup_lint.runner``.

Split from ``test_lint_runner.py`` to stay under the 500-line pylint C0302 limit.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from python_setup_lint.runner import (
    LINT_TOOLS,
    LintResult,
    RunnerConfig,
    main,
    run_lint,
)
from python_setup_lint.runner.baseline import _capture_baseline, _diff_baseline
from python_setup_lint.runner.output import _run_cmd
import python_setup_lint.runner.output as _output_module
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
    baseline_entry_for_tool,
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

    def test_capture_basic(self) -> None:
        baseline = _capture_baseline(
            [
                make_lint_result(
                    tool_name="ruff check", exit_code=0, stdout="no issues"
                ),
                make_lint_result(tool_name="mypy", exit_code=1, stdout="error: x"),
            ]
        )
        assert len(baseline) == 2
        assert baseline[0]["tool"] == "ruff check" and baseline[0]["exit_code"] == 0
        assert baseline[1]["exit_code"] == 1

    @pytest.mark.parametrize(
        "tool,stdout,want_in,want_not_in",
        [
            (
                "pyright check",
                json.dumps({"summary": {"errorCount": 1}}),
                {"diagnostics": {"summary": {"errorCount": 1}}},
                [],
            ),
            (
                "pyright check",
                json.dumps(
                    {
                        "summary": {
                            "errorCount": 1,
                            "timeInSec": 12.5,
                            "filesAnalyzed": 100,
                        }
                    }
                ),
                None,
                ["timeInSec"],
            ),  # volatile timeInSec stripped; filesAnalyzed kept
            (
                "rumdl check",
                "\nSuccess: No issues found in 47 files (12ms)\n",
                {"output": "\nSuccess: No issues found in 47 files (XXXms)\n"},
                [],
            ),
        ],
        ids=[
            "pyright_diagnostics",
            "pyright_strips_time_in_sec",
            "rumdl_strips_timing",
        ],
    )
    def test_capture_strips_volatile_fields(  # type: ignore[no-untyped-def]
        self, tool: str, stdout: str, want_in, want_not_in
    ) -> None:
        baseline = _capture_baseline([make_lint_result(tool_name=tool, stdout=stdout)])
        if want_in is not None:
            for key, want_val in want_in.items():
                assert baseline[0][key] == want_val, (
                    f"{key}: got {baseline[0][key]!r}, want {want_val!r}"
                )
        for stripped_key in want_not_in or []:
            diag = baseline[0].get("diagnostics", {})
            assert stripped_key not in diag.get("summary", {}), (
                f"{stripped_key} should be stripped: {diag!r}"
            )


# ── _diff_baseline parametrised shrinkage/addition/mixed matrix ───


@pytest.mark.parametrize(
    "saved,current,want_kind,post_assert_id",
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

    @pytest.mark.parametrize("saved,current,want_kind", DIFF_EDGE_CASES)
    def test_diff_edge_case_matrix(
        self,
        tmp_path: Path,
        saved: dict[str, Any],
        current: dict[str, Any],
        want_kind: str,
    ) -> None:
        """timeInSec skip / diagnostics-present / identical saved=current → no violation."""
        results = build_current_results([saved], current)
        violations, _ = diff_baseline_with(tmp_path, saved, results)
        if want_kind == "no_violations":
            assert violations == [], f"Expected no violations, got {violations!r}"
        else:
            diff_violation_kind(violations, want_kind)

    @pytest.mark.parametrize("saved,results,want_kind", DIFF_EDGE_INVARIANTS)
    def test_diff_edge_invariants(
        self,
        tmp_path: Path,
        saved: dict[str, Any],
        results: list[LintResult],
        want_kind: str,
    ) -> None:
        """Exit-code changed / shrinkage / new-tool rows — each needs direct LintResult construction."""
        violations, reloaded = diff_baseline_with(tmp_path, saved, results)
        if want_kind == "no_violations":
            assert violations == [], f"Expected no violations, got {violations!r}"
            # shrinkage path: exit_code rewritten in baseline.
            if saved.get("exit_code") == 1:
                assert (
                    baseline_entry_for_tool(reloaded, saved["tool"])["exit_code"] == 0
                )
        else:
            diff_violation_kind(violations, want_kind)

    @pytest.mark.parametrize("kind,body,want_substr", DIFF_BASELINE_PATH_ERRORS)
    def test_diff_baseline_path_errors(  # type: ignore[no-untyped-def]
        self, tmp_path: Path, kind: str, body, want_substr
    ) -> None:
        """Missing baseline → 'not found'; invalid JSON → 'Cannot read'; empty + empty → no violation."""
        if kind == "missing":
            violations = _diff_baseline(
                [make_lint_result()], Path("/nonexistent/baseline.json")
            )
            assert len(violations) == 1 and want_substr in violations[0]
        elif kind == "invalid":
            baseline_path = tmp_path / "baseline.json"
            baseline_path.write_text(body)
            violations = _diff_baseline([make_lint_result()], baseline_path)
            assert len(violations) == 1 and want_substr in violations[0]
        else:  # empty baseline + no current → no violations, baseline stays empty
            violations, reloaded = diff_baseline_with(tmp_path, [], [])
            assert violations == [] and reloaded == []

    def test_diff_unwritable_baseline_returns_violation(self, tmp_path: Path) -> None:
        """D5: unwritable baseline + shrinkage triggers write → graceful violation, not crash."""
        baseline_path = tmp_path / "readonly.json"
        baseline_path.write_text(
            json.dumps(
                [
                    {
                        "tool": "ruff check",
                        "exit_code": 0,
                        "output": "src/a.py:1: error A\nsrc/b.py:2: error B",
                    }
                ]
            )
        )
        baseline_path.chmod(0o444)
        try:
            results = [
                make_lint_result(
                    tool_name="ruff check", exit_code=0, stdout="src/a.py:1: error A"
                )
            ]
            violations = _diff_baseline(results, baseline_path)
            assert any("cannot write baseline" in v.lower() for v in violations), (
                violations
            )
        finally:
            baseline_path.chmod(0o644)

    def test_peek_fallback_tools_snapshot(self) -> None:
        """peek_fallback_tools returns a frozen snapshot of the per-run fallback set."""
        from python_setup_lint.runner.baseline import (  # type: ignore[attr-defined]
            _FALLBACK_TOOLS,
            peek_fallback_tools,
        )

        snapshot = peek_fallback_tools()
        assert isinstance(snapshot, frozenset)
        _FALLBACK_TOOLS.add("test_tool")
        # Snapshot taken before mutation is unchanged
        assert "test_tool" not in snapshot
        # New snapshot reflects the mutation
        assert "test_tool" in peek_fallback_tools()

    def test_peek_fallback_tools_cleared_per_diff(self, tmp_path: Path) -> None:
        """_diff_baseline clears _FALLBACK_TOOLS at the start of each call."""
        from python_setup_lint.runner.baseline import (  # type: ignore[attr-defined]
            _FALLBACK_TOOLS,
            peek_fallback_tools,
        )

        _FALLBACK_TOOLS.add("stale_tool")
        baseline_path = tmp_path / "empty_baseline.json"
        baseline_path.write_text("[]")
        # Diff with empty baseline + empty current → no fallback triggers
        _diff_baseline([], baseline_path)
        assert "stale_tool" not in peek_fallback_tools(), (
            "Fallback set should be cleared per diff call"
        )


# ── overwrite-baseline coverage (D11) ──────────────────────────────


class TestOverwriteBaseline:
    """``--overwrite-baseline`` rewrites an existing baseline file (with fakes)."""

    def test_overwrite_via_main_and_run_lint(
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
        baseline_file2 = (
            tmp_path / "overwrite2.json"
        )  # run_lint(): same behavior via the API
        install_fake_runner(monkeypatch)
        run_lint(path="src/main.py", baseline=str(baseline_file2))
        install_fake_runner(monkeypatch)
        run_lint(
            path="src/main.py", baseline=str(baseline_file2), overwrite_baseline=True
        )
        assert json.loads(baseline_file2.read_text()) and json.loads(
            baseline_file.read_text()
        )

    def test_no_overwrite_without_flag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without ``--overwrite-baseline``, an existing baseline is diffed, not rewritten."""
        baseline_file = tmp_path / "no_overwrite.json"
        saved = [{"tool": "ruff check", "exit_code": 0, "output": "first output"}]
        baseline_file.write_text(json.dumps(saved))
        fake = fake_run_cmd_factory(
            {
                "ruff check": make_lint_result(
                    tool_name="ruff check", exit_code=0, stdout="first output"
                ),
            }
        )
        monkeypatch.setattr(_output_module, "_run_cmd", fake)
        main(
            ["--baseline", str(baseline_file), "--path", "src/main.py"],
            config=RunnerConfig(cwd=tmp_path, package_name="python_setup_lint"),
        )
        data = json.loads(baseline_file.read_text())
        assert len(data) == 1 and data[0]["output"] == "first output"


# ── Observability: _print_result output format ───────────────────


# ── run_lint orchestration ────────────────────────────────────────


class TestRunLintOrchestration:
    """Fake-driven ``run_lint``: --no-fail-fast, tools_override, package_name."""

    def test_no_fail_fast_captures_all_tools_and_returns_int(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        isolated_runner_registries: None,
    ) -> None:
        fake, _ = install_fake_runner(monkeypatch)
        baseline_file = tmp_path / "noff.json"
        rc = run_lint(
            config=tmp_config(tmp_path), baseline=str(baseline_file), no_fail_fast=True
        )
        assert isinstance(rc, int)
        assert {c.label for c in fake.calls} == {t.name for t in LINT_TOOLS}
        assert len(json.loads(baseline_file.read_text())) == len(LINT_TOOLS)

    def test_tools_override_limits_tools(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        install_fake_runner(monkeypatch)
        baseline_file = tmp_path / "tools_override.json"
        run_lint(
            config=tmp_config(tmp_path, tools_override=["ruff check", "mypy"]),
            baseline=str(baseline_file),
            no_fail_fast=True,
        )
        assert {e["tool"] for e in json.loads(baseline_file.read_text())} == {
            "ruff check",
            "mypy",
        }

    @pytest.mark.parametrize(
        "package_name,want_stubtest,want_count_delta", PACKAGE_NAME_STUBTEST_CASES
    )
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
            no_fail_fast=True,
        )
        dispatched = {c.label for c in fake.calls}
        assert ("mypy.stubtest" in dispatched) == want_stubtest
        assert ("pyright verify types" in dispatched) == want_stubtest
        assert len(dispatched) == len(LINT_TOOLS) + want_count_delta


# ── CLI argument parsing via main() (parametrised) ────────────────


@pytest.mark.parametrize("args", MAIN_ARGPARSE_CASES)
def test_main_argparse_accepts_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
) -> None:
    """One row per CLI flag — ``main(args, config=...)`` returns int (parsing succeeds)."""
    cfg = install_fake_runner(monkeypatch)[1]
    assert isinstance(main(args, config=cfg), int), f"main({args!r}) returned non-int"


class TestMainCLI:
    """argparse SystemExit boundary tests: --help exits 0, unknown flag non-zero."""

    @pytest.mark.parametrize("args,want_code_zero", MAIN_EXIT_CODE_CASES)
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

    @pytest.mark.parametrize("fix,override_stdout", RUFF_BASELINE_FIX_CASES)
    def test_run_lint_baseline_capture_with_ruff(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        fix: bool,
        override_stdout: str | None,
    ) -> None:
        """Baseline capture path: optional --fix; ruff check entry present in baseline JSON."""
        ruff_result = (
            None
            if override_stdout is None
            else make_lint_result(
                tool_name="ruff check", exit_code=0, stdout=override_stdout
            )
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
            no_fail_fast=True,
        )
        assert any(
            e["tool"] == "ruff check" for e in json.loads(baseline_file.read_text())
        )

    def test_baseline_create_and_diff_paths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Baseline create → diff round-trip: entries have tool/exit_code; second run matches → exit 0."""
        install_fake_runner(monkeypatch)
        baseline_file = tmp_path / "test_baseline.json"
        run_lint(config=tmp_config(tmp_path), baseline=str(baseline_file))  # create
        data = json.loads(baseline_file.read_text())
        assert (
            isinstance(data, list)
            and data
            and all("tool" in e and "exit_code" in e for e in data)
        )
        assert (
            run_lint(config=tmp_config(tmp_path), baseline=str(baseline_file)) == 0
        )  # re-diff matches

    def test_baseline_exits_nonzero_on_new_violation(self, tmp_path: Path) -> None:
        """Stored baseline with no issues + current new ruff issue → ``_diff_baseline`` returns truthy."""
        baseline_file = tmp_path / "test_baseline_new_violation.json"
        baseline_file.write_text(
            json.dumps([{"tool": "ruff check", "exit_code": 0, "output": "no issues"}])
        )
        results = [
            make_lint_result(
                tool_name="ruff check", exit_code=1, stdout="error: unused import"
            )
        ]
        assert _diff_baseline(results, baseline_file)


# ── _run_cmd ───────────────────────────────────────────────────────


class TestRunCmd:
    """Subprocess runner returns structured results (quick commands only)."""

    @pytest.mark.parametrize("cmd,label,exit_pred,stdout_want", RUN_CMD_CASES)
    def test_run_cmd_success_and_failure(  # type: ignore[no-untyped-def]
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
