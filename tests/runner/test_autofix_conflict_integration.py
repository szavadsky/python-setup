"""T4 — conflict-tolerant autofix: integration tests for ``--fix`` route."""

from __future__ import annotations

from pathlib import Path

import pytest

import python_setup_lint.runner.output as _output_module
from python_setup_lint.runner import (
    LINT_TOOLS,
    LintResult,
    ToolSpec,
    run_lint,
)
from python_setup_lint.runner._autofix import (
    _AUTOFIX_ENV_VAR,
    _apply_autofix_conflict_aware,
)
from python_setup_lint.testing import fake_run_cmd_factory, make_lint_result
from tests._project_helpers import (
    commit_all,
    git_init_bare,
    stage_file,
    write_project_file,
)
from tests.runner._autofix_helpers import (
    _CANARY_LABEL,
    _make_canned_fix_results,
    _PostFixFakeRunCmd,
    _setup_e999_canary_revert,
)
from tests.runner._factories import (
    canned_results_all_tools,
    tmp_config,
)

# ── Surface-unit: env-var opt-out is honoured before the loop ────


class TestRunLintFixDispatch:
    """``run_lint(fix=True)`` routes supports_fix tools through the conflict-aware helper."""

    def test_run_lint_fix_dispatch_given_fix_route_then_uses_conflict_helper(
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
        ``spec.default_paths`` + ``--path``.  Only ruff and rumdl have
        ``default_paths`` set (ruff: ``["src/", "tests/"]``, rumdl: ``["."]``);
        ty without a ``--path`` falls into the "no enumerable targets" branch
        (canary short-circuits).  The test creates files under ruff's default
        dirs + a separate path-only fixture to exercise both branches.
        """
        monkeypatch.delenv(_AUTOFIX_ENV_VAR, raising=False)
        canned = _make_canned_fix_results()
        fake = fake_run_cmd_factory(canned)
        monkeypatch.setattr(_output_module, "_run_cmd", fake)

        # Create source files under ruff's default_paths so the canary has
        # something to enumerate (otherwise canary_targets is empty and the
        # canary short-circuits without calling run_cmd).
        write_project_file(tmp_path, "src/main.py", "x = 1\n")
        write_project_file(tmp_path, "tests/test_main.py", "y = 1\n")
        run_lint(config=tmp_config(tmp_path), fix=True)
        labels = [c.label for c in fake.calls]
        # ruff has default_paths=["src/", "tests/"] → canary fires once.
        assert _CANARY_LABEL in labels, f"canary label never appeared in fix=True labels: {labels!r}"

    def test_run_lint_fix_dispatch_given_path_then_triggers_canary(
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
        monkeypatch.setattr(_output_module, "_run_cmd", fake)
        target = write_project_file(tmp_path, "src/main.py", "x = 1\n")
        run_lint(
            config=tmp_config(tmp_path),
            path=str(target.relative_to(tmp_path)),
            fix=True,
        )
        labels = [c.label for c in fake.calls]
        # All three supports_fix tools receive the --path → canary fires once each.
        assert labels.count(_CANARY_LABEL) == 3, f"canary call count mismatch with --path: {labels!r}"

    def test_run_lint_fix_dispatch_given_no_fix_then_no_canary(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``run_lint(fix=False)`` never calls the canary (no autofix helper used)."""
        monkeypatch.delenv(_AUTOFIX_ENV_VAR, raising=False)
        canned = canned_results_all_tools()
        fake = fake_run_cmd_factory(canned)
        monkeypatch.setattr(_output_module, "_run_cmd", fake)
        run_lint(config=tmp_config(tmp_path), fix=False)
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

    def _make_spec(self) -> ToolSpec:  # pylint: disable=trivial-wrapper  # test helper; readability over DRY
        return next(t for t in LINT_TOOLS if t.name == "ruff check")

    def _make_canned(self, *, canary_e999_files: tuple[str, ...] = ()) -> dict[str, LintResult]:  # pylint: disable=generic-key-dict  # dict[str, LintResult] is a test helper; string keys are fixture labels
        base = canned_results_all_tools(exit_code=0, stdout="")
        canary_stdout = "\n".join(f"{f}:1:1: E999 SyntaxError" for f in canary_e999_files) if canary_e999_files else ""
        base[self._CANARY_LABEL] = make_lint_result(tool_name=self._CANARY_LABEL, exit_code=1, stdout=canary_stdout)
        return base

    # ── Case 1: staged+unstaged same file → skipped ──────────────

    def test_autofix_real_git_given_staged_and_unstaged_same_file_then_skipped(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """File with staged AND unstaged changes is skipped; staged blob untouched."""
        git_init_bare(tmp_path)
        write_project_file(tmp_path, "f.py", "x = 1\n")
        commit_all(tmp_path)
        # Stage a change, then overlay an unstaged change on the same file.
        write_project_file(tmp_path, "f.py", "y = 2\n")
        stage_file(tmp_path, "f.py")
        write_project_file(tmp_path, "f.py", "z = 3\n")
        import subprocess

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
        assert post_staged_blob == staged_blob, f"staged blob changed: was {staged_blob!r}, now {post_staged_blob!r}"
        # The unstaged content is also unchanged (the fix tool never wrote).
        assert (tmp_path / "f.py").read_text() == "z = 3\n"

    # ── Case 2: staged-only file gets fixed ──────────────────────

    def test_autofix_real_git_given_staged_only_then_fixed(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """File staged only (no unstaged changes) → autofix applies."""
        git_init_bare(tmp_path)
        write_project_file(tmp_path, "f.py", "x = 1\n")
        commit_all(tmp_path)
        write_project_file(tmp_path, "f.py", "y = 2\n")
        stage_file(tmp_path, "f.py")
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

    def test_autofix_real_git_given_e999_canary_then_reverts(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A fix that breaks parseability triggers E999-canary revert; file restored."""
        git_init_bare(tmp_path)
        write_project_file(tmp_path, "src/main.py", "x = 1  # original\n")
        commit_all(tmp_path)
        original = "x = 1  # original\n"
        post_fix = "x = 2  # broken-syntax\n"
        target = tmp_path / "src/main.py"
        canned = self._make_canned(canary_e999_files=("src/main.py",))
        wrapped = _setup_e999_canary_revert(
            tmp_path,
            original=original,
            post_fix=post_fix,
            target=target,
            canned=canned,
            make_spec=self._make_spec,
        )
        captured = capsys.readouterr()
        assert "autofix reverted src/main.py: E999 after fix" in captured.err
        # (a) The fix pass modified the file.
        after_fix = wrapped.snapshots_after_label("ruff check")
        assert after_fix == post_fix, f"fix pass did not modify file: got {after_fix!r}"
        # (b) Final on-disk state equals original — revert worked.
        assert target.read_text() == original
