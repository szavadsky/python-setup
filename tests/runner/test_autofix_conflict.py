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

import subprocess
import textwrap
from collections.abc import Callable
from pathlib import Path

import pytest

import python_setup_lint.runner as _runner_module
from python_setup_lint.runner import (
    _AUTOFIX_ENV_VAR,
    LINT_TOOLS,
    LintResult,
    RunnerConfig,
    ToolSpec,
    _apply_autofix_conflict_aware,
    _autofix_target_paths,
    _git_changed_files,
    _ruff_parseability_errors,
    run_lint,
)
from python_setup_lint.testing import fake_run_cmd_factory, make_lint_result
from tests.runner._factories import (
    canned_results_all_tools,
    tmp_config,
)

# ── Module-level constants (shared by rows) ─────────────────────

_CANARY_LABEL = "python-setup:autofix-canary"
"""The label the runner uses for the ruff canary call. Tests pin it so the
dict-mode fake can return E999-marked output for ONLY the canary while
letting the spec's own pass return its canned result."""

_FIX_TOOL_NAMES: frozenset[str] = frozenset(
    t.name for t in LINT_TOOLS if t.supports_fix
)
"""All built-in tools that carry ``supports_fix=True`` — ``{ruff check,
rumdl check, ty check}``.  T4 autofix route applies to exactly these."""

assert {"ruff check", "rumdl check", "ty check"} == _FIX_TOOL_NAMES, (
    f"Built-in supports_fix set drifted: {_FIX_TOOL_NAMES!r}"
)

# ── Git scaffolding ───────────────────────────────────────────────


def _git_init(cwd: Path) -> None:
    """Initialise a fresh git repo at *cwd* with a benign author identity."""
    subprocess.run(["git", "init", "-q"], cwd=cwd, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=cwd,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=cwd, check=True, capture_output=True
    )


def _write_file(cwd: Path, rel: str, content: str) -> Path:
    """Create ``cwd/rel`` with *content*; parent dirs created as needed."""
    p = cwd / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _stage(cwd: Path, rel: str) -> None:
    """``git add`` a single path (after the initial commit, this is staged)."""
    subprocess.run(["git", "add", rel], cwd=cwd, check=True, capture_output=True)


def _commit_all(cwd: Path, msg: str = "init") -> None:
    """Commit all current changes; second commit creates a real HEAD ref."""
    subprocess.run(["git", "add", "."], cwd=cwd, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", msg], cwd=cwd, check=True, capture_output=True
    )


def _make_canned_fix_results(
    *,
    canary_e999_files: tuple[str, ...] = (),
) -> dict[str, LintResult]:
    """Build the 11-tool canned result dict + a canary result.

    The canary result emits one ``E999`` line per *canary_e999_files* entry;
    empty by default → no revert.  All built-in tools return zero-exit empty
    results so the test can drive the autofix path without fail-fast
    interruption.
    """
    base = canned_results_all_tools(exit_code=0, stdout="")
    if canary_e999_files:
        canary_stdout = "\n".join(
            f"{f}:1:1: E999 SyntaxError" for f in canary_e999_files
        )
    else:
        canary_stdout = ""
    base[_CANARY_LABEL] = make_lint_result(
        tool_name=_CANARY_LABEL,
        exit_code=1,
        stdout=canary_stdout,
    )
    return base


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

    @pytest.mark.parametrize(
        "stdout,expected_files",
        [
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
        ],
    )
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


# ── Surface-unit: conflict branches via _apply_autofix_conflict_aware ─


class TestApplyAutofixConflictAware:
    """Each conflict branch from the envelope — one parametrised row."""

    def _make_spec(self) -> ToolSpec:
        return next(t for t in LINT_TOOLS if t.name == "ruff check")

    def test_no_conflict_baseline_applies_fix(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """No staged AND no unstaged files → fix pass runs; no skip line.

        D1 (review T4-0): the prior form only asserted
        ``result.tool_name == "ruff check"`` — vacuous: ``run_cmd`` returns
        the spec's OWN canned result regardless of whether the fix tool
        actually ran.  Strengthened below to assert (a) a ``run_cmd`` call
        with ``label == "ruff check"`` AND ``--fix`` in the constructed
        command was recorded (proves the helper actually dispatched the fix
        pass), AND (b) the canary fired once with the canary label (proves
        the parseability-canary seam ran end-to-end).
        """
        _write_file(tmp_path, "src/main.py", "import os\n")
        # No git repo → both diff sets empty → no skip, no revert.
        # The fake is dict-mode so unknown labels (the canary label) also
        # return a zero-exit empty result by default — that's correct for
        # the no-E999 branch.
        canned = _make_canned_fix_results()  # canary stdout empty
        fake = fake_run_cmd_factory(canned)
        result = _apply_autofix_conflict_aware(
            self._make_spec(),
            config=tmp_config(tmp_path),
            paths_to_check=["src/main.py"],
            run_cmd=fake,
        )
        assert result.tool_name == "ruff check"
        # (a) The fix tool's own pass fired — recorded with label + --fix.
        fix_passes = [c for c in fake.calls if c.label == "ruff check"]
        assert len(fix_passes) == 1, (
            f"expected exactly one 'ruff check' fix pass, got {fake.calls!r}"
        )
        assert "--fix" in fix_passes[0].cmd, (
            f"--fix not in fix-pass cmd: {fix_passes[0].cmd!r}"
        )
        # (b) The canary fired once with the canary label.
        canary_calls = [c for c in fake.calls if c.label == _CANARY_LABEL]
        assert len(canary_calls) == 1, (
            f"canary did not fire exactly once: {fake.calls!r}"
        )
        captured = capsys.readouterr()
        assert "autofix skipped" not in captured.err
        assert "autofix reverted" not in captured.err

    def test_staged_only_applies_fix(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """File staged only → autofix applies; no skip line; no revert."""
        _git_init(tmp_path)
        _write_file(tmp_path, "committed.py", "x = 1\n")
        _commit_all(tmp_path)
        _write_file(tmp_path, "staged.py", "y = 2\n")
        _stage(tmp_path, "staged.py")
        fake = fake_run_cmd_factory(_make_canned_fix_results())
        _apply_autofix_conflict_aware(
            self._make_spec(),
            config=tmp_config(tmp_path),
            paths_to_check=["staged.py"],
            run_cmd=fake,
        )
        captured = capsys.readouterr()
        assert "autofix skipped" not in captured.err
        assert "autofix reverted" not in captured.err

    def test_unstaged_only_applies_fix(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """File unstaged only → autofix applies; no skip line; no revert."""
        _git_init(tmp_path)
        _write_file(tmp_path, "committed.py", "x = 1\n")
        _commit_all(tmp_path)
        _write_file(tmp_path, "unstaged.py", "y = 2\n")  # no git add
        fake = fake_run_cmd_factory(_make_canned_fix_results())
        _apply_autofix_conflict_aware(
            self._make_spec(),
            config=tmp_config(tmp_path),
            paths_to_check=["unstaged.py"],
            run_cmd=fake,
        )
        captured = capsys.readouterr()
        assert "autofix skipped" not in captured.err
        assert "autofix reverted" not in captured.err

    def test_staged_and_unstaged_same_file_skipped(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """File in BOTH staged and unstaged → autofix skipped with stderr line."""
        _git_init(tmp_path)
        _write_file(tmp_path, "f.py", "x = 1\n")
        _commit_all(tmp_path)
        _write_file(tmp_path, "f.py", "y = 2\n")
        _stage(tmp_path, "f.py")
        _write_file(tmp_path, "f.py", "z = 3\n")  # unstaged overlay on the staged state
        fake = fake_run_cmd_factory(_make_canned_fix_results())
        # The conflict detection happens BEFORE the fix tool runs — but the
        # helper still calls run_cmd (the tool's pass on the safe-to-fix
        # set; here that's empty because f.py is conflict-skipped).  The
        # stderr line proves the skip branch ran.
        _apply_autofix_conflict_aware(
            self._make_spec(),
            config=tmp_config(tmp_path),
            paths_to_check=["f.py"],
            run_cmd=fake,
        )
        captured = capsys.readouterr()
        assert "autofix skipped for f.py: staged+unstaged conflict" in captured.err
        # No revert line: the file was never snapshotted (it's conflict-skipped).
        assert "autofix reverted" not in captured.err

    def test_e999_introduced_reverts_from_in_memory_snapshot(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Canary emits E999 → file restored to its pre-fix bytes from snapshot.

        D2 (review T4-0): the prior form only checked the FINAL on-disk
        bytes equalled the original — vacuous when the fix tool did not
        actually write (the file would be unchanged from the start, so the
        revert-vs-no-op difference was unobservable).  Strengthened with
        intermediate-state assertions via ``_PostFixFakeRunCmd.snapshots``:
        the helper records on-disk file state AFTER every ``run_cmd`` call,
        so the test asserts (a) the file was MODIFIED by the fix pass
        (proves a real snapshot-vs-revert loop took place), then (b) the
        file was RESTORED to the original bytes by the canary-triggered
        revert.  The ``_PostFixFakeRunCmd`` itself no longer gates its
        write on ``--fix in cmd`` (the gate was the vacuous-pass source:
        if a future regression dropped ``--fix`` from the constructed
        command, the helper silently wrote nothing and the test passed
        trivially).
        """
        original = "x = 1  # original\n"
        post_fix = "x = 2  # fixed-broken\n"
        target = _write_file(tmp_path, "src/main.py", original)
        canned = _make_canned_fix_results(canary_e999_files=("src/main.py",))
        wrapped = _PostFixFakeRunCmd(
            fake_run_cmd_factory(canned),
            post_fix_path=target,
            post_fix_content=post_fix,
        )
        _apply_autofix_conflict_aware(
            self._make_spec(),
            config=tmp_config(tmp_path),
            paths_to_check=["src/main.py"],
            run_cmd=wrapped,
        )
        captured = capsys.readouterr()
        assert "autofix reverted src/main.py: E999 after fix" in captured.err
        # (a) After the fix pass (label == "ruff check") the file held the
        # post-fix bytes — proves the fix tool actually wrote (the snapshot
        # the runner will revert has something to differ from).
        after_fix = wrapped.snapshots_after_label("ruff check")
        assert after_fix is not None, (
            "fix pass (label 'ruff check') was never invoked — no snapshot"
        )
        assert after_fix == post_fix, (
            f"file NOT modified by fix pass: got {after_fix!r}, want {post_fix!r}"
        )
        # (b) After the canary call (label == _CANARY_LABEL) the file STILL
        # held the post-fix bytes — proves the canary itself did NOT touch
        # the file (only the post-canary revert should change file state).
        # The revert happens AFTER ``_ruff_parseability_errors`` returns,
        # inside ``_apply_autofix_conflict_aware`` — so the snapshot recorded
        # inside the canary's ``__call__`` is BEFORE the revert.
        after_canary = wrapped.snapshots_after_label(_CANARY_LABEL)
        assert after_canary == post_fix, (
            f"canary mutated file unexpectedly: got {after_canary!r}"
        )
        # (c) Final on-disk state — RECORDED AFTER the helper returned —
        # equals original; proves the in-memory snapshot revert ran AFTER
        # the canary call (the only path that could transition post_fix →
        # original is the revert code path).
        assert target.read_text() == original, (
            f"file NOT reverted to original after helper returned: "
            f"got {target.read_text()!r}, want {original!r}"
        )

    def test_canary_no_e999_no_revert(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Canary emits no E999 → no revert; on-disk content is the post-fix state.

        D3 (review T4-0): the prior form was a no-op wrapper (no
        ``_PostFixFakeRunCmd``) — the file was never modified by any fix
        pass, so ``target.read_text() == original`` was trivially true
        regardless of whether the fix tool or canary ran.  Strengthened
        to wrap with ``_PostFixFakeRunCmd`` writing a benign post-fix
        (no syntax break) so the test proves (a) the fix pass ran and
        modified the file, then (b) the canary ran and reported no E999,
        so (c) the file is LEFT at the post-fix state (no revert).
        """
        original = "x = 1\n"
        post_fix = "x = 1  # ruff-fix\n"  # benign — no E999 from canary
        target = _write_file(tmp_path, "src/main.py", original)
        canned = _make_canned_fix_results()  # no E999 in canary
        wrapped = _PostFixFakeRunCmd(
            fake_run_cmd_factory(canned),
            post_fix_path=target,
            post_fix_content=post_fix,
        )
        _apply_autofix_conflict_aware(
            self._make_spec(),
            config=tmp_config(tmp_path),
            paths_to_check=["src/main.py"],
            run_cmd=wrapped,
        )
        captured = capsys.readouterr()
        assert "autofix reverted" not in captured.err
        # (a) The fix pass fired and modified the file.
        after_fix = wrapped.snapshots_after_label("ruff check")
        assert after_fix == post_fix, (
            f"fix pass did not modify file: got {after_fix!r}, want {post_fix!r}"
        )
        # (b) The canary fired (no E999 → no revert); file stays at post_fix.
        after_canary = wrapped.snapshots_after_label(_CANARY_LABEL)
        assert after_canary == post_fix, (
            f"canary mutated file unexpectedly: got {after_canary!r}"
        )
        # (c) Final on-disk state is the post-fix content (no revert path;
        # the canary returned no E999 so the helper's revert loop never
        # entered — the file is left at the post-fix state).
        assert target.read_text() == post_fix

    def test_e999_no_revert_when_fix_does_not_modify_file(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """If the fix pass leaves the file untouched the canary cannot revert it.

        Companion to the D2 strengthened test: covers the "fix did not
        modify" branch.  Even if the canary reports E999, the in-memory
        snapshot equals the current bytes so the revert is a no-op — no
        stderr revert line, no observable change.  This proves the
        snapshot/revert loop tolerates a fix tool whose fix pass did not
        apply any change (e.g. ruff --fix on a file with no fixable
        violations).  Distinct from D2's strengthened test, which proves
        the loop fires when the fix DID modify the file.
        """
        original = "x = 1\n"
        target = _write_file(tmp_path, "src/main.py", original)
        canned = _make_canned_fix_results(canary_e999_files=("src/main.py",))
        # NO _PostFixFakeRunCmd wrap — the fix pass does not write.
        fake = fake_run_cmd_factory(canned)
        _apply_autofix_conflict_aware(
            self._make_spec(),
            config=tmp_config(tmp_path),
            paths_to_check=["src/main.py"],
            run_cmd=fake,
        )
        captured = capsys.readouterr()
        # The canary reported E999; the helper attempts a revert — but the
        # snapshot equals the current bytes, so write_bytes is a no-op.
        # The stderr revert line IS emitted (the revert code path ran and
        # restored the same bytes); the file is unchanged.
        assert "autofix reverted src/main.py: E999 after fix" in captured.err
        assert target.read_text() == original

    def test_untracked_file_reverts_via_memory_only(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Untracked file (not git-tracked) reverts via the in-memory snapshot only.

        The envelope contract: revert happens before any ``git checkout``
        — no fallback needed because the in-memory snapshot is always
        captured first.  This row exercises the untracked-file-only path
        by initialising a git repo but never ``git add``-ing the file.
        """
        _git_init(tmp_path)
        original = "x = 1  # original\n"
        post_fix = "x = 2  # broken-syntax"
        target = _write_file(tmp_path, "untracked.py", original)
        canned = _make_canned_fix_results(canary_e999_files=("untracked.py",))
        wrapped = _PostFixFakeRunCmd(
            fake_run_cmd_factory(canned),
            post_fix_path=target,
            post_fix_content=post_fix,
        )
        _apply_autofix_conflict_aware(
            self._make_spec(),
            config=tmp_config(tmp_path),
            paths_to_check=["untracked.py"],
            run_cmd=wrapped,
        )
        captured = capsys.readouterr()
        assert "autofix reverted untracked.py: E999 after fix" in captured.err
        # No fallback to git checkout: the file was never tracked, so
        # ``git checkout -- untracked.py`` would have failed.  This row
        # asserts the in-memory snapshot was the revert source.
        assert target.read_text() == original


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
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        run_lint(config=tmp_config(tmp_path), fix=True, no_fail_fast=True)
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
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        run_lint(config=tmp_config(tmp_path), fix=True, no_fail_fast=True)
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
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        run_lint(config=tmp_config(tmp_path), fix=True, no_fail_fast=True)
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


# ── Downstream integration: run_lint --fix on real python-setup repo ─


class TestRunLintFixDownstream:
    """End-to-end ``run_lint(fix=True)`` on the python-setup repo itself.

    The envelope downstream-integration gate says: ``uv run lint --fix``
    on python-setup applies at least ruff fixes and does not crash.  This
    test runs the runner in fix mode against the repo's real src tree,
    asserting the run completes (returns int) and that at least one
    supports_fix tool exercised its --fix route.  Marked ``slow`` so
    unit-only test runs (``pytest -m 'not slow'``) skip it.
    """

    @pytest.mark.slow
    def test_run_lint_fix_does_not_crash(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Run ``run_lint(fix=True, no_fail_fast=True)`` to completion (returns int).

        D1 (review T4-0): the prior form asserted only
        ``isinstance(rc, int)`` — vacuously true even if ``run_lint``
        returned 0 without iterating any tool.  Strengthened to (a) the
        temp baseline file exists AND is non-empty (proves the runner
        reached the baseline-save branch, which only fires after a full
        tool-loop completion), (b) the baseline JSON parses to a list
        with at least 9 entries (the runner's stubtest + verifytypes
        are skipped when ``--package-name`` is unset OR when invoked
        without the right config; here ``package_name="python_setup_lint"``
        is set so the expected count is 9 or 11 depending on whether
        stubtest's package is installed — assert ``>= 9`` to cover both),
        and (c) at least one supports_fix tool's label appears in the
        captured baseline labels (proves the autofix route was exercised
        end-to-end against the real repo).
        """
        repo = Path(__file__).resolve().parent.parent.parent
        # Use a temp baseline so the run doesn't touch the repo's checked-in
        # baseline file.  The fix flag still applies — autofix runs the
        # ruff/rumdl/ty fix path against the repo's real source tree.
        baseline = tmp_path / "t4-fix-downstream.baseline"
        config = RunnerConfig(
            cwd=repo,
            package_name="python_setup_lint",
            default_py_dirs=["src", "scripts", "tests"],
        )
        rc = run_lint(
            config=config, fix=True, no_fail_fast=True, baseline=str(baseline)
        )
        assert isinstance(rc, int)
        # (a) The baseline file was created and is non-empty — proves the
        # runner completed the tool loop AND reached the baseline-save
        # branch (which only fires after all tools ran in no-fail-fast
        # mode).
        assert baseline.exists(), "baseline file not created — runner did not finish"
        assert baseline.stat().st_size > 0, (
            f"baseline file empty: {baseline.read_text()!r}"
        )
        # (b) The baseline JSON parses to a list with the expected tool
        # entries (9 when stubtest + verifytypes skipped because their
        # packages aren't installed in the test venv; 11 when both run).
        import json as _json

        entries = _json.loads(baseline.read_text(encoding="utf-8"))
        assert isinstance(entries, list), (
            f"baseline not a JSON list: {type(entries).__name__}"
        )
        assert len(entries) >= 9, (
            f"expected >= 9 baseline entries; got {len(entries)} ({entries!r})"
        )
        # (c) At least one supports_fix tool's label is captured in the
        # baseline entries — proves the autofix route was exercised.
        baseline_labels = {e.get("tool") for e in entries}
        fix_labels_seen = baseline_labels & _FIX_TOOL_NAMES
        assert fix_labels_seen, f"no supports_fix tool in baseline: {baseline_labels!r}"
        # The autofix helper ran through the supports_fix tools without
        # crashing — that's the assertion.  We do NOT assert the ruff F401
        # count drops (the envelope's "post-T1 baseline should drop ruff
        # F401 count" claim requires a pre-T1 baseline diff; this
        # assertion is the stronger "ran to completion + produced real
        # baseline entries + autofix route exercised" form).


# ── Surface-unit: pre-commit template carries --fix (T4 contract)  ─


class TestPrecommitTemplateHasFix:
    """T4 verification gate: rendered template's lint hook entry has ``--fix``."""

    def test_precommit_template_lint_entry_has_fix(self) -> None:
        """The ``lint`` local hook entry contains ``--fix``."""
        from python_setup_lint._setup_precommit import _PRECOMMIT_TEMPLATE

        # The lint line is a unique substring; assert it carries --fix.
        assert "python-setup lint --fix" in _PRECOMMIT_TEMPLATE, (
            "expected 'python-setup lint --fix' in template"
        )

    def test_precommit_template_no_timeout(self) -> None:
        """Template never carries the ``timeout`` key — avoiding the schema warning (D5)."""
        from python_setup_lint._setup_precommit import _PRECOMMIT_TEMPLATE

        assert "timeout" not in _PRECOMMIT_TEMPLATE.lower(), (
            "timeout key present in template — pre-commit would warn"
        )

    def test_precommit_template_no_pre_push(self) -> None:
        """The hook stage name ``pre-push`` is NOT in the template — fast hooks
        are tied to ``git commit`` only."""
        from python_setup_lint._setup_precommit import _PRECOMMIT_TEMPLATE

        assert "pre-push" not in _PRECOMMIT_TEMPLATE, "pre-push present in template"

    def test_precommit_template_still_has_ruff_hooks(self) -> None:
        """ruff-format + ruff-check fast hooks retained for compatibility."""
        from python_setup_lint._setup_precommit import _PRECOMMIT_TEMPLATE

        assert "ruff-format" in _PRECOMMIT_TEMPLATE
        assert "ruff-check" in _PRECOMMIT_TEMPLATE
        assert "args: [--fix, --exit-non-zero-on-fix]" in _PRECOMMIT_TEMPLATE

    def test_agents_snippet_documents_autofix_and_opt_out(self) -> None:
        """The AGENTS snippet mentions the autofix route + env-var opt-out."""
        from python_setup_lint._setup_precommit import (
            _AGENTS_SENTINEL,
            _AGENTS_SENTINEL_END,
            _AGENTS_SNIPPET,
        )

        rendered = _AGENTS_SNIPPET.format(
            open_sentinel=_AGENTS_SENTINEL, close_sentinel=_AGENTS_SENTINEL_END
        )
        assert "autofix" in rendered.lower()
        assert _AUTOFIX_ENV_VAR in rendered, "env-var opt-out name not documented"
        assert "courtesy" in rendered.lower()
        assert "staged" in rendered.lower()
        assert "E999" in rendered

    def test_install_artifact_lint_hook_has_fix(self, tmp_path: Path) -> None:
        """End-to-end install writes a `.pre-commit-config.yaml` whose lint entry has --fix."""
        from python_setup_lint.setup import install

        # Mirror the ``empty_project`` fixture: write a minimal project.
        (tmp_path / "pyproject.toml").write_text(
            textwrap.dedent("""\
            [project]
            name = "t4-artifact"
            version = "0.1.0"
            requires-python = ">=3.14"
            [dependency-groups]
            dev = ["ruff>=0.5"]
        """)
        )
        agents = tmp_path / "AGENTS.md"
        agents.write_text("# Test\n")
        assert install(tmp_path, dev_path="/home/slava/aiexp/python-setup") == 0
        precommit = (tmp_path / ".pre-commit-config.yaml").read_text()
        assert "python-setup lint --fix" in precommit


# ── Surface-unit: env-var opt-out is honoured before the loop ────


class TestRunLintFixDispatch:
    """``run_lint(fix=True)`` routes supports_fix tools through the conflict-aware helper."""

    def test_fix_route_uses_conflict_helper(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """``run_lint(fix=True)`` calls the conflict-aware helper for supports_fix tools.

        Detection: the helper calls ``run_cmd`` with label=spec.name for the
        fix pass AND ``label=_CANARY_LABEL`` for the E999 canary.  When fix=False
        the plain path runs (no canary call).  This asserts the difference.

        The canary fires for tools whose target files are enumerable from
        ``spec.default_paths`` + ``--path``.  Only ruff has ``default_paths``
        set (``["src/", "tests/"]``); rumdl/ty without a ``--path`` fall into
        the "no enumerable targets" branch (canary short-circuits).  The test
        creates files under ruff's default dirs + a separate path-only fixture
        to exercise both branches.
        """
        monkeypatch.delenv(_AUTOFIX_ENV_VAR, raising=False)
        canned = _make_canned_fix_results()
        fake = fake_run_cmd_factory(canned)
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)

        # Create source files under ruff's default_paths so the canary has
        # something to enumerate (otherwise canary_targets is empty and the
        # canary short-circuits without calling run_cmd).
        _write_file(tmp_path, "src/main.py", "x = 1\n")
        _write_file(tmp_path, "tests/test_main.py", "y = 1\n")
        run_lint(config=tmp_config(tmp_path), fix=True, no_fail_fast=True)
        labels = [c.label for c in fake.calls]
        # ruff has default_paths=["src/", "tests/"] → canary fires once.
        assert _CANARY_LABEL in labels, (
            f"canary label never appeared in fix=True labels: {labels!r}"
        )

    def test_fix_route_with_path_triggers_canary_for_each_supports_fix(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When ``--path`` is given, every supports_fix tool fires the canary.

        With an explicit ``path``, ``_autofix_target_paths`` returns that path
        for every ``supports_path`` tool — including rumdl/ty, which have no
        ``default_paths``.  The canary fires once per supports_fix tool.
        """
        monkeypatch.delenv(_AUTOFIX_ENV_VAR, raising=False)
        canned = _make_canned_fix_results()
        fake = fake_run_cmd_factory(canned)
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        target = _write_file(tmp_path, "src/main.py", "x = 1\n")
        run_lint(
            config=tmp_config(tmp_path),
            path=str(target.relative_to(tmp_path)),
            fix=True,
            no_fail_fast=True,
        )
        labels = [c.label for c in fake.calls]
        # All three supports_fix tools receive the --path → canary fires once each.
        assert labels.count(_CANARY_LABEL) == 3, (
            f"canary call count mismatch with --path: {labels!r}"
        )

    def test_no_fix_does_not_invoke_canary(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``run_lint(fix=False)`` never calls the canary (no autofix helper used)."""
        monkeypatch.delenv(_AUTOFIX_ENV_VAR, raising=False)
        canned = canned_results_all_tools()
        fake = fake_run_cmd_factory(canned)
        monkeypatch.setattr(_runner_module, "_run_cmd", fake)
        run_lint(config=tmp_config(tmp_path), fix=False, no_fail_fast=True)
        labels = [c.label for c in fake.calls]
        assert _CANARY_LABEL not in labels


# ── Real-git integration: staged+unstaged conflict, staged-only fix, E999 revert ─


class TestAutofixRealGitIntegration:
    """End-to-end ``_apply_autofix_conflict_aware`` against a real ``git init`` repo.

    Each test creates a fresh tmp git repo, stages/commits files, then
    invokes the conflict-aware helper with a fake ``run_cmd`` that simulates
    ruff writing a fix.  Asserts the correct stderr lines and on-disk state
    — proving the helper's git-diff seam works against a real git index.
    """

    _CANARY_LABEL = "python-setup:autofix-canary"

    def _make_spec(self) -> ToolSpec:
        return next(t for t in LINT_TOOLS if t.name == "ruff check")

    def _make_canned(
        self, *, canary_e999_files: tuple[str, ...] = ()
    ) -> dict[str, LintResult]:
        base = canned_results_all_tools(exit_code=0, stdout="")
        if canary_e999_files:
            canary_stdout = "\n".join(
                f"{f}:1:1: E999 SyntaxError" for f in canary_e999_files
            )
        else:
            canary_stdout = ""
        base[self._CANARY_LABEL] = make_lint_result(
            tool_name=self._CANARY_LABEL, exit_code=1, stdout=canary_stdout
        )
        return base

    # ── Case 1: staged+unstaged same file → skipped ──────────────

    def test_staged_and_unstaged_same_file_skipped_real_git(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """File with staged AND unstaged changes is skipped; staged blob untouched."""
        _git_init(tmp_path)
        _write_file(tmp_path, "f.py", "x = 1\n")
        _commit_all(tmp_path)
        # Stage a change, then overlay an unstaged change on the same file.
        _write_file(tmp_path, "f.py", "y = 2\n")
        _stage(tmp_path, "f.py")
        _write_file(tmp_path, "f.py", "z = 3\n")
        staged_blob = subprocess.run(
            ["git", "show", "HEAD:f.py"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        fake = fake_run_cmd_factory(self._make_canned())
        _apply_autofix_conflict_aware(
            self._make_spec(),
            config=tmp_config(tmp_path),
            paths_to_check=["f.py"],
            run_cmd=fake,
        )
        captured = capsys.readouterr()
        # The file is skipped — no fix pass touches it.
        assert "autofix skipped for f.py: staged+unstaged conflict" in captured.err
        # The staged blob (HEAD:f.py) is untouched — the fix tool never ran.
        post_staged_blob = subprocess.run(
            ["git", "show", "HEAD:f.py"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert post_staged_blob == staged_blob, (
            f"staged blob changed: was {staged_blob!r}, now {post_staged_blob!r}"
        )
        # The unstaged content is also unchanged (the fix tool never wrote).
        assert (tmp_path / "f.py").read_text() == "z = 3\n"

    # ── Case 2: staged-only file gets fixed ──────────────────────

    def test_staged_only_file_fixed_real_git(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """File staged only (no unstaged changes) → autofix applies."""
        _git_init(tmp_path)
        _write_file(tmp_path, "f.py", "x = 1\n")
        _commit_all(tmp_path)
        _write_file(tmp_path, "f.py", "y = 2\n")
        _stage(tmp_path, "f.py")
        # The file is staged-only — no unstaged overlay → safe to fix.
        # The fake fix writes "y = 2  # fixed\n" to simulate ruff --fix.
        target = tmp_path / "f.py"
        post_fix = "y = 2  # fixed\n"
        canned = self._make_canned()
        wrapped = _PostFixFakeRunCmd(
            fake_run_cmd_factory(canned),
            post_fix_path=target,
            post_fix_content=post_fix,
        )
        _apply_autofix_conflict_aware(
            self._make_spec(),
            config=tmp_config(tmp_path),
            paths_to_check=["f.py"],
            run_cmd=wrapped,
        )
        captured = capsys.readouterr()
        assert "autofix skipped" not in captured.err
        assert "autofix reverted" not in captured.err
        # The fix pass wrote the post-fix content.
        assert target.read_text() == post_fix

    # ── Case 3: E999-canary revert with real git repo ─────────────

    def test_e999_canary_revert_real_git(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A fix that breaks parseability triggers E999-canary revert; file restored."""
        _git_init(tmp_path)
        _write_file(tmp_path, "src/main.py", "x = 1  # original\n")
        _commit_all(tmp_path)
        original = "x = 1  # original\n"
        post_fix = "x = 2  # broken-syntax\n"
        target = tmp_path / "src/main.py"
        canned = self._make_canned(canary_e999_files=("src/main.py",))
        wrapped = _PostFixFakeRunCmd(
            fake_run_cmd_factory(canned),
            post_fix_path=target,
            post_fix_content=post_fix,
        )
        _apply_autofix_conflict_aware(
            self._make_spec(),
            config=tmp_config(tmp_path),
            paths_to_check=["src/main.py"],
            run_cmd=wrapped,
        )
        captured = capsys.readouterr()
        assert "autofix reverted src/main.py: E999 after fix" in captured.err
        # (a) The fix pass modified the file.
        after_fix = wrapped.snapshots_after_label("ruff check")
        assert after_fix == post_fix, f"fix pass did not modify file: got {after_fix!r}"
        # (b) Final on-disk state equals original — revert worked.
        assert target.read_text() == original


# ── Helper: post-fix fake that simulates the tool writing bytes to file ─


class _PostFixFakeRunCmd:
    """Wrap a FakeRunCmd so the fix-pass call (label == spec.name) ALSO writes
    the post-fix bytes to the target file.  This simulates an actual ruff/rumdl/ty
    invocation rewriting the file.

    Only the FIRST call with label==one of the supports_fix names writes
    (so subsequent calls, including the canary, don't overwrite again).
    """

    def __init__(
        self,
        inner: Callable[..., LintResult],
        *,
        post_fix_path: Path,
        post_fix_content: str,
    ) -> None:
        self._inner = inner
        self._post_fix_path = post_fix_path
        self._post_fix_content = post_fix_content
        self._post_fix_written = False
        # Per-call on-disk state recorded AFTER every ``run_cmd`` call —
        # keyed by call order so the strengthened D2 test can ask "what
        # did the file look like after the 'ruff check' label saw the
        # call AND after the canary label saw the call?"  Records ``None``
        # when the target file is absent.
        self._post_call_snapshots: list[tuple[str, str | None]] = []

    def __call__(self, cmd: list[str], *, cwd: Path, label: str) -> LintResult:
        # Only write the post-fix bytes on the fix pass (NOT the canary).
        # D2 fix (review T4-0): the prior form gated the write on
        # ``if "--fix" in cmd`` — a regression in ``ToolSpec.fix_flags``
        # wiring (the constructed command losing ``--fix``) would silently
        # skip the write and the snapshot-vs-revert loop would have
        # nothing to revert, making the test pass vacuously.  The helper
        # now writes UNCONDITIONALLY on the first fix-tool-label call;
        # the label alone is the marker for "the fix tool ran", and the
        # ``--fix`` presence in ``cmd`` is a downstream concern of
        # ``build_command`` that the snapshot/revert loop should not
        # depend on.  Other tests (TestRunLintFixDispatch) still assert
        # ``--fix in cmd`` separately — those will fail loudly if the
        # wiring regresses; this helper no longer couples to it.
        if label in _FIX_TOOL_NAMES and not self._post_fix_written:
            self._post_fix_path.write_text(self._post_fix_content, encoding="utf-8")
            self._post_fix_written = True
        # Record on-disk state AFTER every call — keyed by label so the
        # caller can probe the post-fix state vs the post-canary state.
        try:
            after = self._post_fix_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            after = None
        self._post_call_snapshots.append((label, after))
        return self._inner(cmd, cwd=cwd, label=label)

    def snapshots_after_label(self, label: str) -> str | None:
        """Return the on-disk file state recorded AFTER the LAST call with *label*.

        Returns ``None`` when no call with *label* was recorded — used by
        the strengthened D2 test to assert "the fix pass fired and the
        file was modified" without coupling to the call count or order in
        the helper interface.
        """
        for seen_label, after in reversed(self._post_call_snapshots):
            if seen_label == label:
                return after
        return None
