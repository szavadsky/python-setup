"""ADR-005 contract tests: ``ruff format`` modes + single-source 14-tool registry.

The runner keeps 14 built-in tools — 13 analysis/format-check tools plus the
``ruff format`` formatter.  Normal (non-fix) passes must run the formatter in
check mode; only the fix-only phase may mutate files.  Registry constants are
owned by :mod:`python_setup_lint.runner.dispatch` and re-exported from
:mod:`python_setup_lint.runner` so tests, docs and dispatch share one source.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

import python_setup_lint.runner.output as _output_module
from python_setup_lint.runner import STRATEGIES, TOOLS, RunnerConfig, run_lint
from python_setup_lint.runner._config import _default_config_paths
from python_setup_lint.runner.cmd_build import _config_flag_for
from python_setup_lint.testing import FakeRunCmd, fake_run_cmd_factory
from tests.runner._factories import canned_results_all_tools, runner_registry_constant

pytestmark = pytest.mark.no_external_api

_CONFIG = RunnerConfig(cwd=Path.cwd())
_GOLDEN_COUNTS = Path(__file__).resolve().parent.parent / "data" / "golden" / "minimal_sample_project_tool_counts.json"

_EXPECTED_TOOL_NAMES = frozenset(
    {
        "tach check",
        "ruff format",
        "ruff check",
        "rumdl check",
        "mypy",
        "yamllint",
        "ty check",
        "mypy.stubtest",
        "pyright check",
        "pyright verify types",
        "pylint",
        "pylint-pyi",
        "pylint tests",
        "detect-secrets",
    }
)
_FORMATTER_ONLY = frozenset({"ruff format"})
_RECORDLESS_TOOLS = frozenset({"tach check", "mypy.stubtest", "pyright verify types", "detect-secrets", "ruff format"})
_REGISTRY_CONSTANT_NAMES = (
    "EXPECTED_TOOL_NAMES",
    "FORMATTER_ONLY",
    "STATISTICS_PARSER_TOOLS",
    "RECORD_PARSER_TOOLS",
    "RECORDLESS_TOOLS",
)


class TestRuffFormatStrategy:
    """``ruff format`` is check-only on normal passes and mutates only in fix phase 1a."""

    def test_ruff_format_build_command_given_normal_pass_then_check_mode(self) -> None:
        cmd = STRATEGIES["ruff format"].build_command(config=_CONFIG)
        assert cmd[:3] == ["ruff", "format", "--check"], f"normal pass must run check mode, got {cmd!r}"
        assert "--config" in cmd, f"normal pass must pin the shipped ruff config, got {cmd!r}"
        config_index = cmd.index("--config")
        config_path = Path(cmd[config_index + 1])
        assert config_path.is_file(), f"resolved ruff config must exist: {config_path}"
        assert config_path.name == "ruff.toml"

    def test_ruff_format_build_format_command_given_fix_pass_then_mutating_mode(self) -> None:
        build_format_command = getattr(STRATEGIES["ruff format"], "build_format_command", None)
        assert callable(build_format_command), "ruff format strategy must expose build_format_command"
        cmd: list[str] = cast("Callable[..., list[str]]", build_format_command)(config=_CONFIG)
        assert cmd[:2] == ["ruff", "format"]
        assert "--check" not in cmd, f"fix phase must mutate, got {cmd!r}"
        assert "--config" in cmd, f"fix phase must pin the shipped ruff config, got {cmd!r}"
        config_index = cmd.index("--config")
        assert Path(cmd[config_index + 1]).is_file()


class TestRuffFormatConfig:
    """``ruff format`` participates in shipped-config discovery and flag mapping."""

    def test_default_config_paths_given_ruff_format_then_ruff_toml(self) -> None:
        paths = _default_config_paths(Path.cwd())
        assert "ruff format" in paths, f"shipped config discovery missing ruff format: {sorted(paths)}"
        assert paths["ruff format"].name == "ruff.toml"

    def test_config_flag_for_ruff_format_then_config_flag(self, tmp_path: Path) -> None:
        ruff_toml = tmp_path / "ruff.toml"
        ruff_toml.write_text("", encoding="utf-8")
        assert _config_flag_for("ruff format", ruff_toml) == ["--config", str(ruff_toml)]


class TestRegistryConstants:
    """Built-in registry constants are exported from the runner package."""

    def test_expected_tool_names_given_exported_then_matches_builtins(self) -> None:
        names = runner_registry_constant("EXPECTED_TOOL_NAMES")
        assert names == _EXPECTED_TOOL_NAMES
        assert names == {t.name for t in TOOLS}
        assert len(names) == 14

    def test_formatter_only_and_statistics_parser_tools_partition_all_tools(self) -> None:
        names = runner_registry_constant("EXPECTED_TOOL_NAMES")
        formatter_only = runner_registry_constant("FORMATTER_ONLY")
        statistics_tools = runner_registry_constant("STATISTICS_PARSER_TOOLS")
        assert formatter_only == _FORMATTER_ONLY
        assert len(statistics_tools) == 13
        assert statistics_tools == names - formatter_only

    def test_record_parser_and_recordless_tools_partition_all_tools(self) -> None:
        names = runner_registry_constant("EXPECTED_TOOL_NAMES")
        record_tools = runner_registry_constant("RECORD_PARSER_TOOLS")
        recordless = runner_registry_constant("RECORDLESS_TOOLS")
        assert len(record_tools) == 9
        assert recordless == _RECORDLESS_TOOLS
        assert record_tools == names - recordless

    def test_registry_constants_then_match_parser_tables(self) -> None:
        from python_setup_lint.runner.parsers import _RECORD_PARSERS, _STATISTICS_PARSERS

        assert runner_registry_constant("STATISTICS_PARSER_TOOLS") == frozenset(_STATISTICS_PARSERS)
        assert runner_registry_constant("RECORD_PARSER_TOOLS") == frozenset(_RECORD_PARSERS)

    def test_registry_constants_given_runner_then_alias_dispatch_objects(self) -> None:
        import python_setup_lint.runner as runner_pkg
        from python_setup_lint.runner import dispatch

        for name in _REGISTRY_CONSTANT_NAMES:
            value = getattr(runner_pkg, name, None)
            assert value is not None, f"python_setup_lint.runner must re-export {name}"
            assert getattr(dispatch, name, None) is value, f"{name} must be owned by dispatch and re-exported unchanged"


def _run_with_fake(monkeypatch: pytest.MonkeyPatch, *, fix: bool = False) -> FakeRunCmd:
    """Run ``run_lint`` with a dict-mode fake and return the call recorder."""
    fake = fake_run_cmd_factory(canned_results_all_tools())
    monkeypatch.setattr(_output_module, "_run_cmd", fake)
    config = RunnerConfig(cwd=Path.cwd(), package_name="python_setup_lint")
    rc = run_lint(config=config, path="src/python_setup_lint/runner.py", fix=fix)
    assert isinstance(rc, int)
    return fake


class TestPipelineModes:
    """Only ``--fix`` may mutate files; normal passes are check-only."""

    def test_run_lint_without_fix_runs_ruff_format_check_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _run_with_fake(monkeypatch)
        format_calls = [call.cmd for call in fake.calls if call.label == "ruff format"]
        assert len(format_calls) == 1, f"normal pass must run ruff format exactly once, got {format_calls!r}"
        assert "--check" in format_calls[0], f"normal pass must not mutate, got {format_calls[0]!r}"
        assert "--config" in format_calls[0], f"normal pass must use the shipped config, got {format_calls[0]!r}"

    def test_run_lint_with_fix_formats_first_then_checks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _run_with_fake(monkeypatch, fix=True)
        format_calls = [call.cmd for call in fake.calls if call.label == "ruff format"]
        assert len(format_calls) == 2, f"fix phase + lint pass must each run ruff format, got {format_calls!r}"
        mutate_cmd, check_cmd = format_calls
        assert "--check" not in mutate_cmd, f"phase 1a must mutate, got {mutate_cmd!r}"
        assert "--check" in check_cmd, f"lint pass must check, got {check_cmd!r}"
        assert "--config" in mutate_cmd and "--config" in check_cmd


class TestGoldenToolCounts:
    """Committed golden counts stay in lockstep with the 14-tool registry."""

    def test_tool_counts_file_given_registry_then_14_keys_and_ruff_format_zero(self) -> None:
        counts: dict[str, int] = json.loads(_GOLDEN_COUNTS.read_text(encoding="utf-8"))
        assert set(counts) == {t.name for t in TOOLS}
        assert counts["ruff format"] == 0
