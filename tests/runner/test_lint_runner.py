"""Unit tests for ``python_setup_lint.runner``.

Per-tool / per-flag rows are parametrised via shared tables in
``tests/runner/_factories.py`` (T12 consolidation).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import python_setup_lint.runner as _runner_module
from python_setup_lint.runner import (
    LINT_TOOLS,
    PARSE_STRATEGIES,
    STRATEGIES,
    TOOLS,
    ExtraToolsConfigError,
    LintResult,
    RunnerConfig,
    ToolSpec,
    ViolationCount,
    _SUPPORTED_CONFIG_KEYS,
    _build_command,
    _build_statistics_flags,
    _capture_baseline,
    _diff_baseline,
    _expand_globs,
    _find_py_files,
    _print_result,
    _print_statistics_grouped,
    _run_cmd,
    _sort_counts,
    _STATISTICS_PARSERS,
    main,
    register_lint_tool,
    run_lint,
)
from python_setup_lint.testing import fake_run_cmd_factory, make_lint_result

from tests.runner._factories import (
    BUILD_COMMAND_CASES,
    CLEAN_EXTRAS_PYPROJECT_BODY,
    DIFF_BASELINE_CASES,
    DIFF_BASELINE_PATH_ERRORS,
    DIFF_BASELINE_POST_ASSERTS,
    DIFF_EDGE_CASES,
    DIFF_EDGE_INVARIANTS,
    EXPAND_GLOBS_CASES,
    FIND_PY_FILES_BOUNDARY_CASES,
    GROUPED_OUTPUT_CASES,
    GROUPED_SORT_BY_RULE_COUNTS,
    MAIN_ARGPARSE_CASES,
    MAIN_EXIT_CODE_CASES,
    MAIN_GROUP_SORT_CASES,
    MALFORMATION_CASES,
    PACKAGE_NAME_STUBTEST_CASES,
    PARSER_STATISTICS_CASES,
    PRINT_FORMAT_CASES,
    RUFF_BASELINE_FIX_CASES,
    RUN_CMD_CASES,
    SORT_BY_RULE_COUNTS,
    SORT_DEFAULT_COUNTS,
    STATISTICS_FLAG_CASES,
    STRATEGY_TOKENS_CASES,
    baseline_entry_for_tool,
    build_current_results,
    diff_baseline_with,
    diff_violation_kind,
    install_fake_runner,
    lint_config,
    tmp_config,
    write_pyproject,
)

_CONFIG = RunnerConfig(cwd=Path.cwd())


# ── ToolSpec / TOOLS table ─────────────────────────────────────────


class TestToolSpec:
    """The static 11-tool table invariant."""

    def test_known_tools_present(self) -> None:
        assert {t.name for t in TOOLS} == {
            "tach check", "ruff check", "rumdl check", "mypy", "yamllint",
            "ty check", "mypy.stubtest", "pyright check", "pyright verify types",
            "pylint", "detect-secrets",
        }

    def test_autofix_and_no_duplicate_names(self) -> None:
        assert {t.name for t in TOOLS if t.supports_fix} == {"ruff check", "rumdl check", "ty check"}
        assert all(t.name for t in TOOLS)
        assert len({t.name for t in TOOLS}) == len(TOOLS) == 11


# ── _build_command (parametrised via shared table) ────────────────


@pytest.mark.parametrize("spec_kwargs,build_kwargs,expected", BUILD_COMMAND_CASES)
def test_build_command(spec_kwargs: dict, build_kwargs: dict, expected: list[str]) -> None:
    """Covers path/fix/exclude/override-defaults — one row per (spec, kwargs, cmd)."""
    spec = ToolSpec(**spec_kwargs)
    assert _build_command(spec, config=_CONFIG, **build_kwargs) == expected


class TestStrategyBuildCommand:
    """Strategy-driven ``build_command`` cases — exercises LintTool subclasses."""

    def test_pylint_strategy_expands_py_files(self) -> None:
        from python_setup_lint.runner import _PylintLintTool
        cmd = _PylintLintTool(ToolSpec("pylint", ["pylint"], supports_path=True)).build_command(
            config=_CONFIG, path="src/python_setup_lint")
        assert cmd[0] == "pylint"
        # Auto-discovery may inject --rcfile <path> before .py files; skip those.
        py_files = [a for a in cmd[1:] if a.endswith(".py")]
        assert len(py_files) > 0 and all(a.endswith(".py") for a in py_files)

    def test_yamllint_strategy_expands_glob(self) -> None:
        cmd = _build_command(
            ToolSpec("yamllint", ["yamllint"], supports_path=True, default_paths=["src/**/*.py"]),
            config=_CONFIG)
        assert cmd[0] == "yamllint" and len(cmd) > 1 and all(a.endswith(".py") for a in cmd[1:])

    @pytest.mark.parametrize(
        "strategy_name,package_name,expected_tokens", STRATEGY_TOKENS_CASES,
    )
    def test_stubtest_and_verifytypes_strategy_with_package_name(
        self, strategy_name: str, package_name: str, expected_tokens: list[str],
    ) -> None:
        config = RunnerConfig(cwd=Path.cwd(), package_name=package_name)
        cmd = STRATEGIES[strategy_name].build_command(config=config)
        for tok in expected_tokens:
            assert tok in cmd, f"expected {tok!r} in {cmd!r}"

    def test_detect_secrets_strategy_bash_pipeline(self) -> None:
        cmd = STRATEGIES["detect-secrets"].build_command(config=RunnerConfig(cwd=Path.cwd()))
        assert cmd[:2] == ["bash", "-c"]
        assert "detect-secrets-hook" in cmd[2] and "--baseline" in cmd[2]


# ── Path helpers ─────────────────────────────────────────────────


class TestPathHelpers:
    """``_find_py_files`` and ``_expand_globs`` edge cases."""

    def test_find_py_files_in_dir(self) -> None:
        files = _find_py_files(["src/python_setup_lint"], cwd=Path.cwd())
        assert files and all(f.endswith(".py") for f in files) and all(not Path(f).is_absolute() for f in files)

    def test_find_py_files_sorted_and_dedupe(self) -> None:
        files = _find_py_files(["src/python_setup_lint", "src/python_setup_lint"], cwd=Path.cwd())
        assert files == sorted(files) and len(files) == len(set(files))

    @pytest.mark.parametrize("paths,expected", FIND_PY_FILES_BOUNDARY_CASES)
    def test_find_py_files_boundary(self, paths: list[str], expected: list[str]) -> None:
        assert _find_py_files(paths, cwd=Path.cwd()) == expected

    def test_find_py_files_ignores_non_py(self) -> None:
        # ``src/python_setup_lint`` has both .py and .pyi — only .py kept.
        assert all(f.endswith(".py") for f in _find_py_files(["src/python_setup_lint"], cwd=Path.cwd()))

    @pytest.mark.parametrize("paths,check", EXPAND_GLOBS_CASES)
    def test_expand_globs(self, paths: list[str], check) -> None:
        assert check(_expand_globs(paths, cwd=Path.cwd()))


# ── _run_cmd ───────────────────────────────────────────────────────


class TestRunCmd:
    """Subprocess runner returns structured results (quick commands only)."""

    @pytest.mark.parametrize("cmd,label,exit_pred,stdout_want", RUN_CMD_CASES)
    def test_run_cmd_success_and_failure(self, cmd, label, exit_pred, stdout_want) -> None:
        r = _run_cmd(cmd, cwd=Path.cwd(), label=label)
        assert exit_pred(r.exit_code) and r.tool_name == label and r.elapsed >= 0
        if stdout_want is not None:
            assert r.stdout == stdout_want

    def test_non_existent_command_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            _run_cmd(["nonexistent_cmd_xyz789"], cwd=Path.cwd(), label="bad")


# ── Baseline capture / diff ───────────────────────────────────────


class TestCaptureBaseline:
    """``_capture_baseline`` snapshot serialisation."""

    def test_capture_basic(self) -> None:
        baseline = _capture_baseline([
            make_lint_result(tool_name="ruff check", exit_code=0, stdout="no issues"),
            make_lint_result(tool_name="mypy", exit_code=1, stdout="error: x"),
        ])
        assert len(baseline) == 2
        assert baseline[0]["tool"] == "ruff check" and baseline[0]["exit_code"] == 0
        assert baseline[1]["exit_code"] == 1

    @pytest.mark.parametrize(
        "tool,stdout,want_in,want_not_in",
        [
            ("pyright check", json.dumps({"summary": {"errorCount": 1}}),
             {"diagnostics": {"summary": {"errorCount": 1}}}, []),  # noqa: E501
            ("pyright check", json.dumps({"summary": {"errorCount": 1, "timeInSec": 12.5, "filesAnalyzed": 100}}),
             None, ["timeInSec"]),  # volatile timeInSec stripped; filesAnalyzed kept
            ("rumdl check", "\nSuccess: No issues found in 47 files (12ms)\n",
             {"output": "\nSuccess: No issues found in 47 files (XXXms)\n"}, []),
        ],
        ids=["pyright_diagnostics", "pyright_strips_time_in_sec", "rumdl_strips_timing"],
    )
    def test_capture_strips_volatile_fields(self, tool: str, stdout: str, want_in, want_not_in) -> None:
        baseline = _capture_baseline([make_lint_result(tool_name=tool, stdout=stdout)])
        if want_in is not None:
            for key, want_val in want_in.items():
                assert baseline[0][key] == want_val, f"{key}: got {baseline[0][key]!r}, want {want_val!r}"
        for stripped_key in (want_not_in or []):
            diag = baseline[0].get("diagnostics", {})
            assert stripped_key not in diag.get("summary", {}), f"{stripped_key} should be stripped: {diag!r}"


# ── _diff_baseline parametrised shrinkage/addition/mixed matrix ───


@pytest.mark.parametrize(
    "saved,current,want_kind,post_assert_id",
    DIFF_BASELINE_CASES,
)
def test_diff_baseline_matrix(
    tmp_path: Path,
    saved: "dict[str, Any] | list[dict[str, Any]]",
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
        self, tmp_path: Path, saved: dict[str, Any], current: dict[str, Any], want_kind: str,
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
        self, tmp_path: Path, saved: dict[str, Any], results: list[LintResult], want_kind: str,
    ) -> None:
        """Exit-code changed / shrinkage / new-tool rows — each needs direct LintResult construction."""
        violations, reloaded = diff_baseline_with(tmp_path, saved, results)
        if want_kind == "no_violations":
            assert violations == [], f"Expected no violations, got {violations!r}"
            # shrinkage path: exit_code rewritten in baseline.
            if saved.get("exit_code") == 1:
                assert baseline_entry_for_tool(reloaded, saved["tool"])["exit_code"] == 0
        else:
            diff_violation_kind(violations, want_kind)

    @pytest.mark.parametrize("kind,body,want_substr", DIFF_BASELINE_PATH_ERRORS)
    def test_diff_baseline_path_errors(self, tmp_path: Path, kind: str, body, want_substr) -> None:
        """Missing baseline → 'not found'; invalid JSON → 'Cannot read'; empty + empty → no violation."""
        if kind == "missing":
            violations = _diff_baseline([make_lint_result()], Path("/nonexistent/baseline.json"))
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
        baseline_path.write_text(json.dumps([
            {"tool": "ruff check", "exit_code": 0, "output": "src/a.py:1: error A\nsrc/b.py:2: error B"}
        ]))
        baseline_path.chmod(0o444)
        try:
            results = [make_lint_result(tool_name="ruff check", exit_code=0, stdout="src/a.py:1: error A")]
            violations = _diff_baseline(results, baseline_path)
            assert any("cannot write baseline" in v.lower() for v in violations), violations
        finally:
            baseline_path.chmod(0o644)


# ── overwrite-baseline coverage (D11) ──────────────────────────────


class TestOverwriteBaseline:
    """``--overwrite-baseline`` rewrites an existing baseline file (with fakes)."""

    def test_overwrite_via_main_and_run_lint(self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                             monkeypatch: pytest.MonkeyPatch) -> None:
        """``main --overwrite-baseline`` rewrites an existing baseline + emits banner; ``run_lint`` does the same."""
        baseline_file = tmp_path / "overwrite.json"
        _, cfg = install_fake_runner(monkeypatch, default_py_dirs=None)
        main(["--path", "src/main.py", "--baseline", str(baseline_file)], config=cfg)
        install_fake_runner(monkeypatch)
        main(["--overwrite-baseline", "--baseline", str(baseline_file), "--path", "src/main.py"], config=cfg)
        assert "Overwriting baseline" in capsys.readouterr().out
        baseline_file2 = tmp_path / "overwrite2.json"  # run_lint(): same behavior via the API
        install_fake_runner(monkeypatch)
        run_lint(path="src/main.py", baseline=str(baseline_file2))
        install_fake_runner(monkeypatch)
        run_lint(path="src/main.py", baseline=str(baseline_file2), overwrite_baseline=True)
        assert json.loads(baseline_file2.read_text()) and json.loads(baseline_file.read_text())

    def test_no_overwrite_without_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without ``--overwrite-baseline``, an existing baseline is diffed, not rewritten."""
        baseline_file = tmp_path / "no_overwrite.json"
        saved = [{"tool": "ruff check", "exit_code": 0, "output": "first output"}]
        baseline_file.write_text(json.dumps(saved))
        fake = fake_run_cmd_factory({
            "ruff check": make_lint_result(tool_name="ruff check", exit_code=0, stdout="first output"),
        })
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        main(["--baseline", str(baseline_file), "--path", "src/main.py"],
             config=RunnerConfig(cwd=tmp_path, package_name="python_setup_lint"))
        data = json.loads(baseline_file.read_text())
        assert len(data) == 1 and data[0]["output"] == "first output"


# ── Observability: _print_result output format ───────────────────


class TestPrintResult:
    """``_print_result`` produces expected output format."""

    @pytest.mark.parametrize("exit_code,stdout,stderr,want_tokens", PRINT_FORMAT_CASES)
    def test_print_format(self, capsys: pytest.CaptureFixture[str], exit_code, stdout, stderr,
                          want_tokens) -> None:
        """One row per PASSED/FAILED — each asserts expected markers + content surface."""
        _print_result(make_lint_result(tool_name="mytool", exit_code=exit_code,
                                       stdout=stdout or "", stderr=stderr or ""))
        out = capsys.readouterr().out
        for tok in want_tokens:
            assert tok in out, f"expected {tok!r} in output: {out!r}"

    def test_print_stderr_before_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        """stderr line always renders before stdout line in ``_print_result`` output."""
        _print_result(make_lint_result(tool_name="mytool", exit_code=1,
                                       stderr="stderr line\n", stdout="stdout line\n"))
        out = capsys.readouterr().out
        assert out.index("stderr line") < out.index("stdout line")


# ── run_lint orchestration ────────────────────────────────────────


class TestRunLintOrchestration:
    """Fake-driven ``run_lint``: --no-fail-fast, tools_override, package_name."""

    def test_no_fail_fast_captures_all_tools_and_returns_int(self, tmp_path: Path,
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
        fake, _ = install_fake_runner(monkeypatch)
        baseline_file = tmp_path / "noff.json"
        rc = run_lint(config=tmp_config(tmp_path), baseline=str(baseline_file), no_fail_fast=True)
        assert isinstance(rc, int)
        assert {c.label for c in fake.calls} == {t.name for t in TOOLS}
        assert len(json.loads(baseline_file.read_text())) == len(TOOLS)

    def test_tools_override_limits_tools(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        install_fake_runner(monkeypatch)
        baseline_file = tmp_path / "tools_override.json"
        run_lint(config=tmp_config(tmp_path, tools_override=["ruff check", "mypy"]),
                 baseline=str(baseline_file), no_fail_fast=True)
        assert {e["tool"] for e in json.loads(baseline_file.read_text())} == {"ruff check", "mypy"}

    @pytest.mark.parametrize("package_name,want_stubtest,want_count_delta", PACKAGE_NAME_STUBTEST_CASES)
    def test_package_name_governs_stubtest_verifytypes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        package_name: str | None, want_stubtest: bool, want_count_delta: int,
    ) -> None:
        fake, _ = install_fake_runner(monkeypatch, package_name=package_name)
        run_lint(config=RunnerConfig(cwd=tmp_path, package_name=package_name),
                 baseline=str(tmp_path / "pkg.json"), no_fail_fast=True)
        dispatched = {c.label for c in fake.calls}
        assert ("mypy.stubtest" in dispatched) == want_stubtest
        assert ("pyright verify types" in dispatched) == want_stubtest
        assert len(dispatched) == len(TOOLS) + want_count_delta


# ── CLI argument parsing via main() (parametrised) ────────────────


@pytest.mark.parametrize("args", MAIN_ARGPARSE_CASES)
def test_main_argparse_accepts_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, args: list[str],
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
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fix: bool, override_stdout: str | None,
    ) -> None:
        """Baseline capture path: optional --fix; ruff check entry present in baseline JSON."""
        ruff_result = (None if override_stdout is None
                       else make_lint_result(tool_name="ruff check", exit_code=0, stdout=override_stdout))
        if ruff_result is not None:
            fake = fake_run_cmd_factory({"ruff check": ruff_result})
            monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        else:
            install_fake_runner(monkeypatch)
        baseline_file = tmp_path / "test_baseline.json"
        run_lint(config=tmp_config(tmp_path), fix=fix, baseline=str(baseline_file), no_fail_fast=True)
        assert any(e["tool"] == "ruff check" for e in json.loads(baseline_file.read_text()))

    def test_baseline_create_and_diff_paths(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Baseline create → diff round-trip: entries have tool/exit_code; second run matches → exit 0."""
        install_fake_runner(monkeypatch)
        baseline_file = tmp_path / "test_baseline.json"
        run_lint(config=tmp_config(tmp_path), baseline=str(baseline_file))  # create
        data = json.loads(baseline_file.read_text())
        assert isinstance(data, list) and data and all("tool" in e and "exit_code" in e for e in data)
        assert run_lint(config=tmp_config(tmp_path), baseline=str(baseline_file)) == 0  # re-diff matches

    def test_baseline_exits_nonzero_on_new_violation(self, tmp_path: Path) -> None:
        """Stored baseline with no issues + current new ruff issue → ``_diff_baseline`` returns truthy."""
        baseline_file = tmp_path / "test_baseline_new_violation.json"
        baseline_file.write_text(json.dumps([{"tool": "ruff check", "exit_code": 0, "output": "no issues"}]))
        results = [make_lint_result(tool_name="ruff check", exit_code=1, stdout="error: unused import")]
        assert _diff_baseline(results, baseline_file)


# ── Statistics: _build_statistics_flags (parametrised) ─────────────


@pytest.mark.parametrize("tool_name,expected", STATISTICS_FLAG_CASES)
def test_build_statistics_flags(tool_name: str, expected: list[str]) -> None:
    """One row per (tool name, expected flag list); also exercises no-stat tools + cmd propagation."""
    spec = ToolSpec(tool_name, ["tool"])
    assert _build_statistics_flags(spec) == expected, f"{tool_name}: got {_build_statistics_flags(spec)!r}"


def test_statistics_flag_appended_to_build_command_and_empty_for_no_stat_tools() -> None:
    """``_build_command`` + ``_build_statistics_flags(spec)`` propagate ``--statistics``; no-stat tools get ``[]``."""
    cmd = _build_command(ToolSpec("ruff check", ["ruff", "check"]), config=_CONFIG)
    cmd.extend(_build_statistics_flags(ToolSpec("ruff check", ["ruff", "check"])))
    assert "--statistics" in cmd
    for name in ("mypy.stubtest", "detect-secrets", "pyright verify types"):
        assert _build_statistics_flags(ToolSpec(name, ["tool"])) == [], f"{name} should have no flags"


# ── Statistics: per-tool parsers (parametrised) ───────────────────


@pytest.mark.parametrize("tool_name,stdout,stderr,expected", PARSER_STATISTICS_CASES)
def test_statistics_parser(tool_name: str, stdout: str, stderr: str, expected: list[tuple[str, int]]) -> None:
    """One row per (tool, raw input, expected (rule, count) pairs) — dispatched via ``_STATISTICS_PARSERS``."""
    parser = _STATISTICS_PARSERS[tool_name]
    result = parser(stdout, stderr)
    assert dict(result) == dict(expected), (
        f"{tool_name} parser returned {dict(result)!r}, expected {dict(expected)!r}"
    )


def test_statistics_parsers_cover_all_tools() -> None:
    """``_STATISTICS_PARSERS`` has an entry for every built-in tool name."""
    assert {t.name for t in TOOLS} <= set(_STATISTICS_PARSERS)


def test_parse_strategies_includes_all_keys() -> None:
    """``PARSE_STRATEGIES`` includes the 11 built-in stat parsers + T11 generic + ``none`` sentinel."""
    assert {"regex_count", "raw_lines", "none"} <= set(PARSE_STRATEGIES)
    assert {
        "ruff_statistics", "rumdl_statistics", "pylint_json2",
        "pyright_outputjson", "pyright_verify_types", "mypy_stderr",
        "ty_concise", "tach_json", "yamllint_parsable", "stubtest_stderr",
        "detect_secrets_json",
    } <= set(PARSE_STRATEGIES)


# ── Strategy registry ──────────────────────────────────────────────


class TestLintToolRegistry:
    """STRATEGIES/LINT_TOOLS mirror the 11 built-ins AND strategies are LintTool instances."""

    @pytest.mark.parametrize(
        "registry",
        [STRATEGIES, {t.name: t for t in LINT_TOOLS}],
        ids=["STRATEGIES", "LINT_TOOLS"],
    )
    def test_registry_mirrors_builtins(self, registry: dict) -> None:
        assert set(registry) == {t.name for t in TOOLS} and len(registry) == len(TOOLS)

    def test_strategies_are_lint_tool_instances_with_matching_names(self) -> None:
        from python_setup_lint.runner import LintTool
        for name, strategy in STRATEGIES.items():
            assert isinstance(strategy, LintTool), f"Strategy {strategy!r} is not a LintTool"
            assert strategy.name == name and strategy.spec.name == name


class TestRegisterLintTool:
    """``register_lint_tool`` semantics: append-extra, idempotent, builtin-protected."""

    def test_register_appends_extra(self, isolated_runner_registries: None) -> None:
        from python_setup_lint.runner import GenericLintTool
        extra = ToolSpec("t4-extra-test-tool", ["t4extra", "check"], supports_path=True)
        register_lint_tool(extra, statistics_flag=[], parser=None, config_flag=None)
        assert any(t.name == "t4-extra-test-tool" for t in LINT_TOOLS)
        assert isinstance(STRATEGIES.get("t4-extra-test-tool"), GenericLintTool)

    def test_register_idempotent_same_name(self, isolated_runner_registries: None) -> None:
        register_lint_tool(ToolSpec("t4-idempotent-tool", ["t4ida"]))
        count_after_first = len(LINT_TOOLS)
        register_lint_tool(ToolSpec("t4-idempotent-tool", ["t4idb"]))  # update-in-place, no growth
        assert len(LINT_TOOLS) == count_after_first
        assert next(t for t in LINT_TOOLS if t.name == "t4-idempotent-tool").command == ["t4idb"]

    def test_register_does_not_replace_builtin_strategy(self, isolated_runner_registries: None) -> None:
        original_strategy = STRATEGIES["ruff check"]
        register_lint_tool(ToolSpec("ruff check", ["ruff", "duplicate"]))
        assert STRATEGIES["ruff check"] is original_strategy


class TestGenericLintTool:
    """``GenericLintTool`` synthesises command + statistics-flag plumbing from spec."""

    def test_build_command_composes_fix_path_exclude(self) -> None:
        from python_setup_lint.runner import GenericLintTool
        spec = ToolSpec("t4-generic-tool", ["t4g", "check"], supports_fix=True,
                        supports_path=True, supports_exclude=True, default_paths=["src/"])
        g = GenericLintTool(spec, statistics_flag=[], parser=None, config_flag=None)
        assert g.build_command(config=RunnerConfig(cwd=Path("/tmp")),
                               fix=True, path=None, exclude="tests/") == [
            "t4g", "check", "--fix", "src/", "--exclude", "tests/",
        ]

    @pytest.mark.parametrize(
        "override,expected",
        [
            (["--stat-foo"], ["--stat-foo"]),  # explicit override wins
        ],
        ids=["stats_override_wins"],
    )
    def test_statistics_flags_use_override(self, override: list[str], expected: list[str]) -> None:
        from python_setup_lint.runner import GenericLintTool
        g = GenericLintTool(ToolSpec("t4-stats-tool", ["t4s"]),
                            statistics_flag=override, parser=None, config_flag=None)
        assert g.statistics_flags() == expected

    def test_statistics_flags_fall_back_to_module_lookup(self) -> None:
        from python_setup_lint.runner import GenericLintTool
        g = GenericLintTool(ToolSpec("ruff check", ["ruff", "check"]),
                            statistics_flag=None, parser=None, config_flag=None)
        assert g.statistics_flags() == ["--statistics"]

    def test_parse_statistics_uses_override(self) -> None:
        from python_setup_lint.runner import GenericLintTool

        def custom_parser(stdout: str, stderr: str) -> list[tuple[str, int]]:
            return [("custom-rule", 7)]

        g = GenericLintTool(ToolSpec("t4-parse-tool", ["t4p"]),
                            statistics_flag=None, parser=custom_parser, config_flag=None)
        assert g.parse_statistics("ignored", "also-ignored") == [("custom-rule", 7)]

    def test_parse_statistics_falls_back_to_module_lookup(self) -> None:
        from python_setup_lint.runner import GenericLintTool
        g = GenericLintTool(ToolSpec("ruff check", ["ruff", "check"]),
                            statistics_flag=None, parser=None, config_flag=None)
        out = "Count\tCode\tDescription\n------\t----\t-----------\n3\tF401\tmodule imported but unused\n"
        assert ("F401", 3) in g.parse_statistics(out, "")


class TestStrategyForFallback:
    """``_strategy_for`` default-aware fallback (unknown names → GenericLintTool)."""

    def test_returns_cached_builtin(self) -> None:
        from python_setup_lint.runner import _strategy_for
        original = STRATEGIES["ruff check"]
        assert _strategy_for("ruff check", ToolSpec("ruff check", ["ruff", "check"])) is original

    def test_unknown_name_returns_generic(self) -> None:
        from python_setup_lint.runner import _strategy_for, GenericLintTool
        fake_spec = ToolSpec("t4-unknown-fallback", ["t4fake"])
        got = _strategy_for("t4-unknown-fallback", fake_spec)
        assert isinstance(got, GenericLintTool) and got.spec is fake_spec

    def test_unknown_name_does_not_mutate_strategies(self) -> None:
        from python_setup_lint.runner import _strategy_for
        _strategy_for("t4-no-cache-fallback", ToolSpec("t4-no-cache-fallback", ["t4nc"]))
        assert "t4-no-cache-fallback" not in STRATEGIES


# ── _sort_counts + grouped output ─────────────────────────────────


class TestSortCounts:
    """``_sort_counts`` ordering for default + ``--sort-by-rule``."""

    def test_default_sort_highest_count_first(self) -> None:
        result = _sort_counts(SORT_DEFAULT_COUNTS, sort_by_rule=False)
        assert [c.rule for c in result] == ["A001", "B001", "Z001"]

    def test_sort_by_rule(self) -> None:
        result = _sort_counts(SORT_BY_RULE_COUNTS, sort_by_rule=True)
        assert result[0].rule == "A001" and result[0].tool == "tool_a" and result[0].count == 10
        assert result[2].rule == "Z001"

    def test_empty_list(self) -> None:
        assert _sort_counts([]) == []


@pytest.mark.parametrize("args", MAIN_GROUP_SORT_CASES)
def test_main_group_and_sort_by_rule_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, args: list[str],
) -> None:
    """One row per ``--group`` / ``--sort-by-rule`` permutation; ``main(args, ...)`` returns int."""
    install_fake_runner(monkeypatch)
    rc = main(args, config=RunnerConfig(cwd=tmp_path, package_name="python_setup_lint"))
    assert isinstance(rc, int)


def test_run_lint_group_sort_by_rule_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    """``run_lint(group=..., sort_by_rule=True)`` is accepted."""
    install_fake_runner(monkeypatch)
    rc = run_lint(config=RunnerConfig(cwd=Path("/tmp"), package_name="python_setup_lint"),
                  statistics=True, group="tool", sort_by_rule=True)
    assert isinstance(rc, int)


# ── Grouped output content verification ───────────────────────────


class TestGroupedOutput:
    """``_print_statistics_grouped`` content — parametrised via shared ``GROUPED_OUTPUT_CASES``."""

    @pytest.mark.parametrize("group,counts,header,markers,tokens", GROUPED_OUTPUT_CASES)
    def test_group_format_and_subtotals(
        self, capsys: pytest.CaptureFixture[str], group: str, counts: list[ViolationCount],
        header: str, markers: list[str], tokens: list[str],
    ) -> None:
        _print_statistics_grouped(counts, group=group)
        out = capsys.readouterr().out
        if markers:
            assert header in out
            for marker in markers:
                assert marker in out
        for token in tokens:
            assert token in out

    def test_group_rule_with_sort_by_rule_orders_sections(self, capsys: pytest.CaptureFixture[str]) -> None:
        """``--group rule --sort-by-rule`` orders rule sections alphabetically."""
        _print_statistics_grouped(GROUPED_SORT_BY_RULE_COUNTS, group="rule", sort_by_rule=True)
        out = capsys.readouterr().out
        assert out.index("[A001]") < out.index("[Z001]")


def test_invalid_group_value_rejected() -> None:
    """argparse rejects ``--group bogus`` with a non-zero exit code."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--statistics", "--group", "bogus"])
    assert exc_info.value.code != 0


# ── T8: fail-fast on malformed pyproject / invalid tool config ─────


class TestT8FailFastConfig:
    """T8 fail-fast on malformed pyproject / invalid tool config.

    Uses the ``isolated_runner_registries`` fixture so the extras-merge tests
    don't leak mutations into ``LINT_TOOLS``/``STRATEGIES``.
    """

    @pytest.mark.parametrize("body,reason_want,exact_match", MALFORMATION_CASES)
    def test_malformed_pyproject_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        isolated_runner_registries: None, body: str, reason_want: str, exact_match: bool,
    ) -> None:
        """Each T8 malformation row asserts ``ExtraToolsConfigError`` carries file path + locked reason."""
        pyproject = write_pyproject(tmp_path, body)
        install_fake_runner(monkeypatch)
        with pytest.raises(ExtraToolsConfigError) as exc_info:
            run_lint(config=lint_config(tmp_path), no_fail_fast=True)
        err = exc_info.value
        assert err.location == str(pyproject), f"location: got {err.location!r}, want {str(pyproject)!r}"
        if exact_match:
            assert err.reason == reason_want, f"reason: got {err.reason!r}, want {reason_want!r}"
        else:
            assert reason_want in err.reason, f"reason: got {err.reason!r}, want substring {reason_want!r}"

    def test_unknown_config_tool_id(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
        isolated_runner_registries: None,
    ) -> None:
        """Unknown ``--config bogus=...`` exits code 2, lists supported tools, not in _SUPPORTED_CONFIG_KEYS."""
        install_fake_runner(monkeypatch)
        with pytest.raises(SystemExit) as exc_info:
            main(["--config", "bogus=/some/path.toml"], config=lint_config(tmp_path))
        assert exc_info.value.code == 2
        err = capsys.readouterr().err
        assert "bogus" in err and "ruff" in err and "pyright" in err
        assert "bogus" not in _SUPPORTED_CONFIG_KEYS
        assert {"ruff", "mypy", "pylint", "pyright", "rumdl", "ty"} <= _SUPPORTED_CONFIG_KEYS

    def test_bad_tools_list(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                            isolated_runner_registries: None) -> None:
        """Unknown tool name in ``tools_override`` → ExtraToolsConfigError with ``unknown tool name:`` reason."""
        install_fake_runner(monkeypatch)
        config = RunnerConfig(cwd=tmp_path, tools_override=["ruff check", "bogus-tool-name"])
        with pytest.raises(ExtraToolsConfigError) as exc_info:
            run_lint(config=config, no_fail_fast=True)
        assert exc_info.value.reason.startswith("unknown tool name: 'bogus-tool-name'")
        assert "ruff check" in exc_info.value.reason
        assert exc_info.value.location == "<RunnerConfig.tools_override>"

    def test_clean_pyproject_extras_merge_runs_clean(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_runner_registries: None,
    ) -> None:
        """A clean extras-merge pyproject with valid ``t8-grep-noqa`` tool runs to an int exit code."""
        write_pyproject(tmp_path, CLEAN_EXTRAS_PYPROJECT_BODY)
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "__init__.py").write_text("", encoding="utf-8")
        install_fake_runner(monkeypatch)
        config = lint_config(tmp_path, package_name="t8_clean",
                             tools_override=["ruff check", "t8-grep-noqa"])
        assert isinstance(run_lint(config=config, no_fail_fast=True), int)