# pylint: disable=duplicate-code  # shared test helper pattern with test_autofix_conflict_apply
"""Surface-unit tests for T11 v1 extra-tools: parse + validation (R4) +
merge contract + GenericLintTool.build_command. Pure unit tests on
synthetic ``tmp_path`` TOML — NO subprocess, NO real shell-out.

Reason strings LOCKED per DESIGN-8 D6 — production code is source-of-truth.
"""
from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from python_setup_lint.runner import (
    LINT_TOOLS,
    PARSE_STRATEGIES,
    STRATEGIES,
    TOOLS_BY_NAME,
    ExtraToolsConfigError,
    RunnerConfig,
    ToolSpec,
    register_lint_tool,
)
from python_setup_lint.runner.extra_tools import (
    _ExtraToolRegistration,
    _load_extra_tools,
    _register_extra_tools,
    _reset_extra_tools_cache,
)
from tests.runner._factories import write_pyproject
from tests.runner._factories_extras import (
    EMPTY_LOADER_CASES,
    R4_EXACT_REASON_CASES,
    R4_FLAG_WRONG_TYPE_CASES,
    REGEX_BAD_GROUP_CASES,
    VALID_EXTRA_BLOCK,
    extra_block,
)


@pytest.fixture(autouse=True)
def _isolate_registries() -> Generator[None]:
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


@pytest.mark.parametrize(("case", "body"), EMPTY_LOADER_CASES, ids=[c for c, _ in EMPTY_LOADER_CASES])
def test_load_extras_returns_empty(tmp_path: Path, case: str, body: str | None) -> None:
    """No pyproject / no section / empty array → ``_load_extra_tools`` returns ``[]``."""
    if body is not None:
        write_pyproject(tmp_path, body)
    assert _load_extra_tools(tmp_path) == []


def test_load_extras_valid_entry_returns_spec(tmp_path: Path) -> None:
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
    assert reg.parser is not None
    out = reg.parser("src/x.py:5:rule=A # noqa: A\nfoo.py:7: # noqa: B\n", "")


# ── R4 failure table: per-shape ExtraToolsConfigError ─────────────


def _expect_error(tmp_path: Path, body: str, *, reason_starts: str | None = None, reason_eq: str | None = None) -> ExtraToolsConfigError:
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


@pytest.mark.parametrize(("body", "reason_want", "want_kind"), R4_EXACT_REASON_CASES)
def test_validate_r4_reason_matches(tmp_path: Path, body: str, reason_want: str, want_kind: str) -> None:  # pylint: disable=trivial-wrapper  # test function delegates to _expect_error
    """One row per R4 malformation — asserts locked reason (exact OR prefix)."""
    _expect_error(
        tmp_path,
        body,
        reason_eq=reason_want if want_kind == "exact" else None,
        reason_starts=reason_want if want_kind == "starts_with" else None,
    )


@pytest.mark.parametrize(("body_fragment", "reason_want"), R4_FLAG_WRONG_TYPE_CASES)
def test_validate_r4_flag_wrong_type(tmp_path: Path, body_fragment: str, reason_want: str) -> None:  # pylint: disable=trivial-wrapper  # test function delegates to _expect_error
    """One row per wrong-type flag field — name + command are valid; the flag varies."""
    _expect_error(
        tmp_path,
        extra_block(f'name = "x"\ncommand = ["x"]\n{body_fragment}'),
        reason_eq=reason_want,
    )


@pytest.mark.parametrize("regex", REGEX_BAD_GROUP_CASES)
def test_validate_regex_count_invalid_raises(tmp_path: Path, regex: str) -> None:  # pylint: disable=trivial-wrapper  # test function delegates to _expect_error
    """Zero groups / two groups / unparseable regex → locked R4 reason prefix."""
    _expect_error(
        tmp_path,
        extra_block(
            f'name = "x"\ncommand = ["x"]\nparse_strategy = "regex_count"\nparse_regex = "{regex}"\n'
        ),
        reason_starts="regex missing or != 1 capture group",
    )


def test_validate_config_flag_str_wraps_to_single_element(tmp_path: Path) -> None:
    """A string ``config_flag`` is accepted (wrapped to ``[value]``); no error."""
    write_pyproject(
        tmp_path, extra_block('name = "x"\ncommand = ["x"]\nconfig_flag = "--config"\n')
    )
    [reg] = _load_extra_tools(tmp_path)
    assert reg.config_flag == ["--config"]


def test_parse_strategies_includes_all_keys() -> None:
    """``PARSE_STRATEGIES`` includes T11 generic + ``none`` sentinel + built-ins from the parser map."""
    from python_setup_lint.runner.parsers import _BUILTIN_PARSE_STRATEGY_TO_PARSER
    builtin_names = set(_BUILTIN_PARSE_STRATEGY_TO_PARSER)
    assert {"regex_count", "raw_lines", "none"} <= set(PARSE_STRATEGIES)
    assert builtin_names <= set(PARSE_STRATEGIES)


def test_load_extras_pyproject_unreadable_raises(tmp_path: Path) -> None:
    """Malformed TOML → ExtraToolsConfigError with locked prefix + file location."""
    pyproject = write_pyproject(tmp_path, "bad = = syntax # not toml")
    with pytest.raises(ExtraToolsConfigError) as exc_info:
        _load_extra_tools(tmp_path)
    assert exc_info.value.location == str(pyproject)
    assert exc_info.value.reason.startswith("pyproject unreadable:")


@pytest.mark.parametrize(("body", "reason"), [
    (
        '[tool.python-setup-lint]\nextra-tools = "not-a-list"\n',
        "wrong type: extra-tools must be a list of tables",
    ),
    (
        '[tool.python-setup-lint]\nextra-tools = ["scalar"]\n',
        "wrong type: extra-tools entry must be a table",
    ),
],
ids=["not_a_list", "entry_not_a_table"],)
def test_load_extras_array_shape_raises(tmp_path: Path, body: str, reason: str) -> None:  # pylint: disable=trivial-wrapper  # test function delegates to _expect_error
    """``extra-tools`` not a list OR an entry that's not a table → wrong-type reason."""
    _expect_error(tmp_path, body, reason_eq=reason)


# ── ExtraToolsConfigError public attribute contract ────────────────


def test_extra_tools_config_error_given_attributes_then_chains() -> None:
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

    @pytest.fixture(autouse=True)
    def _isolate(self, isolated_runner_registries: None) -> None:
        pass

    def test_extra_tools_merge_given_extra_tools_then_grows_lint_tools(self) -> None:
        baseline_len = len(LINT_TOOLS)
        _register_extra_tools([_X1, _X2])
        assert len(LINT_TOOLS) == baseline_len + 2

    def test_extra_tools_merge_given_same_names_then_idempotent(self) -> None:
        baseline_len = len(LINT_TOOLS)
        _register_extra_tools([_X1])
        _register_extra_tools([_X1])  # idempotent re-call
        assert len(LINT_TOOLS) == baseline_len + 1
        assert STRATEGIES["x1"] is not None

    def test_extra_tools_merge_given_tools_by_name_then_includes_extras(self) -> None:
        _register_extra_tools([_X1, _X2])
        names = {t.name for t in LINT_TOOLS}
        assert {"x1", "x2"} <= names
        assert set(TOOLS_BY_NAME) <= names  # all 11 built-ins remain post-merge

    def test_extra_tools_merge_given_builtin_name_collision_then_rejects(self) -> None:
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

    def test_extra_tools_merge_given_empty_list_then_no_op(self) -> None:
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


def _ctx(cwd: Path, *, config_paths: dict[str, Path] | None = None) -> RunnerConfig:  # pylint: disable=trivial-wrapper  # test helper; readability over DRY
    """Build a minimal RunnerConfig (other fields irrelevant to build_command)."""
    return RunnerConfig(cwd=cwd, config_paths=config_paths or {})


class TestExtraBuildCommand:
    """``GenericLintTool.build_command`` synthesis from declarative fields."""

    def test_extra_build_command_given_config_flag_then_appends(self, tmp_path: Path) -> None:
        _register_extra("extra1", config_flag=["--config"], default_paths=["src/"])
        cfg = tmp_path / "cfg.toml"
        cfg.write_text("x = 1\n")
        cmd = STRATEGIES["extra1"].build_command(
            config=_ctx(tmp_path, config_paths={"extra1": cfg})
        )
        assert cmd[:3] == ["mytool", "--config", str(cfg)]
        assert cmd[3:] == ["src/"]

    def test_extra_build_command_given_fix_then_appends_flag(self, tmp_path: Path) -> None:
        _register_extra("extra1", supports_fix=True)
        ctx = _ctx(tmp_path)
        assert STRATEGIES["extra1"].build_command(config=ctx, _fix=True) == [
            "mytool",
            "--fix",
        ]
        assert STRATEGIES["extra1"].build_command(config=ctx) == [
            "mytool"
        ]  # fix=False: no flag

    def test_extra_build_command_given_exclude_then_appends_flag(self, tmp_path: Path) -> None:
        _register_extra("extra1", supports_exclude=True, supports_path=False)
        assert STRATEGIES["extra1"].build_command(
            config=_ctx(tmp_path), _exclude="bad.py"
        ) == ["mytool", "--exclude", "bad.py"]

    def test_extra_build_command_given_glob_then_expands(self, tmp_path: Path) -> None:
        (tmp_path / "data").mkdir()
        for n in ("file1.txt", "file2.txt"):
            (tmp_path / "data" / n).write_text("a\n")
        _register_extra("extra1", supports_path=True, default_paths=["data/*.txt"])
        cmd = STRATEGIES["extra1"].build_command(config=_ctx(tmp_path))
        assert cmd[0] == "mytool"
        assert cmd[1:] == sorted(
            ["data/file1.txt", "data/file2.txt"]
        )  # sorted relative paths

    @pytest.mark.parametrize(("config_flag", "expected"), [
        (None, ["mytool", "src/"]),  # no_flag → flag dropped
        (["--config"], ["mytool", "src/"]),  # flag set but no path → dropped
    ],
    ids=["no_config_flag", "config_flag_with_no_path"],)
    def test_build_command_config_flag_boundaries(
        self: object,
        tmp_path: Path,
        config_flag: list[str] | None,
        expected: list[str],
    ) -> None:
        """config_flag absent OR config_paths[extra] absent → no flag in the command."""
        _register_extra("extra1", config_flag=config_flag, default_paths=["src/"])
        cmd = STRATEGIES["extra1"].build_command(config=_ctx(tmp_path, config_paths={}))
        assert "--config" not in cmd
        assert cmd == expected

    def test_extra_build_command_given_none_parse_strategy_then_empty_statistics(self) -> None:
        """GenericLintTool with no parser → ``parse_statistics`` returns ``[]``."""
        _register_extra("extra1")
        assert STRATEGIES["extra1"].parse_statistics("noise\nwarn!\n", "") == []


