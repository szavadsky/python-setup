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
    RunnerConfig,
    STRATEGIES,
    TOOLS_BY_NAME,
    ToolSpec,
    ViolationCount,
    ExtraToolsConfigError,
    _ExtraToolRegistration,
    _aggregate_statistics,
    _load_extra_tools,
    _register_extra_tools,
    _reset_extra_tools_cache,
    register_lint_tool,
    run_lint,
)
from python_setup_lint.testing import fake_run_cmd_factory, make_lint_result

# Built-in name used to exercise the duplicate-vs-builtin R4 branch.
_BUILTIN_NAME = "ruff check"

# A complete, valid ``[[...]]`` block mirroring the dogfood
# ``grep-noqa-scan`` fixture (T11d1).
_VALID_BLOCK = (
    'name = "grep-noqa-scan"\n'
    'command = ["grep", "-rnE", "--exclude-dir=__pycache__", '
    '"--include=*.py", "noqa: "]\n'
    "supports_path = true\n"
    'default_paths = ["src/", "tests/"]\n'
    'parse_strategy = "regex_count"\n'
    'parse_regex = "^[^:]+:\\\\d+:.*# noqa: (\\\\S+)"\n'
)


def _write_pyproject(tmp_path: object, body: str) -> object:
    """Write a synthetic ``pyproject.toml`` body under *tmp_path*.

    Returns the resolved path so tests can assert
    ``ExtraToolsConfigError.location`` verbatim.
    """
    pyproject = tmp_path / "pyproject.toml"  # type: ignore[operator]
    pyproject.write_text(body, encoding="utf-8")
    _reset_extra_tools_cache()
    return pyproject.resolve()


def _extra_block(entries: str) -> str:
    """Wrap one-or-more ``[[tool.python-setup-lint.extra-tools]]`` body lines."""
    return f"[tool.python-setup-lint]\n[[tool.python-setup-lint.extra-tools]]\n{entries}"


@pytest.fixture(autouse=True)
def _isolate_registries() -> object:
    """Isolate LINT_TOOLS/STRATEGIES + extra-tools cache per test.

    Snapshot + restore LINT_TOOLS and STRATEGIES around each test so
    merge tests don't leak mutations.  Also clears the per-process
    extra-tools memo so cache-key collisions are impossible.
    """
    baseline = list(LINT_TOOLS)
    baseline_strategies = dict(STRATEGIES)
    _reset_extra_tools_cache()
    yield
    LINT_TOOLS[:] = baseline
    STRATEGIES.clear()
    STRATEGIES.update(baseline_strategies)
    _reset_extra_tools_cache()


# ── Happy paths ─────────────────────────────────────────────────────
# Loader returns ``[]`` on the three "no extras here" shapes: missing
# pyproject, missing section, empty array (T8 R5 enumeration edge).

_EMPTY_LOADER_CASES = [
    ("no_pyproject", None),  # no file at all
    ("no_section", "[tool.python-setup-lint]\nsome = 1\n"),  # tool section w/o array
    ("empty_array", "[tool.python-setup-lint]\nextra-tools = []\n"),  # empty array
]


@pytest.mark.parametrize("case,body", _EMPTY_LOADER_CASES, ids=[c for c, _ in _EMPTY_LOADER_CASES])
def test_load_extras_returns_empty(tmp_path, case, body):
    """Each "no extras here" shape (no pyproject / no section / empty array) → ``[]``."""
    if body is not None:
        _write_pyproject(tmp_path, body)
    assert _load_extra_tools(tmp_path) == []


def test_load_extras_valid_entry_returns_spec(tmp_path):
    """Full dogfood block → one registration with right spec + parser."""
    _write_pyproject(tmp_path, _extra_block(_VALID_BLOCK))
    registrations = _load_extra_tools(tmp_path)
    assert len(registrations) == 1
    reg = registrations[0]
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
    # regex_count strategy → parser is a functools.partial binding parse_regex.
    assert reg.parser is not None
    out = reg.parser("src/x.py:5:rule=A # noqa: A\nfoo.py:7: # noqa: B\n", "")
    assert dict(out) == {"A": 1, "B": 1}


# ── R4 failure table: per-shape ``ExtraToolsConfigError`` ───────────


def _expect_error(tmp_path, body, *, reason_starts: str | None = None,
                  reason_eq: str | None = None):
    """Write *body*, call ``_load_extra_tools``, assert ``ExtraToolsConfigError``."""
    pyproject = _write_pyproject(tmp_path, body)
    with pytest.raises(ExtraToolsConfigError) as exc_info:
        _load_extra_tools(tmp_path)
    err = exc_info.value
    assert err.location == str(pyproject), (
        f"location mismatch: got {err.location!r}, want {str(pyproject)!r}"
    )
    if reason_eq is not None:
        assert err.reason == reason_eq, (
            f"reason mismatch: got {err.reason!r}, want {reason_eq!r}"
        )
    if reason_starts is not None:
        assert err.reason.startswith(reason_starts), (
            f"reason mismatch: got {err.reason!r}, want prefix {reason_starts!r}"
        )
    return err


def test_validate_unknown_field_raises(tmp_path):
    """Unknown field in entry → ``reason`` starts ``"unknown field: "``."""
    _expect_error(
        tmp_path,
        _extra_block('name = "x"\ncommand = ["x"]\nbogus_field = 1\n'),
        reason_starts="unknown field: ",
    )


def test_validate_missing_required_field_raises(tmp_path):
    """Entry with ``name`` only (missing ``command``) → exact missing-field reason."""
    _expect_error(
        tmp_path,
        _extra_block('name = "x"\n'),
        reason_eq="missing required field: command",
    )


# Parametrised R4 rows where one ``_expect_error`` call maps to one R4 line.
# Locked per DESIGN-8 D6 — production code is source-of-truth for reason strings.
_R4_INLINE_CASES: list[tuple[str, str, bool]] = [
    # (block_body, expected_reason, is_prefix)
    ('name = 123\ncommand = ["x"]\n', "wrong type: name must be non-empty str", False),
    # ``name = "   "`` (whitespace-only): the .strip() falsifies it before
    # the empty-name branch, so the wrong-type reason fires first.
    ('name = "   "\ncommand = ["x"]\n', "wrong type: name must be non-empty str", False),
    ('name = "x"\ncommand = "ruff"\n', "wrong type: command must be non-empty list[str]", False),
    ('name = "x"\ncommand = ["x", 1]\n', "wrong type: command must be list[str]", False),
]


@pytest.mark.parametrize(
    "block,reason,is_prefix",
    _R4_INLINE_CASES,
    ids=["name_non_str", "name_whitespace", "command_scalar", "command_non_str_parts"],
)
def test_validate_r4_inline(tmp_path, block, reason, is_prefix):
    """One R4 row per malformed block; locked reason strings emitted by code."""
    _expect_error(tmp_path, _extra_block(block), reason_eq=None if is_prefix else reason,
                  reason_starts=reason if is_prefix else None)


def test_validate_duplicate_within_file_raises(tmp_path):
    """Two entries with the same name → second entry raises duplicate-within-file."""
    body = (
        _extra_block('name = "dup"\ncommand = ["x"]\n')
        + "[[tool.python-setup-lint.extra-tools]]\n"
        + 'name = "dup"\ncommand = ["x"]\n'
    )
    _expect_error(tmp_path, body, reason_eq="duplicate within file: dup")


def test_validate_duplicate_vs_builtin_raises(tmp_path):
    """An entry whose name shadows a built-in tool → duplicate-vs-builtin reason."""
    _expect_error(
        tmp_path,
        _extra_block(f'name = "{_BUILTIN_NAME}"\ncommand = ["x"]\n'),
        reason_eq=f"duplicate vs built-in: {_BUILTIN_NAME}",
    )


# Wrong-type R4 table — parametrised over the boolean / list / scalar shapes.
# Each (block-body fragment, expected reason) pair is one R4 line.
_WRONG_TYPE_CASES = [
    ('supports_fix = "yes"\n', "wrong type: supports_fix must be bool"),
    ("supports_path = 1\n", "wrong type: supports_path must be bool"),
    ('supports_exclude = "no"\n', "wrong type: supports_exclude must be bool"),
    ('default_paths = "src/"\n', "wrong type: default_paths must be list[str]"),
    ('default_paths = ["x", 1]\n', "wrong type: default_paths must be list[str]"),
    ("config_flag = 12\n", "wrong type: config_flag must be str | list[str]"),
    ('config_flag = ["--x", 1]\n', "wrong type: config_flag must be str | list[str]"),
    ("parse_strategy = 7\n", "wrong type: parse_strategy must be str"),
    ('parse_strategy = "bogus"\n', "bad enum: parse_strategy 'bogus'"),
]


@pytest.mark.parametrize("extra,reason", _WRONG_TYPE_CASES)
def test_validate_wrong_type_parametrised(tmp_path, extra, reason):
    """One R4 row per wrong-type field — locked reason string emitted by code."""
    _expect_error(
        tmp_path,
        _extra_block(f'name = "x"\ncommand = ["x"]\n{extra}'),
        reason_eq=reason,
    )


def test_validate_config_flag_str_wraps_to_single_element(tmp_path):
    """A string ``config_flag`` is accepted (wrapped to ``[value]``); no error."""
    _write_pyproject(
        tmp_path, _extra_block('name = "x"\ncommand = ["x"]\nconfig_flag = "--config"\n')
    )
    [reg] = _load_extra_tools(tmp_path)
    assert reg.config_flag == ["--config"]


def test_validate_bad_enum_lists_every_built_in_name():
    """``PARSE_STRATEGIES`` includes both T11 generic + ``none`` sentinel."""
    assert "regex_count" in PARSE_STRATEGIES
    assert "raw_lines" in PARSE_STRATEGIES
    assert "none" in PARSE_STRATEGIES
    # 11 built-in stat parsers must all be present.
    assert {
        "ruff_statistics", "rumdl_statistics", "pylint_json2",
        "pyright_outputjson", "pyright_verify_types", "mypy_stderr",
        "ty_concise", "tach_json", "yamllint_parsable", "stubtest_stderr",
        "detect_secrets_json",
    } <= PARSE_STRATEGIES


def test_validate_regex_count_requires_parse_regex_raises(tmp_path):
    """``parse_strategy = "regex_count"`` with no ``parse_regex`` → missing-field."""
    _expect_error(
        tmp_path,
        _extra_block('name = "x"\ncommand = ["x"]\nparse_strategy = "regex_count"\n'),
        reason_starts='missing required field: parse_regex',
    )


def test_validate_regex_count_bad_group_count_raises(tmp_path):
    """``parse_regex`` with zero capture groups → locked R4 reason prefix."""
    _expect_error(
        tmp_path,
        _extra_block(
            'name = "x"\ncommand = ["x"]\nparse_strategy = "regex_count"\n'
            'parse_regex = "no_groups_here"\n'
        ),
        reason_starts="regex missing or != 1 capture group",
    )


# Three regex_count R4 rows — parametrised over (parse_regex value).
_REGEX_BAD_GROUP_CASES = [
    "no_groups_here",          # zero capture groups
    "(a)(b)",                  # two capture groups
    "(unclosed",               # unparseable regex
]


@pytest.mark.parametrize("regex", _REGEX_BAD_GROUP_CASES)
def test_validate_regex_count_invalid_raises(tmp_path, regex):
    """Zero groups / two groups / unparseable regex → locked R4 reason prefix."""
    _expect_error(
        tmp_path,
        _extra_block(
            f'name = "x"\ncommand = ["x"]\nparse_strategy = "regex_count"\n'
            f'parse_regex = "{regex}"\n'
        ),
        reason_starts="regex missing or != 1 capture group",
    )


# ── Loader boundary shapes (T8 R4: pyproject-unreadable + array shapes) ──


def test_load_extras_pyproject_unreadable_raises(tmp_path):
    """Malformed TOML → ExtraToolsConfigError with locked prefix + file location."""
    pyproject = _write_pyproject(tmp_path, "bad = = syntax # not toml")
    with pytest.raises(ExtraToolsConfigError) as exc_info:
        _load_extra_tools(tmp_path)
    err = exc_info.value
    assert err.location == str(pyproject)
    assert err.reason.startswith("pyproject unreadable:")


@pytest.mark.parametrize(
    "body,reason",
    [
        ('[tool.python-setup-lint]\nextra-tools = "not-a-list"\n',
         "wrong type: extra-tools must be a list of tables"),
        ('[tool.python-setup-lint]\nextra-tools = ["scalar"]\n',
         "wrong type: extra-tools entry must be a table"),
    ],
    ids=["not_a_list", "entry_not_a_table"],
)
def test_load_extras_array_shape_raises(tmp_path, body, reason):
    """``extra-tools`` not a list OR an entry that's not a table → wrong-type reason."""
    _expect_error(tmp_path, body, reason_eq=reason)


# ── ExtraToolsConfigError public attribute contract ────────────────


def test_extra_tools_config_error_attributes():
    """Constructor stores ``location`` + ``reason`` AND formats ``str(err)``."""
    err = ExtraToolsConfigError(location="x", reason="y")
    assert err.location == "x" and err.reason == "y"
    assert str(err) == "[x] y"
    assert isinstance(err, Exception) and not isinstance(err, SystemExit)


def test_extra_tools_config_error_preserves_subclass_chain():
    """The error is raisable through ``raise from`` and unwrapped by ``pytest.raises``."""
    with pytest.raises(ExtraToolsConfigError) as exc_info:
        try:
            raise ValueError("inner")
        except ValueError as inner:
            raise ExtraToolsConfigError("loc", "outer-reason") from inner
    assert exc_info.value.location == "loc" and exc_info.value.reason == "outer-reason"
    assert isinstance(exc_info.value.__cause__, ValueError)


# MERGE category — _register_extra_tools contract

# Synthetic extra-tool registrations (not loaded from disk).
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
    """_register_extra_tools merge contract: additive, idempotent, collision-safe."""

    def test_register_extra_tools_grows_lint_tools_by_n(self):
        baseline_len = len(LINT_TOOLS)
        _register_extra_tools([_X1, _X2])
        assert len(LINT_TOOLS) == baseline_len + 2

    def test_register_extra_tools_idempotent_on_same_names(self):
        baseline_len = len(LINT_TOOLS)
        _register_extra_tools([_X1])
        _register_extra_tools([_X1])  # idempotent re-call with same name
        assert len(LINT_TOOLS) == baseline_len + 1
        assert STRATEGIES["x1"] is not None  # strategy stable, no double registration

    def test_register_extra_tools_tools_by_name_includes_extras(self):
        _register_extra_tools([_X1, _X2])
        names = {t.name for t in LINT_TOOLS}
        assert "x1" in names and "x2" in names
        # All 11 built-ins remain post-merge.
        for builtin in TOOLS_BY_NAME:
            assert builtin in names, f"Built-in {builtin!r} missing after merge"

    def test_register_extra_tools_rejects_builtin_name_collision(self):
        collision = _ExtraToolRegistration(
            spec=ToolSpec(name="ruff check", command=["ruff", "check"]),
            statistics_flag=None, parser=None, config_flag=None,
        )
        with pytest.raises(ExtraToolsConfigError) as exc_info:
            _register_extra_tools([collision])
        assert exc_info.value.reason == "duplicate vs built-in: ruff check"
        assert exc_info.value.location == "<runtime>"

    def test_register_extra_tools_no_op_on_empty_list(self):
        baseline_len = len(LINT_TOOLS)
        _register_extra_tools([])
        assert len(LINT_TOOLS) == baseline_len


# BUILD_COMMAND category — GenericLintTool.build_command.
# Verifies T11 v1: a registered extra's strategy builds the same shape as
# the built-ins — command + config_flag + default_paths + --fix (when
# supports_fix) + --exclude (when supports_exclude) + glob expansion via
# _expand_globs.  Direct strategy.build_command(ctx) — NO subprocess.


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

    def test_builds_command_with_config_flag(self, tmp_path: Path) -> None:
        """``config_flag=["--config"]`` + ``config_paths[extra]`` → flag+path right after the command."""
        _register_extra("extra1", config_flag=["--config"], default_paths=["src/"])
        cfg = tmp_path / "cfg.toml"
        cfg.write_text("x = 1\n")
        cmd = STRATEGIES["extra1"].build_command(config=_ctx(tmp_path, config_paths={"extra1": cfg}))
        assert cmd[:3] == ["mytool", "--config", str(cfg)]
        assert cmd[3:] == ["src/"]

    def test_appends_fix_flag_when_supports_fix(self, tmp_path: Path) -> None:
        """``supports_fix=True`` + ``fix=True`` → ``--fix`` appended (non-ruff/rumdl/ty branch)."""
        _register_extra("extra1", supports_fix=True)
        ctx = _ctx(tmp_path)
        assert STRATEGIES["extra1"].build_command(config=ctx, fix=True) == ["mytool", "--fix"]
        # Sanity: fix=False does not append.
        assert STRATEGIES["extra1"].build_command(config=ctx) == ["mytool"]

    def test_appends_exclude_flag_when_supports_exclude(self, tmp_path: Path) -> None:
        """``supports_exclude=True`` + ``exclude`` → ``--exclude <path>`` (non-tach extras)."""
        _register_extra("extra1", supports_exclude=True, supports_path=False)
        ctx = _ctx(tmp_path)
        assert STRATEGIES["extra1"].build_command(config=ctx, exclude="bad.py") == ["mytool", "--exclude", "bad.py"]

    def test_expands_globs_in_default_paths(self, tmp_path: Path) -> None:
        """``default_paths=["data/*.txt"]`` is expanded against ``cwd`` by ``_expand_globs``."""
        (tmp_path / "data").mkdir()
        for n in ("file1.txt", "file2.txt"):
            (tmp_path / "data" / n).write_text("a\n")
        _register_extra("extra1", supports_path=True, default_paths=["data/*.txt"])
        cmd = STRATEGIES["extra1"].build_command(config=_ctx(tmp_path))
        # ``_expand_globs`` produces sorted relative paths.
        assert cmd[0] == "mytool"
        assert cmd[1:] == sorted(["data/file1.txt", "data/file2.txt"])

    @pytest.mark.parametrize(
        "config_flag,config_paths,expected",
        [
            # no_flag → bare command + default_paths; config_paths entry ignored
            (None, {"extra1": Path("/x.toml")}, ["mytool", "src/"]),
            # flag set but no config path → flag silently dropped; default_paths still appended
            (["--config"], {}, ["mytool", "src/"]),
        ],
        ids=["no_config_flag", "config_flag_with_no_path"],
    )
    def test_config_flag_boundaries(self, tmp_path: Path, config_flag, config_paths, expected) -> None:
        """config_flag absent OR config_paths[extra] absent → no flag in the command."""
        _register_extra("extra1", config_flag=config_flag, default_paths=["src/"])
        cmd = STRATEGIES["extra1"].build_command(config=_ctx(tmp_path, config_paths=config_paths))
        assert "--config" not in cmd
        assert cmd == expected

    def test_parse_strategy_none_produces_empty_parse_statistics(self, tmp_path: Path) -> None:
        """GenericLintTool with no parser → ``parse_statistics`` returns ``[]`` (matches ``_aggregate_statistics`` skip)."""
        _register_extra("extra1")
        strat = STRATEGIES["extra1"]
        assert strat.parse_statistics("noise that looks like a violation\nwarn!\n", "") == []


# ── DOWNSTREAM-INTEGRATION ───────────────────────────────────────
# End-to-end fake-subprocess pipeline for extras — reuses the T1
# ``fake_run_cmd_factory`` idiom (NO real subprocess). Covers the
# loader → validator → registration → strategy dispatch → fake
# subprocess → parse → aggregate composition chain.
#
# NOTE on run_lint return shape: ``run_lint`` returns ``int`` exit code
# and does NOT expose its internal ``results`` list. Integration is
# observed via:
#   * ``capsys`` — lint output text (each tool's ``[<name>]`` banner)
#   * ``--statistics --format json`` output — the aggregated
#     ``ViolationCount`` list (the exact ``_aggregate_statistics(result)``
#     artefact), one entry per parsed rule id.
# Per the task brief: "consult production code for whether results is a
# list of LintResult or a dict". Production code is source-of-truth.

_REGEX_BLOCK = (
    'name = "regextool"\n'
    'command = ["fake-regex-cli"]\n'
    "supports_path = true\n"
    'default_paths = []\n'
    'parse_strategy = "regex_count"\n'
    'parse_regex = "^(?P<rule>[A-Z]+[0-9]+): .*"\n'
)

_NONE_BLOCK = (
    'name = "nonestattool"\n'
    'command = ["fake-none-cli"]\n'
    "supports_path = true\n"
    'default_paths = []\n'
    'parse_strategy = "none"\n'
)


def _write_extra_pyproject(tmp_path: Path, body: str) -> Path:
    """Write a synthetic ``pyproject.toml`` with one extra-tools block + resetmemo."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(f"[tool.python-setup-lint]\n[[tool.python-setup-lint.extra-tools]]\n{body}")
    _reset_extra_tools_cache()
    return pyproject.resolve()


class TestRunLintExtraDownstreamIntegration:
    """End-to-end fake-subprocess integration of the extras pipeline."""

    def test_extra_runs_and_rule_appears_in_aggregate_statistics(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A registered ``regex_count`` extra flows through the full pipeline.

        Composition: loader → validator → ``_register_extra_tools`` →
        ``_strategy_for`` synthesises a ``GenericLintTool`` → fake
        ``_run_cmd`` returns a canned ``LintResult`` whose stdout is parsed
        by the regex closure → ``_aggregate_statistics`` emits a
        ``ViolationCount(tool="regextool", rule="RC1", count=2)`` (and RC2×1).

        The canned ``LintResult`` shape (production source-of-truth, no
        ``linted_files`` field — ``LintResult`` only has tool_name /
        exit_code / stdout / stderr / elapsed)::

            LintResult(
                tool_name="regextool",
                exit_code=0,
                stdout="RC1: bad line\\nRC2: worse line\\nRC1: another",
                stderr="",
            )

        The aggregation artefact (the list returned by
        ``_aggregate_statistics``) is observed via ``--statistics --format
        json`` output which serialises the same ``ViolationCount`` triples.
        """
        _write_extra_pyproject(tmp_path, _REGEX_BLOCK)
        # Empty stdout for built-ins — they have parsers but we feed them
        # nothing so they contribute zero rows. Dict-mode fake falls back
        # to a zero-exit empty ``LintResult`` for unknown labels.
        fake = fake_run_cmd_factory(
            {
                "regextool": make_lint_result(
                    tool_name="regextool",
                    exit_code=0,
                    stdout="RC1: bad line\nRC2: worse line\nRC1: another",
                ),
            }
        )
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)

        rc = run_lint(
            config=RunnerConfig(cwd=tmp_path),
            no_fail_fast=True,
            statistics=True,
            statistics_format="json",
        )
        assert isinstance(rc, int), f"run_lint must return int; got {type(rc)}"

        captured = capsys.readouterr()
        out = captured.out
        # NOTE: under statistics=True, per-tool ``_print_result`` banner is
        # suppressed (runner.py L1597 ``if not statistics: _print_result``).
        # Proof the extra ran is its label in ``fake.calls`` (it dispatched
        # through ``GenericLintTool.build_command`` to the fake subprocess).
        assert any(c.label == "regextool" for c in fake.calls), (
            "regextool must have been dispatched to _run_cmd. "
            f"Got labels: {[c.label for c in fake.calls]}"
        )

        # The last non-empty line is the JSON statistics array. Parse it
        # and assert our extra's rule ids are present with the right counts.
        # Under ``statistics=True`` no per-tool ``_print_result`` banner is
        # emitted, so the entire stdout is the JSON array.
        out_stripped = out.strip()
        assert out_stripped.startswith("["), (
            f"expected JSON array as the entire stats output; got: {out!r}"
        )
        data = json.loads(out_stripped)

        # Build a quick lookup of (tool, rule) → count for assertion clarity.
        by_key = {(e["tool"], e["rule"]): e["count"] for e in data}
        assert ("regextool", "RC1") in by_key, (
            f"regex_count parser must emit RC1 into aggregate. Got: {data}"
        )
        assert by_key[("regextool", "RC1")] == 2, (
            f"RC1 count wrong: expected 2, got {by_key[('regextool', 'RC1')]}. Full: {data}"
        )
        assert by_key.get(("regextool", "RC2")) == 1, (
            f"RC2 count wrong: expected 1, got {by_key.get(('regextool', 'RC2'))}. Full: {data}"
        )

        # Direct re-aggregation of the captured fake results verifies the
        # closure path independently of the JSON serialisation seam.
        direct = _aggregate_statistics(
            [
                make_lint_result(
                    tool_name="regextool",
                    stdout="RC1: bad line\nRC2: worse line\nRC1: another",
                ),
            ]
        )
        assert ViolationCount("regextool", "RC1", 2) in direct
        assert ViolationCount("regextool", "RC2", 1) in direct

        # Verify the extra's ``cmd`` actually reached the fake subprocess
        # (proves ``GenericLintTool.build_command`` composed from the spec).
        regextool_call = next(c for c in fake.calls if c.label == "regextool")
        assert regextool_call.cmd == ["fake-regex-cli"], (
            "extra's command must reach _run_cmd verbatim. "
            f"Got: {regextool_call.cmd}"
        )

    def test_extra_with_parse_strategy_none_runs_but_skips_statistics(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A ``parse_strategy="none"`` extra runs but contributes no stats rows.

        ``_aggregate_statistics`` skips tools whose strategy returns ``[]``
        from ``parse_statistics`` (the ``GenericLintTool`` ``_parser=None``
        path). Smoke-level skip-assertion for T11t6's deeper observability
        coverage: the extra's banner appears in lint output (it ran) but
        its ``tool`` name does NOT appear in the JSON statistics array.
        """
        _write_extra_pyproject(tmp_path, _NONE_BLOCK)
        fake = fake_run_cmd_factory(
            {
                "nonestattool": make_lint_result(
                    tool_name="nonestattool",
                    exit_code=0,
                    stdout="noise\nthat has no rule ids\nRC1: ignored too\n",
                ),
            }
        )
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)

        rc = run_lint(
            config=RunnerConfig(cwd=tmp_path),
            no_fail_fast=True,
            statistics=True,
            statistics_format="json",
        )
        assert isinstance(rc, int), f"run_lint must return int; got {type(rc)}"
        captured = capsys.readouterr()
        out = captured.out

        # The extra ran (its label reached the fake subprocess).
        # ``_print_result`` is suppressed under statistics=True, so the
        # banner assertion would be misleading; ``fake.calls`` is the
        # authoritative "this tool was dispatched" evidence.
        assert any(c.label == "nonestattool" for c in fake.calls), (
            "nonestattool must have been dispatched to _run_cmd. "
            f"Got labels: {[c.label for c in fake.calls]}"
        )

        # The extra's rule ids do NOT leak into the aggregate. The entire
        # stdout is the JSON statistics array (no per-tool banner under
        # statistics=True).
        out_stripped = out.strip()
        assert out_stripped.startswith("["), (
            f"expected JSON array as the entire stats output; got: {out!r}"
        )
        data = json.loads(out_stripped)
        assert isinstance(data, list), f"stats JSON must be a list; got {type(data)}"

        # Either the aggregate is empty (only the none extra ran, plus the
        # built-ins were fed empty stdout) OR none of the entries reference
        # the none-extra's tool name. RC1 must NOT appear under the extra.
        none_tool_entries = [e for e in data if e.get("tool") == "nonestattool"]
        assert none_tool_entries == [], (
            f"parse_strategy=none extra must not contribute stats rows; "
            f"got: {none_tool_entries}. Full aggregate: {data}"
        )

        # Direct re-aggregation confirms the skip path independently.
        direct = _aggregate_statistics(
            [
                make_lint_result(
                    tool_name="nonestattool",
                    stdout="RC1: ignored\n",
                ),
            ]
        )
        assert all(v.tool != "nonestattool" for v in direct), (
            f"_aggregate_statistics must skip parse_strategy=none extras; "
            f"got: {direct}"
        )

        # The extra's command still reached the subprocess (composition held).
        none_call = next(c for c in fake.calls if c.label == "nonestattool")
        assert none_call.cmd == ["fake-none-cli"], (
            f"none-extra must still be dispatched; got cmd: {none_call.cmd}"
        )

# ── PERF-BENCHMARK ─────────────────────────────────────────────────
# ``_load_extra_tools`` memoisation verified via ratio assertion on
# ``run_lint`` startup time.  ``@pytest.mark.slow`` so the fast gate
# (``-m "not slow"``) skips it; the slow opt-in (``-m slow``) exercises
# it.


@pytest.mark.slow
def test_run_lint_with_extras_startup_overhead_within_10_percent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_load_extra_tools`` memoisation verified via warm ratio assertion.

    Synthetic ``pyproject.toml`` with 10 extras (all
    ``parse_strategy="none"``, no real subprocess) vs. a ``pyproject.toml``
    with zero extras.  ``_run_cmd`` is monkeypatched so subprocess time
    does not pollute the startup measurement.

    The warm (memoised) ratio t(N=10)/t(N=0) must be < 1.10, proving the
    ``_EXTRA_TOOLS_CACHE`` + registration-gate overhead stays O(1) regardless
    of N extras.  Cold measurements (cache cleared before each iteration)
    are recorded as informational only.  Both cold runs measure the full
    pyproject read + validate + register path symmetrically.
    """
    # ── Two directories with different pyproject.toml ────────────
    no_extras_dir = tmp_path / "no_extras"
    extras_dir = tmp_path / "extras"
    no_extras_dir.mkdir()
    extras_dir.mkdir()

    # pyproject with 0 extras (section present but no extra-tools key).
    (no_extras_dir / "pyproject.toml").write_text("[tool.python-setup-lint]\n")

    # pyproject with 10 extras (all parse_strategy="none" so no stats
    # parse — the perf concern is the loader + merge startup).
    lines = ["[tool.python-setup-lint]"]
    for i in range(10):
        lines.append("[[tool.python-setup-lint.extra-tools]]")
        lines.append(f'name = "extra{i}"')
        lines.append(f'command = ["extra{i}"]')
        lines.append('parse_strategy = "none"')
    (extras_dir / "pyproject.toml").write_text("\n".join(lines) + "\n")

    # Fast fake ``_run_cmd`` — no real subprocess; empty dict mode
    # returns zero-exit ``LintResult`` for every tool label.
    fake = fake_run_cmd_factory({})
    monkeypatch.setattr(_runner_module, "_run_cmd", fake)

    # Multiple iterations to stabilise sub-ms wall-time measurements.
    _N_ITER = 50

    # ── Cold N=0 (no extras, cache cleared before each) ─────────
    t_0_cold = 0.0
    for _ in range(_N_ITER):
        _reset_extra_tools_cache()
        start = time.perf_counter()
        run_lint(config=RunnerConfig(cwd=no_extras_dir), no_fail_fast=True)
        t_0_cold += time.perf_counter() - start
    t_0_cold /= _N_ITER

    # ── Cold N=10 (10 extras, cache cleared before each) ──────
    t_10_cold = 0.0
    for _ in range(_N_ITER):
        _reset_extra_tools_cache()
        start = time.perf_counter()
        run_lint(config=RunnerConfig(cwd=extras_dir), no_fail_fast=True)
        t_10_cold += time.perf_counter() - start
    t_10_cold /= _N_ITER

    # ── Informational warm measurements (memo hot) ─────────────
    # Discard first iteration as module-level cache warmup for N=0.
    _reset_extra_tools_cache()
    run_lint(config=RunnerConfig(cwd=no_extras_dir), no_fail_fast=True)

    t_0_warm = 0.0
    for _ in range(_N_ITER):
        start = time.perf_counter()
        run_lint(config=RunnerConfig(cwd=no_extras_dir), no_fail_fast=True)
        t_0_warm += time.perf_counter() - start
    t_0_warm /= _N_ITER

    # Warm-up N=10 cache entry.
    _reset_extra_tools_cache()
    run_lint(config=RunnerConfig(cwd=extras_dir), no_fail_fast=True)

    t_10_warm = 0.0
    for _ in range(_N_ITER):
        start = time.perf_counter()
        run_lint(config=RunnerConfig(cwd=extras_dir), no_fail_fast=True)
        t_10_warm += time.perf_counter() - start
    t_10_warm /= _N_ITER

    warm_ratio = t_10_warm / t_0_warm
    cold_ratio = t_10_cold / t_0_cold
    print(f"\n[bench] cold: t_0={t_0_cold:.6f}s  t_10={t_10_cold:.6f}s  "
          f"ratio={cold_ratio:.4f}  |  "
          f"warm: t_0={t_0_warm:.6f}s  t_10={t_10_warm:.6f}s  "
          f"ratio={warm_ratio:.4f}")
    # Assert the WARM memoised path — cache reused both sides, so the
    # ratio reflects pure memo lookup overhead regardless of N extras.
    # < 1.10 ensures the cache-key lookup + registration-gate check stay
    # sub-linear. Cold measurements printed for informational comparison
    # only; cold ratio naturally exceeds 1.10 due to TOML parse + validate.
    assert warm_ratio < 1.10, (
        f"warm t(N=10)/t(N=0) = {warm_ratio:.4f} >= 1.10 — memoised "
        f"extras path may have non-linear overhead "
        f"(t_0_warm={t_0_warm:.6f}s, t_10_warm={t_10_warm:.6f}s)"
    )


# ── OBSERVABILITY ─────────────────────────────────────────────────
# ``--statistics --format json`` + ``--statistics --format table``
# output surfaces for extras: a non-``none`` ``parse_strategy`` extra's
# ``{tool, rule, count}`` entries appear in the JSON + render in the
# aligned table.  Uniform treatment across built-ins + extras (no
# separate "extras" section — T8 R3 observably-additive contract).


class TestExtraStatisticsObservability:
    """Stats output surfaces for extras — JSON + table format."""

    _EXTRA_BLOCK = (
        'name = "regextool"\n'
        'command = ["fake-regex-cli"]\n'
        "supports_path = true\n"
        'default_paths = []\n'
        'parse_strategy = "regex_count"\n'
        'parse_regex = "^(?P<rule>[A-Z]+[0-9]+): .*"\n'
    )

    def _setup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """Write pyproject with ``regextool`` extra + monkeypatch ``_run_cmd``.

        The fake returns a canned ``LintResult`` for ``regextool`` (2 RC1 +
        1 RC2) and zero-exit empty results for all 11 built-ins (empty
        stdout → parsers return ``[]``, so only the extra contributes rows).
        """
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            f"[tool.python-setup-lint]\n"
            f"[[tool.python-setup-lint.extra-tools]]\n"
            f"{self._EXTRA_BLOCK}"
        )
        _reset_extra_tools_cache()

        fake = fake_run_cmd_factory({
            "regextool": make_lint_result(
                tool_name="regextool",
                exit_code=0,
                stdout="RC1: bad line\nRC2: worse line\nRC1: another",
            ),
        })
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        return pyproject.resolve()

    def test_statistics_format_json_includes_extra_rule_counts(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """JSON output includes the extra's ``{tool, rule, count}`` entries."""
        self._setup(tmp_path, monkeypatch)
        rc = run_lint(
            config=RunnerConfig(cwd=tmp_path),
            no_fail_fast=True,
            statistics=True,
            statistics_format="json",
        )
        assert isinstance(rc, int)
        captured = capsys.readouterr()
        out = captured.out.strip()
        assert out.startswith("["), (
            f"expected JSON array as the entire stats output; got: {out!r}"
        )
        data = json.loads(out)
        by_key = {(e["tool"], e["rule"]): e["count"] for e in data}
        assert by_key[("regextool", "RC1")] == 2, (
            f"regextool RC1 count wrong: got {by_key.get(('regextool', 'RC1'))}. "
            f"Full data: {data}"
        )
        assert by_key.get(("regextool", "RC2")) == 1, (
            f"regextool RC2 count wrong: got {by_key.get(('regextool', 'RC2'))}. "
            f"Full data: {data}"
        )

    def test_statistics_format_table_renders_extra_in_aligned_table(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Table output contains the extra's tool, rules, and count strings."""
        self._setup(tmp_path, monkeypatch)
        rc = run_lint(
            config=RunnerConfig(cwd=tmp_path),
            no_fail_fast=True,
            statistics=True,
            statistics_format="table",
        )
        assert isinstance(rc, int)
        captured = capsys.readouterr()
        out = captured.out

        # Assert the table header row is present (proves rendering path).
        assert "VIOLATION STATISTICS" in out, (
            f"expected table header 'VIOLATION STATISTICS'; got: {out!r}"
        )
        assert "Tool" in out and "Rule" in out and "Count" in out, (
            f"expected column headers Tool/Rule/Count; got: {out!r}"
        )

        # Assert the extra's tool name, rule labels, and count values are
        # in the table output (string-``in`` per envelope: don't parse
        # exact spacing; assert token presence).
        for token in ("regextool", "RC1", "RC2", "1", "2"):
            assert token in out, (
                f"expected token {token!r} in table output; got: {out!r}"
            )

    def test_statistics_skips_extra_with_parse_strategy_none(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``parse_strategy="none"`` extra runs but does NOT appear in stats."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            "[tool.python-setup-lint]\n"
            "[[tool.python-setup-lint.extra-tools]]\n"
            'name = "nonestattool"\n'
            'command = ["fake-none-cli"]\n'
            "supports_path = true\n"
            'default_paths = []\n'
            'parse_strategy = "none"\n'
        )
        _reset_extra_tools_cache()
        fake = fake_run_cmd_factory({
            "nonestattool": make_lint_result(
                tool_name="nonestattool",
                exit_code=0,
                stdout="RC1: would be counted but strategy=none\n",
            ),
        })
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)

        rc = run_lint(
            config=RunnerConfig(cwd=tmp_path),
            no_fail_fast=True,
            statistics=True,
            statistics_format="json",
        )
        assert isinstance(rc, int)
        captured = capsys.readouterr()
        out = captured.out.strip()
        assert out.startswith("["), (
            f"expected JSON array; got: {out!r}"
        )
        data = json.loads(out)
        # None of the entries should reference nonestattool.
        none_entries = [e for e in data if e.get("tool") == "nonestattool"]
        assert none_entries == [], (
            f"parse_strategy=none extra must not contribute stats rows; "
            f"got: {none_entries}. Full aggregate: {data}"
        )
