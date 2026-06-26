"""Unit tests for ``python_setup_lint.runner``.

Per-tool / per-flag rows are parametrised via shared tables in
``tests/runner/_factories.py`` (T12 consolidation).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from python_setup_lint.runner import STRATEGIES, TOOLS, TOOLS_BY_NAME, RunnerConfig, ToolSpec, register_lint_tool, run_lint
from python_setup_lint.runner.cmd_build import _build_command, _expand_globs, _find_py_files
from python_setup_lint.runner.output import _print_result
import python_setup_lint.runner.output as _output_module
from python_setup_lint.testing import fake_run_cmd_factory, make_lint_result
from tests.runner._factories import canned_results_all_tools
from tests.runner._factories_extras import (
    EXPAND_GLOBS_CASES,
    FIND_PY_FILES_BOUNDARY_CASES,
    PRINT_FORMAT_CASES,
    STRATEGY_TOKENS_CASES,
)
from tests.runner._factories_tables import BUILD_COMMAND_CASES

_CONFIG = RunnerConfig(cwd=Path.cwd())


# ── ToolSpec / TOOLS table ─────────────────────────────────────────


class TestToolSpec:
    """The static 11-tool table invariant."""

    def test_known_tools_present(self) -> None:
        assert {t.name for t in TOOLS} == {
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

    def test_autofix_and_no_duplicate_names(self) -> None:
        assert {t.name for t in TOOLS if t.supports_fix} == {
            "ruff check",
            "rumdl check",
            "ty check",
        }
        assert all(t.name for t in TOOLS)
        assert len({t.name for t in TOOLS}) == len(TOOLS) == 11

    def test_yamllint_default_paths_is_dot(self) -> None:
        """yamllint default_paths changed from config/*.yaml to . (T5 fix)."""
        yamllint_spec = TOOLS_BY_NAME["yamllint"]
        assert yamllint_spec.default_paths == ["."], (
            f"Expected ['.'], got {yamllint_spec.default_paths!r}"
        )


# ── register_lint_tool identity ────────────────────────────────────


class TestRegisterLintToolIdentity:
    """``register_lint_tool`` is the same function from both import paths."""

    def test_extra_tools_imports_dispatch_register(self) -> None:
        """extra_tools.register_lint_tool is dispatch.register_lint_tool (re-export)."""
        from python_setup_lint.runner.dispatch import register_lint_tool as dispatch_reg
        from python_setup_lint.runner.extra_tools import register_lint_tool as extra_reg  # type: ignore[attr-defined]

        assert dispatch_reg is extra_reg, (
            "extra_tools.register_lint_tool must be the same function object "
            "as dispatch.register_lint_tool"
        )

    def test_runner_init_exports_dispatch_register(self) -> None:
        """``python_setup_lint.runner.register_lint_tool`` is dispatch.register_lint_tool."""
        from python_setup_lint.runner.dispatch import register_lint_tool as dispatch_reg

        assert register_lint_tool is dispatch_reg, (
            "runner.__init__ must re-export dispatch.register_lint_tool"
        )


# ── _build_command (parametrised via shared table) ────────────────


@pytest.mark.parametrize("spec_kwargs,build_kwargs,expected", BUILD_COMMAND_CASES)
def test_build_command(
    spec_kwargs: dict[str, Any], build_kwargs: dict[str, Any], expected: list[str]
) -> None:
    """Covers path/fix/exclude/override-defaults — one row per (spec, kwargs, cmd)."""
    spec = ToolSpec(**spec_kwargs)
    assert _build_command(spec, config=_CONFIG, **build_kwargs) == expected


class TestStrategyBuildCommand:
    """Strategy-driven ``build_command`` cases — exercises LintTool subclasses."""

    def test_pylint_strategy_expands_py_files(self) -> None:
        from python_setup_lint.runner.dispatch import _PylintLintTool

        cmd = _PylintLintTool(
            ToolSpec("pylint", ["pylint"], supports_path=True)
        ).build_command(config=_CONFIG, _path="src/python_setup_lint")
        assert cmd[0] == "pylint"
        # Auto-discovery may inject --rcfile <path> before .py files; skip those.
        py_files = [a for a in cmd[1:] if a.endswith(".py")]
        assert len(py_files) > 0 and all(a.endswith(".py") for a in py_files)

    def test_pylint_rcfile_auto_discovery(self) -> None:
        """_resolve_pylintrc discovers config/.pylintrc when no explicit path given."""
        from python_setup_lint.runner.dispatch import _PylintLintTool

        cwd = Path.cwd()
        rcfile = _PylintLintTool._resolve_pylintrc({}, cwd)  # type: ignore[attr-defined]
        assert rcfile is not None, "Expected auto-discovered rcfile"
        assert rcfile.name == ".pylintrc"
        assert rcfile.is_file()

    def test_pylint_rcfile_explicit_override(self, tmp_path: Path) -> None:
        """_resolve_pylintrc returns explicit config_paths entry when provided."""
        from python_setup_lint.runner.dispatch import _PylintLintTool

        fake_rc = tmp_path / "custom.pylintrc"
        fake_rc.write_text("[MASTER]\n")
        rcfile = _PylintLintTool._resolve_pylintrc({"pylint": fake_rc}, Path.cwd())  # type: ignore[attr-defined]
        assert rcfile == fake_rc

    def test_pylint_rcfile_none_when_missing(self, tmp_path: Path) -> None:
        """_resolve_pylintrc returns None when no rcfile exists."""
        from python_setup_lint.runner.dispatch import _PylintLintTool

        rcfile = _PylintLintTool._resolve_pylintrc({}, tmp_path)  # type: ignore[attr-defined]
        assert rcfile is None

    def test_pylint_rcfile_project_root_fallback(self, tmp_path: Path) -> None:
        """_resolve_pylintrc falls back to project-root .pylintrc when config/.pylintrc missing."""
        from python_setup_lint.runner.dispatch import _PylintLintTool

        # Create only project-root .pylintrc, NOT config/.pylintrc
        (tmp_path / ".pylintrc").write_text("[MASTER]\n")
        rcfile = _PylintLintTool._resolve_pylintrc({}, tmp_path)  # type: ignore[attr-defined]
        assert rcfile is not None
        assert rcfile == tmp_path / ".pylintrc"
        assert rcfile.is_file()

    def test_pylint_rcfile_prefers_config_over_root(self, tmp_path: Path) -> None:
        """_resolve_pylintrc prefers config/.pylintrc over project-root .pylintrc."""
        from python_setup_lint.runner.dispatch import _PylintLintTool

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / ".pylintrc").write_text("[MASTER]\nconfig\n")
        (tmp_path / ".pylintrc").write_text("[MASTER]\nroot\n")
        rcfile = _PylintLintTool._resolve_pylintrc({}, tmp_path)  # type: ignore[attr-defined]
        assert rcfile == config_dir / ".pylintrc"
        assert rcfile.read_text() == "[MASTER]\nconfig\n"

    def test_pylint_build_command_injects_rcfile(self) -> None:
        """build_command includes --rcfile when auto-discovered."""
        from python_setup_lint.runner.dispatch import _PylintLintTool

        cmd = _PylintLintTool(
            ToolSpec("pylint", ["pylint"], supports_path=True)
        ).build_command(config=_CONFIG, _path="src/python_setup_lint")
        assert "--rcfile" in cmd, f"Expected --rcfile in {cmd!r}"
        rcfile_idx = cmd.index("--rcfile")
        assert rcfile_idx + 1 < len(cmd)
        rcfile_path = Path(cmd[rcfile_idx + 1])
        assert rcfile_path.name == ".pylintrc"

    def test_yamllint_strategy_expands_glob(self) -> None:
        cmd = _build_command(
            ToolSpec(
                "yamllint",
                ["yamllint"],
                supports_path=True,
                default_paths=["src/**/*.py"],
            ),
            config=_CONFIG,
        )
        assert (
            cmd[0] == "yamllint"
            and len(cmd) > 1
            and all(a.endswith(".py") for a in cmd[1:])
        )

    @pytest.mark.parametrize(
        "strategy_name,package_name,expected_tokens",
        STRATEGY_TOKENS_CASES,
    )
    def test_stubtest_and_verifytypes_strategy_with_package_name(
        self,
        strategy_name: str,
        package_name: str,
        expected_tokens: list[str],
    ) -> None:
        config = RunnerConfig(cwd=Path.cwd(), package_name=package_name)
        cmd = STRATEGIES[strategy_name].build_command(config=config)
        for tok in expected_tokens:
            assert tok in cmd, f"expected {tok!r} in {cmd!r}"

    def test_detect_secrets_strategy_bash_pipeline(self) -> None:
        cmd = STRATEGIES["detect-secrets"].build_command(
            config=RunnerConfig(cwd=Path.cwd())
        )
        assert cmd[:2] == ["bash", "-c"]
        assert "detect-secrets-hook" in cmd[2] and "--baseline" in cmd[2]


# ── Path helpers ─────────────────────────────────────────────────


class TestPathHelpers:
    """``_find_py_files`` and ``_expand_globs`` edge cases."""

    def test_find_py_files_in_dir(self) -> None:
        files = _find_py_files(["src/python_setup_lint"], cwd=Path.cwd())
        assert (
            files
            and all(f.endswith(".py") for f in files)
            and all(not Path(f).is_absolute() for f in files)
        )

    def test_find_py_files_sorted_and_dedupe(self) -> None:
        files = _find_py_files(
            ["src/python_setup_lint", "src/python_setup_lint"], cwd=Path.cwd()
        )
        assert files == sorted(files) and len(files) == len(set(files))

    @pytest.mark.parametrize("paths,expected", FIND_PY_FILES_BOUNDARY_CASES)
    def test_find_py_files_boundary(
        self, paths: list[str], expected: list[str]
    ) -> None:
        assert _find_py_files(paths, cwd=Path.cwd()) == expected

    def test_find_py_files_ignores_non_py(self) -> None:
        # ``src/python_setup_lint`` has both .py and .pyi — only .py kept.
        assert all(
            f.endswith(".py")
            for f in _find_py_files(["src/python_setup_lint"], cwd=Path.cwd())
        )

    @pytest.mark.parametrize("paths,check", EXPAND_GLOBS_CASES)
    def test_expand_globs(self, paths: list[str], check) -> None:  # type: ignore[no-untyped-def]
        assert check(_expand_globs(paths, cwd=Path.cwd()))

    def test_expand_globs_yamllint_config_glob(self, tmp_path: Path) -> None:
        """yamllint ``config/*.yaml`` glob resolves to actual files under cwd/config/."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "test.yaml").write_text("key: value\n")
        (config_dir / "other.yaml").write_text("foo: bar\n")
        result = _expand_globs(["config/*.yaml"], cwd=tmp_path)
        assert len(result) == 2
        assert "config/test.yaml" in result
        assert "config/other.yaml" in result

    def test_expand_globs_no_match_returns_empty(self, tmp_path: Path) -> None:
        """Glob with no matching files returns empty list (no crash)."""
        result = _expand_globs(["config/*.yaml"], cwd=tmp_path)
        assert result == []


# ── T1: detect-secrets bootstrap ──────────────────────────────────


class TestDetectSecretsBootstrap:
    """``_DetectSecretsLintTool`` bootstraps baseline when missing."""

    def test_bootstrap_when_baseline_missing(self, tmp_path: Path) -> None:
        """When ``.secrets.baseline`` does not exist, build_command returns a bootstrap scan command."""
        from python_setup_lint.runner.dispatch import _DetectSecretsLintTool

        config = RunnerConfig(cwd=tmp_path)
        cmd = _DetectSecretsLintTool(
            ToolSpec("detect-secrets", ["detect-secrets-hook"])
        ).build_command(config=config)
        assert cmd[:2] == ["bash", "-c"]
        assert "detect-secrets scan" in cmd[2]
        assert ".secrets.baseline" in cmd[2]

    def test_standard_pipeline_when_baseline_exists(self, tmp_path: Path) -> None:
        """When ``.secrets.baseline`` exists, build_command returns the standard git-ls-files pipeline."""
        from python_setup_lint.runner.dispatch import _DetectSecretsLintTool

        (tmp_path / ".secrets.baseline").write_text("{}")
        config = RunnerConfig(cwd=tmp_path)
        cmd = _DetectSecretsLintTool(
            ToolSpec("detect-secrets", ["detect-secrets-hook"])
        ).build_command(config=config)
        assert cmd[:2] == ["bash", "-c"]
        assert "git ls-files" in cmd[2]
        assert "detect-secrets-hook" in cmd[2]
        assert "--baseline" in cmd[2]

    def test_bootstrap_with_custom_baseline_path(self, tmp_path: Path) -> None:
        """Custom ``secrets_baseline`` path is respected in bootstrap command."""
        from python_setup_lint.runner.dispatch import _DetectSecretsLintTool

        config = RunnerConfig(cwd=tmp_path, secrets_baseline="config/secrets.baseline")
        cmd = _DetectSecretsLintTool(
            ToolSpec("detect-secrets", ["detect-secrets-hook"])
        ).build_command(config=config)
        assert "config/secrets.baseline" in cmd[2]


# ── T1: tach.toml ships ──────────────────────────────────────────


class TestTachConfig:
    """``tach.toml`` exists in the project root."""

    def test_tach_toml_exists(self) -> None:
        """tach.toml is present in the python-setup project root."""
        project_root = Path(__file__).resolve().parent.parent.parent
        tach_toml = project_root / "tach.toml"
        assert tach_toml.is_file(), f"Expected {tach_toml} to exist"

    def test_tach_toml_has_source_roots(self) -> None:
        """tach.toml declares source_roots so tach check can run."""
        import tomllib

        project_root = Path(__file__).resolve().parent.parent.parent
        tach_toml = project_root / "tach.toml"
        data = tomllib.loads(tach_toml.read_text())
        assert "source_roots" in data
        assert "src" in data["source_roots"]


# ── T1: .pylintrc has no max-complexity ──────────────────────────


class TestPylintrcNoMaxComplexity:
    """``config/.pylintrc`` has no ``max-complexity`` (T1 fix)."""

    def test_pylintrc_no_max_complexity(self) -> None:
        """The shipped .pylintrc does not contain max-complexity (removed in T1)."""
        project_root = Path(__file__).resolve().parent.parent.parent
        pylintrc = project_root / "config" / ".pylintrc"
        assert pylintrc.is_file(), f"Expected {pylintrc} to exist"
        text = pylintrc.read_text()
        assert "max-complexity" not in text, (
            "max-complexity should be absent from .pylintrc (removed in T1)"
        )


# ── T1: observability — stderr skip lines ────────────────────────


class TestObservabilitySkipLines:
    """Stderr skip lines for tools that legitimately cannot run."""

    def test_package_name_none_emits_stderr_skip(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``package_name=None`` prints SKIPPED lines to stderr for stubtest+verifytypes."""

        fake = fake_run_cmd_factory(canned_results_all_tools())
        monkeypatch.setattr(_output_module, "_run_cmd", fake)
        config = RunnerConfig(cwd=Path.cwd(), package_name=None)
        run_lint(config=config, no_fail_fast=True)
        captured = capsys.readouterr()
        assert "SKIPPED: --package-name not set" in captured.err
        assert "[mypy.stubtest]" in captured.err
        assert "[pyright verify types]" in captured.err

    def test_fix_na_emits_stderr(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``--fix`` on a tool that does not support autofix prints N/A to stderr."""

        fake = fake_run_cmd_factory(canned_results_all_tools())
        monkeypatch.setattr(_output_module, "_run_cmd", fake)
        config = RunnerConfig(cwd=Path.cwd(), package_name="python_setup_lint")
        run_lint(config=config, fix=True, no_fail_fast=True)
        captured = capsys.readouterr()
        assert "--fix: N/A" in captured.err

    def test_path_na_emits_stderr(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``--path`` on a tool that does not support path scoping prints N/A to stderr."""

        fake = fake_run_cmd_factory(canned_results_all_tools())
        monkeypatch.setattr(_output_module, "_run_cmd", fake)
        config = RunnerConfig(cwd=Path.cwd(), package_name="python_setup_lint")
        run_lint(config=config, path="src/main.py", no_fail_fast=True)
        captured = capsys.readouterr()
        assert "--path: N/A" in captured.err

    def test_exclude_na_emits_stderr(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``--exclude`` on a tool that does not support exclude prints N/A to stderr."""

        fake = fake_run_cmd_factory(canned_results_all_tools())
        monkeypatch.setattr(_output_module, "_run_cmd", fake)
        config = RunnerConfig(cwd=Path.cwd(), package_name="python_setup_lint")
        run_lint(config=config, exclude="tests/", no_fail_fast=True)
        captured = capsys.readouterr()
        assert "--exclude: N/A" in captured.err


# ── Observability: _print_result output format ───────────────────


class TestPrintResult:
    """``_print_result`` produces expected output format."""

    @pytest.mark.parametrize("exit_code,stdout,stderr,want_tokens", PRINT_FORMAT_CASES)
    def test_print_format(  # type: ignore[no-untyped-def]
        self, capsys: pytest.CaptureFixture[str], exit_code, stdout, stderr, want_tokens
    ) -> None:
        """One row per PASSED/FAILED — each asserts expected markers + content surface."""
        _print_result(
            make_lint_result(
                tool_name="mytool",
                exit_code=exit_code,
                stdout=stdout or "",
                stderr=stderr or "",
            )
        )
        out = capsys.readouterr().out
        for tok in want_tokens:
            assert tok in out, f"expected {tok!r} in output: {out!r}"

    def test_print_stderr_before_stdout(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """stderr line always renders before stdout line in ``_print_result`` output."""
        _print_result(
            make_lint_result(
                tool_name="mytool",
                exit_code=1,
                stderr="stderr line\n",
                stdout="stdout line\n",
            )
        )
        out = capsys.readouterr().out
        assert out.index("stderr line") < out.index("stdout line")
