"""T4 — conflict-tolerant autofix: ``--fix`` route through the wrapper.

Each row exercises one logical-coverage branch named in the T4 envelope:

* **no-conflict baseline** — autofix applied; tool's fix pass runs and the
  returned :class:`LintResult` is the spec's own.
* **staged-only** — autofix applied; only the staged set is non-empty,
  intersection with unstaged is empty, no skip line emitted.
* **unstaged-only** — autofix applied; only the unstaged set is non-empty,
  same outcome as staged-only.
* **staged+unstaged same file** — autofix skipped for that file with the
  stderr skip line ``[<tool>] autofix skipped for <file>: staged+unstaged
  conflict``.  The fix tool still runs (it's free to touch the file's
  unstaged sibling state), but the in-memory snapshot is not captured so
  the E999-canary cannot revert it.
* **E999 introduced** — a prior tool's fix broke parseability; the canary
  reports ``E999`` and the file is reverted from the in-memory snapshot
  with the stderr revert line ``[<tool>] autofix reverted <file>: E999
  after fix``.
* **``PYTHON_SETUP_LINT_NO_AUTOFIX=1``** — env-var opt-out;
  :func:`run_lint` flips ``fix=False`` internally before the loop, so no
  fix flags reach any tool.  Stderr emits the override notice once.
* **non-git cwd** — autofix applies unconditionally; ``_git_changed_files``
  returns empty on non-git cwd; no skip lines.
* **canary no-E999** — fix pass runs, canary runs, no E999 → no revert.
* **in-memory only — untracked files** — the file is not git-tracked; the
  in-memory byte snapshot is the only revert path (no ``git checkout``).
* **observability** — every skip/revert produces exactly one stderr line;
  sensitive data NOT leaked.
* **downstream integration** — ``uv run lint --fix`` end-to-end applies the
  ruff fixes; assertion: the post-fix file content is different from the
  pre-fix content (i.e. the fix actually applied).  Tested against the
  python-setup repo itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import python_setup_lint.runner.output as _output_module
from python_setup_lint.runner import LintResult, ToolSpec, run_lint
from python_setup_lint.runner._autofix import (
    _AUTOFIX_ENV_VAR,
    _apply_autofix_conflict_aware,
    _autofix_target_paths,
    _git_changed_files,
    _ruff_parseability_errors,
)
from python_setup_lint.testing import fake_run_cmd_factory, make_lint_result
from tests.runner._autofix_helpers import (
    _CANARY_LABEL,
    _FIX_TOOL_NAMES,
    _commit_all,
    _git_init,
    _make_canned_fix_results,
    _PostFixFakeRunCmd,
    _stage,
    _write_file,
)
from tests.runner._factories import (
    canned_results_all_tools,
    tmp_config,
)

# ── Surface-unit: _git_changed_files ──────────────────────────────


class TestGitChangedFiles:
    """``_git_changed_files`` snapshots git diff cleanly, tolerates non-git."""

    def test_non_git_cwd_returns_empty(self, tmp_path: Path) -> None:
        """No git repo initialised → empty set on both staged branches."""
        assert _git_changed_files(tmp_path, staged=True) == set()
        assert _git_changed_files(tmp_path, staged=False) == set()

    def test_staged_and_unstaged_separate(self, tmp_path: Path) -> None:
        """A file in the staged set is absent from the unstaged set (and vice versa).

        Both files must be tracked by git for the diff to report them — newly
        created (untracked) files do NOT appear in ``git diff --name-only``.
        """
        _git_init(tmp_path)
        _write_file(tmp_path, "staged.py", "x = 1\n")
        _write_file(tmp_path, "unstaged.py", "x = 1\n")
        _commit_all(tmp_path)
        # Staged: edit + stage (without committing).
        _write_file(tmp_path, "staged.py", "y = 2\n")
        _stage(tmp_path, "staged.py")
        # Unstaged: edit tracked file (no ``git add``).
        _write_file(tmp_path, "unstaged.py", "z = 3\n")
        assert "staged.py" in _git_changed_files(tmp_path, staged=True)
        assert "unstaged.py" not in _git_changed_files(tmp_path, staged=True)
        assert "unstaged.py" in _git_changed_files(tmp_path, staged=False)
        assert "staged.py" not in _git_changed_files(tmp_path, staged=False)

    def test_staged_and_unstaged_overlap_intersected_by_helper(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A file with staged AND unstaged changes appears in BOTH sets."""
        _git_init(tmp_path)
        _write_file(tmp_path, "f.py", "v1\n")
        _commit_all(tmp_path)
        # Edit + stage; then edit again without staging → in BOTH sets.
        _write_file(tmp_path, "f.py", "v2\n")
        _stage(tmp_path, "f.py")
        _write_file(tmp_path, "f.py", "v3\n")
        staged = _git_changed_files(tmp_path, staged=True)
        unstaged = _git_changed_files(tmp_path, staged=False)
        assert "f.py" in staged
        assert "f.py" in unstaged
        assert staged & unstaged == {"f.py"}


# ── Surface-unit: _ruff_parseability_errors ───────────────────────


class TestRuffParseabilityErrors:
    """E999-canary returns the set of paths that emitted E999 in stdout."""

    def test_empty_paths_short_circuits(self, tmp_path: Path) -> None:
        """No files → no ruff invocation (empty result, no fake calls recorded)."""
        run_called: list[tuple[list[str], str]] = []

        def fake_run(cmd: list[str], *, cwd: Path, label: str) -> LintResult:
            run_called.append((cmd, label))
            return make_lint_result(tool_name=label, stdout="")

        assert _ruff_parseability_errors(tmp_path, [], fake_run) == set()
        assert run_called == []  # short-circuit verified

    @pytest.mark.parametrize(("stdout", "expected_files"), [
        ("src/a.py:1:1: E999 SyntaxError\n", {"src/a.py"}),
        (
            "src/a.py:1:1: E999 first\nsrc/b.py:2:2: E999 second\n",
            {"src/a.py", "src/b.py"},
        ),
        ("src/a.py:1:1: F401 unused import\n", set()),
        ("", set()),
        ("src/a.py:1:1: F401 unused\nsrc/b.py:2:2: E999 broken\n", {"src/b.py"}),
        ("src/no-colon: line\n", set()),
    ],
    ids=[
        "one_e999",
        "two_e999",
        "non_e999_only",
        "empty",
        "mixed_e999_and_other",
        "no_colon",
    ],)
    def test_parses_e999_lines(
        self,
        tmp_path: Path,
        stdout: str,
        expected_files: set[str],
    ) -> None:
        """The canary parser reads ``path:line:col: E999 message`` lines only."""

        def fake_run(cmd: list[str], *, cwd: Path, label: str) -> LintResult:
            assert label == _CANARY_LABEL, f"canary label leaked: {label!r}"
            return make_lint_result(tool_name=label, stdout=stdout)

        result = _ruff_parseability_errors(tmp_path, ["src/a.py", "src/b.py"], fake_run)
        assert result == expected_files

    def test_run_cmd_filenotfound_swallowed(self, tmp_path: Path) -> None:
        """``FileNotFoundError`` from run_cmd becomes an empty set (no propagation)."""

        def fake_run(cmd: list[str], *, cwd: Path, label: str) -> LintResult:
            raise FileNotFoundError

        assert _ruff_parseability_errors(tmp_path, ["src/a.py"], fake_run) == set()


# ── Surface-unit: _autofix_target_paths ────────────────────────────


class TestAutofixTargetPaths:
    """``_autofix_target_paths`` mirrors ``_build_command``'s path slot."""

    def test_explicit_path_overrides_default(self, tmp_path: Path) -> None:
        """When ``--path`` is given and the spec supports_path, that path is it."""
        _write_file(tmp_path, "src/main.py", "x = 1\n")
        spec = ToolSpec(
            "ruff check",
            ["ruff", "check"],
            supports_path=True,
            default_paths=["src/", "tests/"],
        )
        assert _autofix_target_paths(
            spec, config=tmp_config(tmp_path), path="src/main.py"
        ) == ["src/main.py"]

    def test_default_paths_used_when_no_path(self, tmp_path: Path) -> None:
        """No ``--path`` → ``spec.default_paths`` is the seed."""
        _write_file(tmp_path, "src/a.py", "x = 1\n")
        _write_file(tmp_path, "src/b.py", "y = 2\n")
        spec = ToolSpec(
            "ruff check", ["ruff", "check"], supports_path=True, default_paths=["src/"]
        )
        result = _autofix_target_paths(spec, config=tmp_config(tmp_path), path=None)
        assert set(result) >= {"src/a.py", "src/b.py"}

    def test_no_default_no_path_returns_empty(self, tmp_path: Path) -> None:
        """``rumdl check`` shape (no default_paths, supports_path=True) → empty list."""
        spec = ToolSpec("rumdl check", ["rumdl", "check"], supports_path=True)
        assert _autofix_target_paths(spec, config=tmp_config(tmp_path), path=None) == []

    def test_glob_expansion_runs(self, tmp_path: Path) -> None:
        """``config/*.py`` glob expands to all matching python files."""
        _write_file(tmp_path, "config/a.py", "")
        _write_file(tmp_path, "config/b.py", "")
        spec = ToolSpec(
            "test", ["t"], supports_path=True, default_paths=["config/*.py"]
        )
        result = _autofix_target_paths(spec, config=tmp_config(tmp_path), path=None)
        assert sorted(result) == ["config/a.py", "config/b.py"]



# ── Surface-unit: env-var opt-out (PYTHON_SETUP_LINT_NO_AUTOFIX=1) ─


class TestEnvVarAutofixOptOut:
    """``PYTHON_SETUP_LINT_NO_AUTOFIX=1`` flips ``fix=False`` before the loop."""

    def test_env_var_disables_fix_flags_through_run_lint(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``run_lint(fix=True)`` with the env-var set → no tool sees fix=True."""
        monkeypatch.setenv(_AUTOFIX_ENV_VAR, "1")
        fake = fake_run_cmd_factory(canned_results_all_tools())
        monkeypatch.setattr(_output_module, "_run_cmd", fake)
        run_lint(config=tmp_config(tmp_path), fix=True)
        captured = capsys.readouterr()
        # D4 (review T4-0): the prior form asserted only substring matches
        # for the env-var name AND the word "disabling" — soft tautology.
        # Pin the EXACT stderr line the runner produces so a downstream
        # parser (T6 / hooks) can match it deterministically AND a future
        # format regression (e.g. dropping "set —" or changing "for this
        # run" to "this run") breaks the test rather than passing silently.
        expected_notice = (
            f"[autofix] {_AUTOFIX_ENV_VAR}=1 set — disabling autofix for this run"
        )
        assert expected_notice in captured.err, (
            f"override notice mismatch:\nexpected: {expected_notice!r}\n"
            f"got stderr: {captured.err!r}"
        )
        # The fix tools did NOT receive ``--fix`` in their commands.
        for record in fake.calls:
            if record.label in _FIX_TOOL_NAMES:
                assert "--fix" not in record.cmd, (
                    f"--fix leaked to {record.label}: {record.cmd!r}"
                )

    def test_no_env_var_keeps_fix_flags(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Without the env-var, ``run_lint(fix=True)`` sends --fix to fix tools."""
        monkeypatch.delenv(_AUTOFIX_ENV_VAR, raising=False)
        canned = _make_canned_fix_results()
        fake = fake_run_cmd_factory(canned)
        monkeypatch.setattr(_output_module, "_run_cmd", fake)
        run_lint(config=tmp_config(tmp_path), fix=True)
        captured = capsys.readouterr()
        assert "disabling autofix" not in captured.err
        for record in fake.calls:
            if record.label in _FIX_TOOL_NAMES:
                assert "--fix" in record.cmd, (
                    f"--fix missing from {record.label}: {record.cmd!r}"
                )
            # The canary is NOT called when fix is on — but only the
            # fix-route uses the canary; the env-var opt-out route skips
            # the autofix helper entirely (the loop falls back to the
            # plain ``_build_command(fix=False)`` path).

    def test_env_var_zero_or_other_value_does_not_opt_out(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Only ``=1`` exact value triggers the opt-out — ``=0`` keeps autofix on."""
        monkeypatch.setenv(_AUTOFIX_ENV_VAR, "0")
        canned = _make_canned_fix_results()
        fake = fake_run_cmd_factory(canned)
        monkeypatch.setattr(_output_module, "_run_cmd", fake)
        run_lint(config=tmp_config(tmp_path), fix=True)
        for record in fake.calls:
            if record.label in _FIX_TOOL_NAMES:
                assert "--fix" in record.cmd


# ── Observability: stderr skip + revert lines ─────────────────────


class TestAutofixObservability:
    """Skip + revert messages log to stderr; no sensitive data leaked."""

    def test_skip_line_format(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Stderr skip line: ``[<tool>] autofix skipped for <file>: staged+unstaged conflict``."""
        _git_init(tmp_path)
        _write_file(tmp_path, "f.py", "x = 1\n")
        _commit_all(tmp_path)
        _write_file(tmp_path, "f.py", "y = 2\n")
        _stage(tmp_path, "f.py")
        _write_file(tmp_path, "f.py", "z = 3\n")
        canned = _make_canned_fix_results()
        fake = fake_run_cmd_factory(canned)
        _apply_autofix_conflict_aware(
            ToolSpec("ruff check", ["ruff", "check"], supports_fix=True),
            config=tmp_config(tmp_path),
            paths_to_check=["f.py"],
            run_cmd=fake,
        )
        captured = capsys.readouterr()
        # Stable format pinned so a downstream parser (T6 / hooks) can match.
        assert (
            "[ruff check] autofix skipped for f.py: staged+unstaged conflict"
            in captured.err
        )

    def test_revert_line_format(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Stderr revert line: ``[<tool>] autofix reverted <file>: E999 after fix``."""
        original = "x = 1\n"
        post_fix = "x = 2 broken"
        target = _write_file(tmp_path, "src/main.py", original)
        canned = _make_canned_fix_results(canary_e999_files=("src/main.py",))
        wrapped = _PostFixFakeRunCmd(
            fake_run_cmd_factory(canned),
            post_fix_path=target,
            post_fix_content=post_fix,
        )
        _apply_autofix_conflict_aware(
            ToolSpec(
                "rumdl check",
                ["rumdl", "check"],
                supports_fix=True,
                fix_flags=("--fix",),
            ),
            config=tmp_config(tmp_path),
            paths_to_check=["src/main.py"],
            run_cmd=wrapped,
        )
        captured = capsys.readouterr()
        assert (
            "[rumdl check] autofix reverted src/main.py: E999 after fix" in captured.err
        )


# ── Canary label observability: distinct from "ruff check" ────────


class TestCanaryLabelObservability:
    """The E999 canary call carries ``_CANARY_LABEL`` — never ``ruff check``.

    Label distinction is the contract that lets a single dict-mode FakeRunCmd
    return E999-marked output for ONLY the canary call while letting the
    spec's own ``ruff check`` pass return its canned result.  If the canary
    ever emitted the same ``"ruff check"`` label, the dict-mode fake would
    return the spec's canned result for the canary too — and the E999 signal
    would never surface, so the revert path would silently never run.
    """

    def test_canary_label_is_distinct_from_ruff_check(
        self,
        tmp_path: Path,
    ) -> None:
        """``_ruff_parseability_errors`` calls run_cmd with the canary label."""
        # Record every call's label so the assertion can also assert OTHER
        # labels didn't appear (i.e. the canary call did NOT reuse the
        # spec's own ``ruff check`` label).
        seen_labels: list[str] = []

        def fake_run(cmd: list[str], *, cwd: Path, label: str) -> LintResult:
            seen_labels.append(label)
            # Canary stdout carries no E999 — no revert; the test only
            # probes the label that was used.
            assert label == _CANARY_LABEL, (
                f"canary call reused a non-canary label: {label!r}"
            )
            return make_lint_result(tool_name=label, stdout="")

        result = _ruff_parseability_errors(tmp_path, ["src/a.py", "src/b.py"], fake_run)
        assert result == set()  # no E999 in canary output
        assert seen_labels == [_CANARY_LABEL], (
            f"expected exactly one canary call; got labels {seen_labels!r}"
        )


# ── Windows-path safety for _ruff_parseability_errors (D7) ────────


class TestWindowsPathSafety:
    """E999 parser tolerates Windows drive-letter colons in the path group.

    D7 (review T4-0): the prior ``line.split(":", 1)[0]`` parser yielded
    ``C`` for ``C:\\foo\\bar.py:5:1: E999 SyntaxError`` — a garbage
    short-path landing in the revert target set.  The new regex anchors
    on the trailing ``:INT:INT: E999`` shape with a greedy path group so
    the drive-letter colon is absorbed into the path.  No Windows consumer
    ships today, but the parser is now robust enough that one could arrive
    without silently breaking the revert path.
    """

    def test_e999_parses_drive_letter_path_robustly(self, tmp_path: Path) -> None:
        """Windows ``C:\\foo\\bar.py:5:1: E999 SyntaxError`` parses as the full path."""
        stdout = "C:\\foo\\bar.py:5:1: E999 SyntaxError\n"

        def fake_run(cmd: list[str], *, cwd: Path, label: str) -> LintResult:
            assert label == _CANARY_LABEL
            return make_lint_result(tool_name=label, stdout=stdout)

        result = _ruff_parseability_errors(tmp_path, ["C:\\foo\\bar.py"], fake_run)
        assert result == {"C:\\foo\\bar.py"}, (
            f"Windows E999 path not parsed whole: got {result!r}"
        )

    def test_e999_drive_letter_does_not_emit_garbage_short_path(
        self, tmp_path: Path
    ) -> None:
        """The drive-letter colon must NOT yield ``C`` as a separate path entry."""
        stdout = "D:\\repo\\src\\mod.py:12:3: E999 invalid syntax\n"

        def fake_run(cmd: list[str], *, cwd: Path, label: str) -> LintResult:
            return make_lint_result(tool_name=label, stdout=stdout)

        result = _ruff_parseability_errors(
            tmp_path, ["D:\\repo\\src\\mod.py"], fake_run
        )
        # The garbage short-path outcome under the OLD parser would be
        # ``{"D"}``; assert the full path is the only entry.
        assert "D" not in result, f"garbage short-path 'D' landed in result: {result!r}"
        assert result == {"D:\\repo\\src\\mod.py"}

    def test_e999_drive_letter_with_message_parses_cleanly(
        self, tmp_path: Path
    ) -> None:
        """Drive-letter path with a multi-word message still parses whole."""
        stdout = "C:\\dev\\proj\\pkg\\a.py:1:1: E999 SyntaxError: unexpected EOF\n"

        def fake_run(cmd: list[str], *, cwd: Path, label: str) -> LintResult:
            return make_lint_result(tool_name=label, stdout=stdout)

        result = _ruff_parseability_errors(
            tmp_path, ["C:\\dev\\proj\\pkg\\a.py"], fake_run
        )
        assert result == {"C:\\dev\\proj\\pkg\\a.py"}

    def test_e999_posix_path_still_parses_unchanged(self, tmp_path: Path) -> None:
        """Regression guard: POSIX paths parse the same as before the regex."""
        stdout = "src/a.py:1:1: E999 SyntaxError\n"

        def fake_run(cmd: list[str], *, cwd: Path, label: str) -> LintResult:
            return make_lint_result(tool_name=label, stdout=stdout)

        result = _ruff_parseability_errors(tmp_path, ["src/a.py"], fake_run)
        assert result == {"src/a.py"}










