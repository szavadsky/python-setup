"""Unit tests for ``python_setup_lint.testing`` lint-runner fakes.

Covers ``make_lint_result``, ``fake_run_cmd_factory``, and ``FakeRunCmd``
behaviour: dict dispatch, list dispatch, unknown-label fallback, cmd capture,
and a smoke integration test that exercises ``run_lint(...)`` with the fake
installed (no real subprocess spawned).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from python_setup_lint.runner import LintResult, RunnerConfig, run_lint
from python_setup_lint.testing import (
    FakeRunCmd,
    _FakeRunCmdRecord,
    fake_run_cmd_factory,
    make_lint_result,
)


# ── make_lint_result ────────────────────────────────────────────────


class TestMakeLintResult:
    """Verify the convenience factory produces correct ``LintResult``."""

    def test_defaults(self) -> None:
        r = make_lint_result()
        assert isinstance(r, LintResult)
        assert r.tool_name == "ruff check"
        assert r.exit_code == 0
        assert r.stdout == ""
        assert r.stderr == ""
        assert r.elapsed == 0.0

    def test_custom_values(self) -> None:
        r = make_lint_result(
            tool_name="mypy",
            exit_code=1,
            stdout="error found",
            stderr="details",
            elapsed=2.5,
        )
        assert r.tool_name == "mypy"
        assert r.exit_code == 1
        assert r.stdout == "error found"
        assert r.stderr == "details"
        assert r.elapsed == 2.5

    def test_partial_override(self) -> None:
        r = make_lint_result(tool_name="ruff check", exit_code=1)
        assert r.tool_name == "ruff check"
        assert r.exit_code == 1
        assert r.stdout == ""
        assert r.elapsed == 0.0


# ── fake_run_cmd_factory — dict dispatch ────────────────────────────


class TestFakeRunCmdDict:
    """Verify dict-mode dispatch by tool label."""

    def test_known_label_returns_canned_result(self) -> None:
        canned = make_lint_result(tool_name="ruff check", exit_code=1, stdout="issues")
        fake = fake_run_cmd_factory({"ruff check": canned})
        result = fake(["ruff", "check", "src/"], label="ruff check")
        assert result.exit_code == 1
        assert result.stdout == "issues"

    def test_unknown_label_returns_zero_exit_empty(self) -> None:
        """Unknown labels get a zero-exit empty result (implicit skip)."""
        canned = make_lint_result(tool_name="ruff check")
        fake = fake_run_cmd_factory({"ruff check": canned})
        result = fake(["python", "-m", "mypy.stubtest"], label="mypy.stubtest")
        assert result.exit_code == 0
        assert result.stdout == ""
        assert result.tool_name == "mypy.stubtest"

    def test_captures_cmd_and_label(self) -> None:
        canned = make_lint_result(tool_name="ruff check")
        fake = fake_run_cmd_factory({"ruff check": canned})
        fake(["ruff", "check", "src/", "--fix"], label="ruff check")
        assert len(fake.calls) == 1
        record = fake.calls[0]
        assert record.cmd == ["ruff", "check", "src/", "--fix"]
        assert record.label == "ruff check"

    def test_multiple_calls_captured_in_order(self) -> None:
        ruff_result = make_lint_result(tool_name="ruff check")
        mypy_result = make_lint_result(tool_name="mypy", exit_code=1)
        fake = fake_run_cmd_factory({"ruff check": ruff_result, "mypy": mypy_result})
        fake(["ruff", "check", "."], label="ruff check")
        fake(["mypy", "."], label="mypy")
        assert len(fake.calls) == 2
        assert fake.calls[0].label == "ruff check"
        assert fake.calls[1].label == "mypy"
        assert fake.calls[0].cmd == ["ruff", "check", "."]
        assert fake.calls[1].cmd == ["mypy", "."]

    def test_empty_dict_returns_zero_exit_empty(self) -> None:
        """Empty dict — any label returns zero-exit empty result."""
        fake = fake_run_cmd_factory({})
        result = fake(["ruff", "check", "."], label="ruff check")
        assert result.exit_code == 0
        assert result.stdout == ""
        assert result.tool_name == "ruff check"

    def test_empty_dict_multiple_labels(self) -> None:
        """Empty dict — multiple different labels all get zero-exit empty."""
        fake = fake_run_cmd_factory({})
        r1 = fake(["ruff", "check", "."], label="ruff check")
        r2 = fake(["mypy", "."], label="mypy")
        assert r1.exit_code == 0
        assert r2.exit_code == 0
        assert r1.tool_name == "ruff check"
        assert r2.tool_name == "mypy"


# ── fake_run_cmd_factory — list dispatch ────────────────────────────


class TestFakeRunCmdList:
    """Verify list-mode dispatch by call order."""

    def test_returns_results_in_order(self) -> None:
        r1 = make_lint_result(tool_name="ruff check", exit_code=0)
        r2 = make_lint_result(tool_name="mypy", exit_code=1)
        fake = fake_run_cmd_factory([r1, r2])
        assert fake(["ruff", "check", "."], label="ruff check").exit_code == 0
        assert fake(["mypy", "."], label="mypy").exit_code == 1

    def test_extra_calls_return_zero_exit_empty(self) -> None:
        r1 = make_lint_result(tool_name="ruff check")
        fake = fake_run_cmd_factory([r1])
        fake(["ruff", "check", "."], label="ruff check")
        extra = fake(["extra", "tool"], label="extra")
        assert extra.exit_code == 0
        assert extra.stdout == ""
        assert extra.tool_name == "extra"

    def test_captures_cmd_and_label(self) -> None:
        r1 = make_lint_result(tool_name="ruff check")
        fake = fake_run_cmd_factory([r1])
        fake(["ruff", "check", "--fix"], label="ruff check")
        assert len(fake.calls) == 1
        assert fake.calls[0].cmd == ["ruff", "check", "--fix"]
        assert fake.calls[0].label == "ruff check"

    def test_empty_list_returns_zero_exit_empty(self) -> None:
        """Empty list — any call returns zero-exit empty result."""
        fake = fake_run_cmd_factory([])
        result = fake(["ruff", "check", "."], label="ruff check")
        assert result.exit_code == 0
        assert result.stdout == ""
        assert result.tool_name == "ruff check"

    def test_fewer_results_than_calls(self) -> None:
        """Fewer results than calls — extra calls return zero-exit empty."""
        r1 = make_lint_result(tool_name="tool_a", exit_code=1)
        fake = fake_run_cmd_factory([r1])
        r1_out = fake(["tool_a"], label="tool_a")
        r2_out = fake(["tool_b"], label="tool_b")
        r3_out = fake(["tool_c"], label="tool_c")
        assert r1_out.exit_code == 1
        assert r2_out.exit_code == 0
        assert r3_out.exit_code == 0
        assert r2_out.tool_name == "tool_b"
        assert r3_out.tool_name == "tool_c"


# ── FakeRunCmd direct construction ─────────────────────────────────


class TestFakeRunCmdDirect:
    """Verify ``FakeRunCmd`` can be constructed directly (not just via factory)."""

    def test_dict_dispatch(self) -> None:
        canned = make_lint_result(tool_name="mypy", exit_code=2)
        fake = FakeRunCmd(results={"mypy": canned})
        result = fake(["mypy", "."], label="mypy")
        assert result.exit_code == 2

    def test_list_dispatch(self) -> None:
        r1 = make_lint_result(tool_name="tool_a", exit_code=0)
        r2 = make_lint_result(tool_name="tool_b", exit_code=1)
        fake = FakeRunCmd(results=[r1, r2])
        assert fake(["tool_a"], label="tool_a").exit_code == 0
        assert fake(["tool_b"], label="tool_b").exit_code == 1

    def test_calls_list_is_shared(self) -> None:
        """calls is a mutable list — tests can inspect it after the fact."""
        fake = FakeRunCmd(results={})
        fake(["cmd1"], label="a")
        fake(["cmd2"], label="b")
        assert len(fake.calls) == 2
        assert fake.calls[0].label == "a"
        assert fake.calls[1].label == "b"


# ── _FakeRunCmdRecord ──────────────────────────────────────────────


class TestFakeRunCmdRecord:
    """Verify the record dataclass stores expected fields."""

    def test_fields(self) -> None:
        rec = _FakeRunCmdRecord(cmd=["ruff", "check"], label="ruff check")
        assert rec.cmd == ["ruff", "check"]
        assert rec.label == "ruff check"


# ── Smoke integration: run_lint with fake installed ────────────────


class TestFakeIntegration:
    """Exercise ``run_lint(...)`` with the fake installed — no real subprocess."""

    def test_run_lint_with_fake_no_subprocess(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """run_lint with fake installed returns 0 and captures all tool commands."""
        canned = make_lint_result(tool_name="placeholder", exit_code=0)
        fake = fake_run_cmd_factory(
            {
                "tach check": canned,
                "ruff check": canned,
                "rumdl check": canned,
                "mypy": canned,
                "yamllint": canned,
                "ty check": canned,
                "mypy.stubtest": canned,
                "pyright check": canned,
                "pyright verify types": canned,
                "pylint": canned,
                "detect-secrets": canned,
            }
        )
        monkeypatch.setattr("python_setup_lint.runner._run_cmd", fake)

        config = RunnerConfig(cwd=Path.cwd(), package_name="python_setup_lint")
        rc = run_lint(
            config=config,
            path="src/python_setup_lint/runner.py",
            no_fail_fast=True,
        )
        assert rc == 0
        # All 11 tools should have been called
        assert len(fake.calls) == 11
        # Each call has a non-empty cmd and a label
        for call in fake.calls:
            assert len(call.cmd) > 0, f"Empty cmd for label={call.label}"
            assert call.label != "", "Empty label"

    def test_fake_captures_fix_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When --fix is passed, the fake records the --fix flag in cmd."""
        canned = make_lint_result(tool_name="placeholder", exit_code=0)
        fake = fake_run_cmd_factory(
            {
                "tach check": canned,
                "ruff check": canned,
                "rumdl check": canned,
                "mypy": canned,
                "yamllint": canned,
                "ty check": canned,
                "mypy.stubtest": canned,
                "pyright check": canned,
                "pyright verify types": canned,
                "pylint": canned,
                "detect-secrets": canned,
            }
        )
        monkeypatch.setattr("python_setup_lint.runner._run_cmd", fake)

        config = RunnerConfig(cwd=Path.cwd(), package_name="python_setup_lint")
        run_lint(config=config, path="src/python_setup_lint/runner.py", fix=True, no_fail_fast=True)

        # ruff check, rumdl check, ty check should have --fix in their cmd
        fix_labels = {"ruff check", "rumdl check", "ty check"}
        for call in fake.calls:
            if call.label in fix_labels:
                assert "--fix" in call.cmd, f"Expected --fix in cmd for {call.label}, got {call.cmd}"

    def test_fake_captures_exclude_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When --exclude is passed, the fake records the exclude flag in cmd."""
        canned = make_lint_result(tool_name="placeholder", exit_code=0)
        fake = fake_run_cmd_factory(
            {
                "tach check": canned,
                "ruff check": canned,
                "rumdl check": canned,
                "mypy": canned,
                "yamllint": canned,
                "ty check": canned,
                "mypy.stubtest": canned,
                "pyright check": canned,
                "pyright verify types": canned,
                "pylint": canned,
                "detect-secrets": canned,
            }
        )
        monkeypatch.setattr("python_setup_lint.runner._run_cmd", fake)

        config = RunnerConfig(cwd=Path.cwd(), package_name="python_setup_lint")
        run_lint(config=config, path="src/python_setup_lint/runner.py", exclude="tests/", no_fail_fast=True)

        # tach check, ruff check, rumdl check, ty check support exclude
        exclude_labels = {"tach check", "ruff check", "rumdl check", "ty check"}
        for call in fake.calls:
            if call.label in exclude_labels:
                assert "--exclude" in call.cmd or "-e" in call.cmd, (
                    f"Expected exclude flag in cmd for {call.label}, got {call.cmd}"
                )

    def test_run_lint_with_package_name_none_skips_stubtest_verifytypes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When package_name=None, stubtest and verifytypes are not called (9 tools)."""
        canned = make_lint_result(tool_name="placeholder", exit_code=0)
        fake = fake_run_cmd_factory(
            {
                "tach check": canned,
                "ruff check": canned,
                "rumdl check": canned,
                "mypy": canned,
                "yamllint": canned,
                "ty check": canned,
                "mypy.stubtest": canned,
                "pyright check": canned,
                "pyright verify types": canned,
                "pylint": canned,
                "detect-secrets": canned,
            }
        )
        monkeypatch.setattr("python_setup_lint.runner._run_cmd", fake)

        config = RunnerConfig(cwd=Path.cwd(), package_name=None)
        rc = run_lint(config=config, path="src/python_setup_lint/runner.py", no_fail_fast=True)
        assert rc == 0
        # 11 tools total, but stubtest and verifytypes are skipped → 9 calls
        assert len(fake.calls) == 9, f"Expected 9 calls, got {len(fake.calls)}"
        called_labels = {c.label for c in fake.calls}
        assert "mypy.stubtest" not in called_labels
        assert "pyright verify types" not in called_labels

    def test_fake_no_subprocess_spawned(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify that no subprocess is spawned when the fake is installed."""
        import subprocess

        original_run = subprocess.run
        spy_calls: list[list[str]] = []

        def spy_run(*args: object, **kwargs: object) -> object:
            cmd = args[0] if args else kwargs.get("args", [])
            spy_calls.append(list(cmd) if isinstance(cmd, (list, tuple)) else [str(cmd)])
            return original_run(*args, **kwargs)

        monkeypatch.setattr(subprocess, "run", spy_run)

        canned = make_lint_result(tool_name="placeholder", exit_code=0)
        fake = fake_run_cmd_factory(
            {
                "tach check": canned,
                "ruff check": canned,
                "rumdl check": canned,
                "mypy": canned,
                "yamllint": canned,
                "ty check": canned,
                "mypy.stubtest": canned,
                "pyright check": canned,
                "pyright verify types": canned,
                "pylint": canned,
                "detect-secrets": canned,
            }
        )
        monkeypatch.setattr("python_setup_lint.runner._run_cmd", fake)

        config = RunnerConfig(cwd=Path.cwd(), package_name="python_setup_lint")
        run_lint(config=config, path="src/python_setup_lint/runner.py", no_fail_fast=True)

        # The fake intercepts all _run_cmd calls — subprocess.run should not be
        # called by the runner.  (It may be called by pytest internals or imports.)
        runner_subprocess_calls = [c for c in spy_calls if "ruff" in c or "mypy" in c or "pylint" in c]
        assert len(runner_subprocess_calls) == 0, (
            f"Expected no subprocess.run for lint tools, got: {runner_subprocess_calls}"
        )
