"""Surface-unit tests for T11 v1 extra-tools: parse + validation (R4) +
merge contract + GenericLintTool.build_command. Pure unit tests on
synthetic ``tmp_path`` TOML — NO subprocess, NO real shell-out.

Reason strings LOCKED per DESIGN-8 D6 — production code is source-of-truth.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

import python_setup_lint.runner as _runner_module
from python_setup_lint.runner import (
    LINT_TOOLS,
    PARSE_STRATEGIES,
    STRATEGIES,
    TOOLS_BY_NAME,
    ExtraToolsConfigError,
    RunnerConfig,
    ToolSpec,
    ViolationCount,
    _aggregate_statistics,
    _ExtraToolRegistration,
    _load_extra_tools,
    _register_extra_tools,
    _reset_extra_tools_cache,
    register_lint_tool,
    run_lint,
)
from python_setup_lint.testing import fake_run_cmd_factory, make_lint_result
from tests.runner._factories import (
    DOWNSTREAM_CASES,
    EMPTY_LOADER_CASES,
    EXTRA_OBSERV_BLOCK,
    EXTRA_OBSERV_NAME,
    EXTRA_OBSERV_STDOUT,
    R4_EXACT_REASON_CASES,
    R4_FLAG_WRONG_TYPE_CASES,
    REGEX_BAD_GROUP_CASES,
    VALID_EXTRA_BLOCK,
    extra_block,
    write_pyproject,
)


@pytest.fixture(autouse=True)
def _isolate_registries() -> None:
    """Snapshot+restore LINT_TOOLS/STRATEGIES + extras cache per test."""
    baseline = list(LINT_TOOLS)
    baseline_strategies = dict(STRATEGIES)
    _reset_extra_tools_cache()
    yield
    LINT_TOOLS[:] = baseline
    STRATEGIES.clear()
    STRATEGIES.update(baseline_strategies)
    _reset_extra_tools_cache()


# ── Happy paths ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "case,body", EMPTY_LOADER_CASES, ids=[c for c, _ in EMPTY_LOADER_CASES]
)
def test_load_extras_returns_empty(tmp_path, case, body) -> None:
    """No pyproject / no section / empty array → ``_load_extra_tools`` returns ``[]``."""
    if body is not None:
        write_pyproject(tmp_path, body)
    assert _load_extra_tools(tmp_path) == []


def test_load_extras_valid_entry_returns_spec(tmp_path) -> None:
    """Full dogfood block → one registration with right spec + parser."""
    write_pyproject(tmp_path, extra_block(VALID_EXTRA_BLOCK))
    [reg] = _load_extra_tools(tmp_path)
    assert reg.spec.name == "grep-noqa-scan"
    assert reg.spec.supports_path is True
    assert reg.spec.default_paths == ["src/", "tests/"]
    assert reg.spec.command == [
        "grep",
        "-rnE",
        "--exclude-dir=__pycache__",
        "--include=*.py",
        "noqa: ",
    ]
    assert reg.config_flag is None
    assert reg.statistics_flag is None
    out = reg.parser("src/x.py:5:rule=A # noqa: A\nfoo.py:7: # noqa: B\n", "")
    assert dict(out) == {"A": 1, "B": 1}


# ── R4 failure table: per-shape ExtraToolsConfigError ─────────────


def _expect_error(tmp_path, body, *, reason_starts=None, reason_eq=None):  # type: ignore[misc]
    """Write *body*, call ``_load_extra_tools``, assert ExtraToolsConfigError; return err."""
    pyproject = write_pyproject(tmp_path, body)
    with pytest.raises(ExtraToolsConfigError) as exc_info:
        _load_extra_tools(tmp_path)
    err = exc_info.value
    assert err.location == str(pyproject)
    if reason_eq is not None:
        assert err.reason == reason_eq
    if reason_starts is not None:
        assert err.reason.startswith(reason_starts)
    return err


@pytest.mark.parametrize("body,reason_want,want_kind", R4_EXACT_REASON_CASES)
def test_validate_r4_reason_matches(tmp_path, body, reason_want, want_kind) -> None:
    """One row per R4 malformation — asserts locked reason (exact OR prefix)."""
    _expect_error(  # type: ignore[no-untyped-call]
        tmp_path,
        body,
        reason_eq=reason_want if want_kind == "exact" else None,
        reason_starts=reason_want if want_kind == "starts_with" else None,
    )


@pytest.mark.parametrize("body_fragment,reason_want", R4_FLAG_WRONG_TYPE_CASES)
def test_validate_r4_flag_wrong_type(tmp_path, body_fragment, reason_want) -> None:
    """One row per wrong-type flag field — name + command are valid; the flag varies."""
    _expect_error(  # type: ignore[no-untyped-call]
        tmp_path,
        extra_block(f'name = "x"\ncommand = ["x"]\n{body_fragment}'),
        reason_eq=reason_want,
    )


@pytest.mark.parametrize("regex", REGEX_BAD_GROUP_CASES)
def test_validate_regex_count_invalid_raises(tmp_path, regex) -> None:
    """Zero groups / two groups / unparseable regex → locked R4 reason prefix."""
    _expect_error(  # type: ignore[no-untyped-call]
        tmp_path,
        extra_block(
            f'name = "x"\ncommand = ["x"]\nparse_strategy = "regex_count"\nparse_regex = "{regex}"\n'
        ),
        reason_starts="regex missing or != 1 capture group",
    )


def test_validate_config_flag_str_wraps_to_single_element(tmp_path) -> None:
    """A string ``config_flag`` is accepted (wrapped to ``[value]``); no error."""
    write_pyproject(
        tmp_path, extra_block('name = "x"\ncommand = ["x"]\nconfig_flag = "--config"\n')
    )
    [reg] = _load_extra_tools(tmp_path)
    assert reg.config_flag == ["--config"]


def test_parse_strategies_includes_all_keys() -> None:
    """``PARSE_STRATEGIES`` includes T11 generic + ``none`` sentinel + 11 built-ins."""
    assert {"regex_count", "raw_lines", "none"} <= set(PARSE_STRATEGIES)
    assert {
        "ruff_statistics",
        "rumdl_statistics",
        "pylint_json2",
        "pyright_outputjson",
        "pyright_verify_types",
        "mypy_stderr",
        "ty_concise",
        "tach_json",
        "yamllint_parsable",
        "stubtest_stderr",
        "detect_secrets_json",
    } <= set(PARSE_STRATEGIES)


def test_load_extras_pyproject_unreadable_raises(tmp_path) -> None:
    """Malformed TOML → ExtraToolsConfigError with locked prefix + file location."""
    pyproject = write_pyproject(tmp_path, "bad = = syntax # not toml")
    with pytest.raises(ExtraToolsConfigError) as exc_info:
        _load_extra_tools(tmp_path)
    assert exc_info.value.location == str(pyproject)
    assert exc_info.value.reason.startswith("pyproject unreadable:")


@pytest.mark.parametrize(
    "body,reason",
    [
        (
            '[tool.python-setup-lint]\nextra-tools = "not-a-list"\n',
            "wrong type: extra-tools must be a list of tables",
        ),
        (
            '[tool.python-setup-lint]\nextra-tools = ["scalar"]\n',
            "wrong type: extra-tools entry must be a table",
        ),
    ],
    ids=["not_a_list", "entry_not_a_table"],
)
def test_load_extras_array_shape_raises(tmp_path, body, reason) -> None:
    """``extra-tools`` not a list OR an entry that's not a table → wrong-type reason."""
    _expect_error(tmp_path, body, reason_eq=reason)  # type: ignore[no-untyped-call]


# ── ExtraToolsConfigError public attribute contract ────────────────


def test_extra_tools_config_error_attributes_and_chain() -> None:
    """Constructor stores ``location``+``reason``, formats ``str(err)``, preserves cause via ``raise from``."""
    err = ExtraToolsConfigError(location="x", reason="y")
    assert err.location == "x" and err.reason == "y"
    assert str(err) == "[x] y"
    assert isinstance(err, Exception) and not isinstance(err, SystemExit)
    with pytest.raises(ExtraToolsConfigError) as exc_info:
        try:
            raise ValueError("inner")
        except ValueError as inner:
            raise ExtraToolsConfigError("loc", "outer-reason") from inner
    assert exc_info.value.location == "loc" and exc_info.value.reason == "outer-reason"
    assert isinstance(exc_info.value.__cause__, ValueError)


# MERGE category — _register_extra_tools contract

_X1 = _ExtraToolRegistration(
    spec=ToolSpec(name="x1", command=["x1"]),
    statistics_flag=None,
    parser=None,
    config_flag=None,
)
_X2 = _ExtraToolRegistration(
    spec=ToolSpec(name="x2", command=["x2"]),
    statistics_flag=None,
    parser=None,
    config_flag=None,
)


class TestExtraToolsMerge:
    """``_register_extra_tools`` merge contract: additive, idempotent, collision-safe."""

    def test_grows_lint_tools_by_n(self) -> None:
        baseline_len = len(LINT_TOOLS)
        _register_extra_tools([_X1, _X2])
        assert len(LINT_TOOLS) == baseline_len + 2

    def test_idempotent_on_same_names(self) -> None:
        baseline_len = len(LINT_TOOLS)
        _register_extra_tools([_X1])
        _register_extra_tools([_X1])  # idempotent re-call
        assert len(LINT_TOOLS) == baseline_len + 1
        assert STRATEGIES["x1"] is not None

    def test_tools_by_name_includes_extras_and_builtins(self) -> None:
        _register_extra_tools([_X1, _X2])
        names = {t.name for t in LINT_TOOLS}
        assert {"x1", "x2"} <= names
        assert set(TOOLS_BY_NAME) <= names  # all 11 built-ins remain post-merge

    def test_rejects_builtin_name_collision(self) -> None:
        collision = _ExtraToolRegistration(
            spec=ToolSpec(name="ruff check", command=["ruff", "check"]),
            statistics_flag=None,
            parser=None,
            config_flag=None,
        )
        with pytest.raises(ExtraToolsConfigError) as exc_info:
            _register_extra_tools([collision])
        assert exc_info.value.reason == "duplicate vs built-in: ruff check"
        assert exc_info.value.location == "<runtime>"

    def test_no_op_on_empty_list(self) -> None:
        baseline_len = len(LINT_TOOLS)
        _register_extra_tools([])
        assert len(LINT_TOOLS) == baseline_len


# BUILD_COMMAND category — GenericLintTool.build_command (no subprocess).


def _register_extra(
    name: str = "extra1",
    *,
    command: list[str] | None = None,
    supports_fix: bool = False,
    supports_path: bool = True,
    supports_exclude: bool = False,
    default_paths: list[str] | None = None,
    config_flag: list[str] | None = None,
) -> None:
    """Register a fresh extra via register_lint_tool (clean baseline per test)."""
    _reset_extra_tools_cache()
    register_lint_tool(
        ToolSpec(
            name=name,
            command=command or ["mytool"],
            supports_fix=supports_fix,
            supports_path=supports_path,
            supports_exclude=supports_exclude,
            default_paths=default_paths or [],
        ),
        config_flag=config_flag,
    )


def _ctx(cwd: Path, *, config_paths: dict[str, Path] | None = None) -> RunnerConfig:
    """Build a minimal RunnerConfig (other fields irrelevant to build_command)."""
    return RunnerConfig(cwd=cwd, config_paths=config_paths or {})


class TestExtraBuildCommand:
    """``GenericLintTool.build_command`` synthesis from declarative fields."""

    def test_build_command_with_config_flag(self, tmp_path: Path) -> None:
        _register_extra("extra1", config_flag=["--config"], default_paths=["src/"])
        cfg = tmp_path / "cfg.toml"
        cfg.write_text("x = 1\n")
        cmd = STRATEGIES["extra1"].build_command(
            config=_ctx(tmp_path, config_paths={"extra1": cfg})
        )
        assert cmd[:3] == ["mytool", "--config", str(cfg)]
        assert cmd[3:] == ["src/"]

    def test_build_command_appends_fix_flag(self, tmp_path: Path) -> None:
        _register_extra("extra1", supports_fix=True)
        ctx = _ctx(tmp_path)
        assert STRATEGIES["extra1"].build_command(config=ctx, fix=True) == [
            "mytool",
            "--fix",
        ]
        assert STRATEGIES["extra1"].build_command(config=ctx) == [
            "mytool"
        ]  # fix=False: no flag

    def test_build_command_appends_exclude_flag(self, tmp_path: Path) -> None:
        _register_extra("extra1", supports_exclude=True, supports_path=False)
        assert STRATEGIES["extra1"].build_command(
            config=_ctx(tmp_path), exclude="bad.py"
        ) == ["mytool", "--exclude", "bad.py"]

    def test_build_command_expands_glob_in_default_paths(self, tmp_path: Path) -> None:
        (tmp_path / "data").mkdir()
        for n in ("file1.txt", "file2.txt"):
            (tmp_path / "data" / n).write_text("a\n")
        _register_extra("extra1", supports_path=True, default_paths=["data/*.txt"])
        cmd = STRATEGIES["extra1"].build_command(config=_ctx(tmp_path))
        assert cmd[0] == "mytool"
        assert cmd[1:] == sorted(
            ["data/file1.txt", "data/file2.txt"]
        )  # sorted relative paths

    @pytest.mark.parametrize(
        "config_flag,expected",
        [
            (None, ["mytool", "src/"]),  # no_flag → flag dropped
            (["--config"], ["mytool", "src/"]),  # flag set but no path → dropped
        ],
        ids=["no_config_flag", "config_flag_with_no_path"],
    )
    def test_build_command_config_flag_boundaries(
        self,
        tmp_path: Path,
        config_flag,
        expected,
    ) -> None:
        """config_flag absent OR config_paths[extra] absent → no flag in the command."""
        _register_extra("extra1", config_flag=config_flag, default_paths=["src/"])
        cmd = STRATEGIES["extra1"].build_command(config=_ctx(tmp_path, config_paths={}))
        assert "--config" not in cmd
        assert cmd == expected

    def test_parse_strategy_none_produces_empty_parse_statistics(self) -> None:
        """GenericLintTool with no parser → ``parse_statistics`` returns ``[]``."""
        _register_extra("extra1")
        assert STRATEGIES["extra1"].parse_statistics("noise\nwarn!\n", "") == []


# ── DOWNSTREAM-INTEGRATION ───────────────────────────────────────
# End-to-end fake-subprocess pipeline for extras (NO real subprocess).
# Covers loader → validator → registration → strategy dispatch → fake
# subprocess → parse → aggregate. ``--statistics --format json`` output
# observed via capsys (per-tool banners suppressed under statistics=True).


class TestRunLintExtraDownstreamIntegration:
    """End-to-end fake-subprocess integration of the extras pipeline."""

    @pytest.mark.parametrize(
        "block,extra_name,extra_cmd,extra_stdout,expected_counts",
        DOWNSTREAM_CASES,
    )
    def test_extra_downstream_pipeline(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        block: str,
        extra_name: str,
        extra_cmd: list[str],
        extra_stdout: str,
        expected_counts: list[tuple[str, str, int]],
    ) -> None:
        """(a) extra dispatched with its spec command; (b) JSON output has expected triples;
        (c) direct re-aggregation reproduces the same counts/skip path."""
        write_pyproject(
            tmp_path,
            f"[tool.python-setup-lint]\n[[tool.python-setup-lint.extra-tools]]\n{block}",
        )
        fake = fake_run_cmd_factory(
            {extra_name: make_lint_result(tool_name=extra_name, stdout=extra_stdout)}
        )
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)

        rc = run_lint(
            config=RunnerConfig(cwd=tmp_path),
            no_fail_fast=True,
            statistics=True,
            statistics_format="json",
        )
        assert isinstance(rc, int), f"run_lint must return int; got {type(rc)}"

        # (a) extra's command reached the fake subprocess verbatim.
        extra_call = next(c for c in fake.calls if c.label == extra_name)
        assert extra_call.cmd == extra_cmd

        # (b) JSON output is the entire stdout under statistics=True.
        data = json.loads(capsys.readouterr().out.strip())
        by_key = {(e["tool"], e["rule"]): e["count"] for e in data}
        if expected_counts:
            for tool, rule, count in expected_counts:
                assert by_key.get((tool, rule)) == count, (
                    f"{tool}/{rule} → got {by_key.get((tool, rule))}. Full: {data}"
                )
        else:  # parse_strategy="none" → the extra's tool name must NOT appear
            leaked = [e for e in data if e.get("tool") == extra_name]
            assert leaked == [], (
                f"parse_strategy=none extra must not contribute rows: {leaked}. Full: {data}"
            )

        # (c) Direct re-aggregation reproduces the expected counts/skip.
        direct = _aggregate_statistics(
            [make_lint_result(tool_name=extra_name, stdout=extra_stdout)]
        )
        if expected_counts:
            for tool, rule, count in expected_counts:
                assert ViolationCount(tool, rule, count) in direct, (
                    f"_aggregate_statistics must emit {tool}/{rule}×{count}; got {direct}"
                )
        else:
            assert all(v.tool != extra_name for v in direct)


# ── PERF-BENCHMARK ─────────────────────────────────────────────────


def _time_run_lint(cwd: Path, *, n: int = 50, clear_cache_each: bool = False) -> float:
    """Run ``run_lint`` *n* times from *cwd* and return the per-iter wall-time."""
    total = 0.0
    for _ in range(n):
        if clear_cache_each:
            _reset_extra_tools_cache()
        start = time.perf_counter()
        run_lint(config=RunnerConfig(cwd=cwd), no_fail_fast=True)
        total += time.perf_counter() - start
    return total / n


@pytest.mark.slow
def test_run_lint_with_extras_startup_overhead_within_10_percent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Warm (memoised) t(N=10)/t(N=0) < 1.10 — extras caching stays O(1)."""
    no_extras_dir = tmp_path / "no_extras"
    extras_dir = tmp_path / "extras"
    no_extras_dir.mkdir()
    extras_dir.mkdir()

    (no_extras_dir / "pyproject.toml").write_text("[tool.python-setup-lint]\n")
    lines = ["[tool.python-setup-lint]"]
    for i in range(10):
        lines.append("[[tool.python-setup-lint.extra-tools]]")
        lines.append(f'name = "extra{i}"')
        lines.append(f'command = ["extra{i}"]')
        lines.append('parse_strategy = "none"')
    (extras_dir / "pyproject.toml").write_text("\n".join(lines) + "\n")

    monkeypatch.setattr(_runner_module, "_run_cmd", fake_run_cmd_factory({}))

    t_0_cold = _time_run_lint(no_extras_dir, clear_cache_each=True)
    t_10_cold = _time_run_lint(extras_dir, clear_cache_each=True)
    _reset_extra_tools_cache()
    run_lint(config=RunnerConfig(cwd=no_extras_dir), no_fail_fast=True)
    t_0_warm = _time_run_lint(no_extras_dir)
    _reset_extra_tools_cache()
    run_lint(config=RunnerConfig(cwd=extras_dir), no_fail_fast=True)
    t_10_warm = _time_run_lint(extras_dir)

    warm_ratio = t_10_warm / t_0_warm
    print(
        f"\n[bench] cold t_0={t_0_cold:.6f}s t_10={t_10_cold:.6f}s ratio={t_10_cold / t_0_cold:.4f} | "
        f"warm t_0={t_0_warm:.6f}s t_10={t_10_warm:.6f}s ratio={warm_ratio:.4f}"
    )
    assert warm_ratio < 1.10, (
        f"warm t(N=10)/t(N=0) = {warm_ratio:.4f} >= 1.10 — memoised extras path is non-linear "
        f"(t_0_warm={t_0_warm:.6f}s, t_10_warm={t_10_warm:.6f}s)"
    )


# ── OBSERVABILITY ─────────────────────────────────────────────────


class TestExtraStatisticsObservability:
    """Stats output surfaces for extras — JSON + table format + ``none`` skip."""

    @staticmethod
    def _install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Write the ``regextool`` extra pyproject + monkeypatch fake ``_run_cmd``."""
        write_pyproject(
            tmp_path,
            f"[tool.python-setup-lint]\n[[tool.python-setup-lint.extra-tools]]\n{EXTRA_OBSERV_BLOCK}",
        )
        fake = fake_run_cmd_factory(
            {
                EXTRA_OBSERV_NAME: make_lint_result(
                    tool_name=EXTRA_OBSERV_NAME,
                    exit_code=0,
                    stdout=EXTRA_OBSERV_STDOUT,
                ),
            }
        )
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)

    @pytest.mark.parametrize("fmt", ["json", "table"])
    def test_extra_rule_counts_surface_in_statistics_output(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        fmt: str,
    ) -> None:
        """JSON + table output both surface the extra's ``{tool, rule, count}`` triples."""
        self._install(tmp_path, monkeypatch)
        rc = run_lint(
            config=RunnerConfig(cwd=tmp_path),
            no_fail_fast=True,
            statistics=True,
            statistics_format=fmt,
        )
        assert isinstance(rc, int)
        out = capsys.readouterr().out.strip()
        if fmt == "json":
            by_key = {(e["tool"], e["rule"]): e["count"] for e in json.loads(out)}
            assert by_key[("regextool", "RC1")] == 2, (
                f"RC1 wrong: {by_key}. Full: {out}"
            )
            assert by_key.get(("regextool", "RC2")) == 1, (
                f"RC2 wrong: {by_key}. Full: {out}"
            )
        else:
            assert "VIOLATION STATISTICS" in out
            for token in ("regextool", "RC1", "RC2", "1", "2"):
                assert token in out, f"expected {token!r} in table output\n{out}"


# ``parse_strategy="none"`` observability skip is exercised by
# ``test_extra_downstream_pipeline[parse_strategy_none_skips_aggregate]``.
