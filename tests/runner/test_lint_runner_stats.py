# pylint: disable=too-many-positional-arguments  # parametrized tests with 6 args; pylint default is 5
"""Unit tests for statistics/grouping/sort/fail-fast in ``python_setup_lint.runner``.

Split from ``test_lint_runner.py`` to stay under the 500-line pylint C0302 limit.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from python_setup_lint.runner import (
    LINT_TOOLS,
    PARSE_STRATEGIES,
    STRATEGIES,
    TOOLS,
    ExtraToolsConfigError,
    RunnerConfig,
    ToolSpec,
    ViolationCount,
    main,
    register_lint_tool,
    run_lint,
)
from python_setup_lint.runner._config import _SUPPORTED_CONFIG_KEYS
from python_setup_lint.runner.cmd_build import _build_command, _build_statistics_flags
from python_setup_lint.runner.output import _print_statistics_grouped, _sort_counts
from python_setup_lint.runner.parsers import _STATISTICS_PARSERS
from tests.runner._factories import install_fake_runner, lint_config, write_pyproject
from tests.runner._factories_extras import (
    CLEAN_EXTRAS_PYPROJECT_BODY,
    GROUPED_OUTPUT_CASES,
    GROUPED_SORT_BY_RULE_COUNTS,
    MALFORMATION_CASES,
    SORT_BY_RULE_COUNTS,
    SORT_DEFAULT_COUNTS,
)
from tests.runner._factories_tables import (
    MAIN_GROUP_SORT_CASES,
    PARSER_STATISTICS_CASES,
    STATISTICS_FLAG_CASES,
)

pytestmark = pytest.mark.no_external_api

_CONFIG = RunnerConfig(cwd=Path.cwd())


@pytest.mark.parametrize(("tool_name", "expected"), STATISTICS_FLAG_CASES)
def test_build_statistics_flags(tool_name: str, expected: list[str]) -> None:
    spec = ToolSpec(tool_name, ["tool"])
    assert _build_statistics_flags(spec) == expected, f"{tool_name}: got {_build_statistics_flags(spec)!r}"


def test_statistics_flag_given_build_command_then_appended() -> None:
    cmd = _build_command(ToolSpec("ruff check", ["ruff", "check"]), config=_CONFIG)
    cmd.extend(_build_statistics_flags(ToolSpec("ruff check", ["ruff", "check"])))
    assert "--statistics" in cmd
    for name in ("mypy.stubtest", "detect-secrets", "pyright verify types"):
        assert _build_statistics_flags(ToolSpec(name, ["tool"])) == [], f"{name} should have no flags"


@pytest.mark.parametrize(("tool_name", "stdout", "stderr", "expected"), PARSER_STATISTICS_CASES)
def test_statistics_parser(tool_name: str, stdout: str, stderr: str, expected: list[tuple[str, int]]) -> None:
    parser = _STATISTICS_PARSERS[tool_name]
    result = parser(stdout, stderr)
    assert dict(result) == dict(expected), f"{tool_name} parser returned {dict(result)!r}, expected {dict(expected)!r}"


def test_statistics_parsers_given_all_tools_then_covered() -> None:
    assert {t.name for t in TOOLS} <= set(_STATISTICS_PARSERS)


def test_parse_strategies_given_stats_then_includes_all_keys() -> None:
    assert {"regex_count", "raw_lines", "none"} <= set(PARSE_STRATEGIES)
    assert {
        "ruff_statistics", "rumdl_statistics", "pylint_json2", "pyright_outputjson",
        "pyright_verify_types", "mypy_stderr", "ty_concise", "tach_json",
        "yamllint_parsable", "stubtest_stderr", "detect_secrets_json",
    } <= set(PARSE_STRATEGIES)


class TestSortCounts:
    @pytest.mark.parametrize(("counts", "sort_by_rule", "expected_rules"), [
        (SORT_DEFAULT_COUNTS, False, ["A001", "B001", "Z001"]),
        (SORT_BY_RULE_COUNTS, True, None),
    ],
    ids=["default_sort_highest_count_first", "sort_by_rule"],)
    def test_sort_counts(self: object, counts: list[Any], sort_by_rule: bool, expected_rules: list[str] | None) -> None:
        result = _sort_counts(counts, sort_by_rule=sort_by_rule)
        if expected_rules is not None:
            assert [c.rule for c in result] == expected_rules
        if sort_by_rule:
            assert result[0].rule == "A001" and result[0].tool == "tool_a" and result[0].count == 10
            assert result[2].rule == "Z001"

    def test_sort_counts_given_empty_list_then_returns_empty(self) -> None:
        assert _sort_counts([]) == []


@pytest.mark.parametrize("args", MAIN_GROUP_SORT_CASES)
def test_main_group_and_sort_given_rule_accepted_then_works(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, args: list[str]) -> None:
    install_fake_runner(monkeypatch)
    rc = main(args, config=RunnerConfig(cwd=tmp_path, package_name="python_setup_lint"))
    assert isinstance(rc, int)


def test_run_lint_group_sort_given_rule_then_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_runner(monkeypatch)
    rc = run_lint(config=RunnerConfig(cwd=Path("/tmp"), package_name="python_setup_lint"), statistics=True, group="tool", sort_by_rule=True)
    assert isinstance(rc, int)


class TestGroupedOutput:
    @pytest.mark.parametrize(("group", "counts", "header", "markers", "tokens"), GROUPED_OUTPUT_CASES)
    def test_group_format_and_subtotals(
        self, capsys: pytest.CaptureFixture[str], group: str, counts: list[ViolationCount], header: str, markers: list[str], tokens: list[str]
    ) -> None:
        _print_statistics_grouped(counts, group=group)
        out = capsys.readouterr().out
        if markers:
            assert header in out
            for marker in markers:
                assert marker in out
        for token in tokens:
            assert token in out

    def test_grouped_output_given_sort_by_rule_then_orders_sections(self, capsys: pytest.CaptureFixture[str]) -> None:
        _print_statistics_grouped(GROUPED_SORT_BY_RULE_COUNTS, group="rule", sort_by_rule=True)
        out = capsys.readouterr().out
        assert out.index("[A001]") < out.index("[Z001]")


class TestT8FailFastConfig:
    @pytest.mark.parametrize(("body", "reason_want", "exact_match"), MALFORMATION_CASES)
    def test_malformed_pyproject_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_runner_registries: None, body: str, reason_want: str, exact_match: bool
    ) -> None:
        pyproject = write_pyproject(tmp_path, body)
        install_fake_runner(monkeypatch)
        with pytest.raises(ExtraToolsConfigError) as exc_info:
            run_lint(config=lint_config(tmp_path))
        err = exc_info.value
        assert err.location == str(pyproject), f"location: got {err.location!r}, want {str(pyproject)!r}"
        if exact_match:
            assert err.reason == reason_want, f"reason: got {err.reason!r}, want {reason_want!r}"
        else:
            assert reason_want in err.reason, f"reason: got {err.reason!r}, want substring {reason_want!r}"

    def test_t8_fail_fast_given_unknown_tool_id_then_raises(self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, isolated_runner_registries: None) -> None:
        install_fake_runner(monkeypatch)
        with pytest.raises(SystemExit) as exc_info:
            main(["--config", "bogus=/some/path.toml"], config=lint_config(tmp_path))
        assert exc_info.value.code == 2
        err = capsys.readouterr().err
        assert "bogus" in err and "ruff" in err and "pyright" in err
        assert "bogus" not in _SUPPORTED_CONFIG_KEYS
        assert {"ruff", "mypy", "pylint", "pyright", "rumdl", "ty"} <= _SUPPORTED_CONFIG_KEYS

    def test_t8_fail_fast_given_bad_tools_list_then_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_runner_registries: None) -> None:
        install_fake_runner(monkeypatch)
        config = RunnerConfig(cwd=tmp_path, tools_override=["ruff check", "bogus-tool-name"])
        with pytest.raises(ExtraToolsConfigError) as exc_info:
            run_lint(config=config)
        assert exc_info.value.reason.startswith("unknown tool name: 'bogus-tool-name'")
        assert "ruff check" in exc_info.value.reason
        assert exc_info.value.location == "<RunnerConfig.tools_override>"

    def test_t8_fail_fast_given_clean_pyproject_then_runs_clean(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_runner_registries: None) -> None:
        write_pyproject(tmp_path, CLEAN_EXTRAS_PYPROJECT_BODY)
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "__init__.py").write_text("", encoding="utf-8")
        install_fake_runner(monkeypatch)
        config = lint_config(tmp_path, package_name="t8_clean", tools_override=["ruff check", "t8-grep-noqa"])
        assert isinstance(run_lint(config=config), int)


# ── Strategy registry ──────────────────────────────────────────────


class TestLintToolRegistry:
    """STRATEGIES/LINT_TOOLS mirror the 13 built-ins AND strategies are LintTool instances."""

    @pytest.mark.parametrize(
        "registry",
        [STRATEGIES, {t.name: t for t in LINT_TOOLS}],
        ids=["STRATEGIES", "LINT_TOOLS"],
    )
    def test_registry_mirrors_builtins(self, registry: dict[str, Any], isolated_runner_registries: None) -> None:
        assert set(registry) == {t.name for t in TOOLS} and len(registry) == len(TOOLS)

    def test_strategies_are_lint_tool_instances_with_matching_names(self) -> None:
        from python_setup_lint.runner.dispatch import LintTool

        for name, strategy in STRATEGIES.items():
            assert isinstance(strategy, LintTool), (
                f"Strategy {strategy!r} is not a LintTool"
            )
            assert strategy.name == name and strategy.spec.name == name


class TestRegisterLintTool:
    """``register_lint_tool`` semantics: append-extra, idempotent, builtin-protected."""

    def test_register_appends_extra(self, isolated_runner_registries: None) -> None:
        from python_setup_lint.runner.dispatch import GenericLintTool

        extra = ToolSpec("t4-extra-test-tool", ["t4extra", "check"], supports_path=True)
        register_lint_tool(extra, statistics_flag=[], parser=None, config_flag=None)
        assert any(t.name == "t4-extra-test-tool" for t in LINT_TOOLS)
        assert isinstance(STRATEGIES.get("t4-extra-test-tool"), GenericLintTool)

    def test_register_lint_tool_given_same_name_then_idempotent(
        self, isolated_runner_registries: None
    ) -> None:
        register_lint_tool(ToolSpec("t4-idempotent-tool", ["t4ida"]))
        count_after_first = len(LINT_TOOLS)
        register_lint_tool(
            ToolSpec("t4-idempotent-tool", ["t4idb"])
        )  # update-in-place, no growth
        assert len(LINT_TOOLS) == count_after_first
        assert next(
            t for t in LINT_TOOLS if t.name == "t4-idempotent-tool"
        ).command == ["t4idb"]

    def test_register_lint_tool_given_builtin_then_does_not_replace(
        self, isolated_runner_registries: None
    ) -> None:
        original_strategy = STRATEGIES["ruff check"]
        register_lint_tool(ToolSpec("ruff check", ["ruff", "duplicate"]))
        assert STRATEGIES["ruff check"] is original_strategy


class TestGenericLintTool:
    """``GenericLintTool`` synthesises command + statistics-flag plumbing from spec."""

    def test_build_command_composes_fix_path_exclude(self) -> None:
        from python_setup_lint.runner.dispatch import GenericLintTool

        spec = ToolSpec(
            "t4-generic-tool",
            ["t4g", "check"],
            supports_fix=True,
            supports_path=True,
            supports_exclude=True,
            default_paths=["src/"],
        )
        g = GenericLintTool(spec, statistics_flag=[], parser=None, config_flag=None)
        assert g.build_command(
            config=RunnerConfig(cwd=Path("/tmp")), _fix=True, _path=None, _exclude="tests/"
        ) == [
            "t4g",
            "check",
            "--fix",
            "src/",
            "--exclude",
            "tests/",
        ]

    @pytest.mark.parametrize(("override", "expected"), [
        (["--stat-foo"], ["--stat-foo"]),  # explicit override wins
    ],
    ids=["stats_override_wins"],)
    def test_statistics_flags_use_override(
        self, override: list[str], expected: list[str]
    ) -> None:
        from python_setup_lint.runner.dispatch import GenericLintTool

        g = GenericLintTool(
            ToolSpec("t4-stats-tool", ["t4s"]),
            statistics_flag=override,
            parser=None,
            config_flag=None,
        )
        assert g.statistics_flags() == expected

    def test_statistics_flags_fall_back_to_module_lookup(self) -> None:
        from python_setup_lint.runner.dispatch import GenericLintTool

        g = GenericLintTool(
            ToolSpec("ruff check", ["ruff", "check"]),
            statistics_flag=None,
            parser=None,
            config_flag=None,
        )
        assert g.statistics_flags() == ["--statistics"]

    def test_parse_statistics_uses_override(self) -> None:
        from python_setup_lint.runner.dispatch import GenericLintTool

        def custom_parser(stdout: str, stderr: str) -> list[tuple[str, int]]:
            return [("custom-rule", 7)]

        g = GenericLintTool(
            ToolSpec("t4-parse-tool", ["t4p"]),
            statistics_flag=None,
            parser=custom_parser,
            config_flag=None,
        )
        assert g.parse_statistics("ignored", "also-ignored") == [("custom-rule", 7)]

    def test_parse_statistics_falls_back_to_module_lookup(self) -> None:
        from python_setup_lint.runner.dispatch import GenericLintTool

        g = GenericLintTool(
            ToolSpec("ruff check", ["ruff", "check"]),
            statistics_flag=None,
            parser=None,
            config_flag=None,
        )
        out = "Count\tCode\tDescription\n------\t----\t-----------\n3\tF401\tmodule imported but unused\n"
        assert ("F401", 3) in g.parse_statistics(out, "")


class TestStrategyForFallback:
    """``_strategy_for`` default-aware fallback (unknown names → GenericLintTool)."""

    def test_returns_cached_builtin(self) -> None:
        from python_setup_lint.runner.dispatch import (
            _strategy_for,
        )

        original = STRATEGIES["ruff check"]
        assert (
            _strategy_for("ruff check", ToolSpec("ruff check", ["ruff", "check"]))
            is original
        )

    def test_unknown_name_returns_generic(self) -> None:
        from python_setup_lint.runner.dispatch import (
            GenericLintTool,
            _strategy_for,
        )

        fake_spec = ToolSpec("t4-unknown-fallback", ["t4fake"])
        got = _strategy_for("t4-unknown-fallback", fake_spec)
        assert isinstance(got, GenericLintTool) and got.spec is fake_spec

    def test_unknown_name_does_not_mutate_strategies(self) -> None:
        from python_setup_lint.runner.dispatch import (
            _strategy_for,
        )

        _strategy_for(
            "t4-no-cache-fallback", ToolSpec("t4-no-cache-fallback", ["t4nc"])
        )
        assert "t4-no-cache-fallback" not in STRATEGIES



def test_invalid_group_value_given_invalid_then_rejected() -> None:
    """argparse rejects ``--group bogus`` with a non-zero exit code."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--statistics", "--group", "bogus"])
    assert exc_info.value.code != 0

