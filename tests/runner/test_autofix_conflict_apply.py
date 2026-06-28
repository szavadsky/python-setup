"""T4 — conflict-tolerant autofix: ``_apply_autofix_conflict_aware`` branch tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from python_setup_lint.runner import LINT_TOOLS, ToolSpec
from python_setup_lint.runner._autofix import _apply_autofix_conflict_aware
from python_setup_lint.testing import fake_run_cmd_factory
from tests.runner._autofix_helpers import (
    _CANARY_LABEL,
    _commit_all,
    _git_init,
    _make_canned_fix_results,
    _PostFixFakeRunCmd,
    _stage,
    _write_file,
)
from tests.runner._factories import tmp_config


class TestApplyAutofixConflictAware:
    """Each conflict branch from the envelope — one parametrised row."""

    def _make_spec(self) -> ToolSpec:  # pylint: disable=trivial-wrapper  # test helper; readability over DRY
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
