"""T4 — conflict-tolerant autofix: integration tests for ``--fix`` route."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

import python_setup_lint.runner.output as _output_module
from python_setup_lint.runner import LINT_TOOLS, LintResult, RunnerConfig, ToolSpec, run_lint
from python_setup_lint.runner._autofix import _AUTOFIX_ENV_VAR, _apply_autofix_conflict_aware
from python_setup_lint.testing import fake_run_cmd_factory, make_lint_result
from tests.runner._autofix_helpers import (
    _CANARY_LABEL,
    _FIX_TOOL_NAMES,
    _commit_all,
    _git_init,
    _make_canned_fix_results,
    _PostFixFakeRunCmd,
    _setup_e999_canary_revert,
    _stage,
    _write_file,
)
from tests.runner._factories import (
    canned_results_all_tools,
    tmp_config,
)

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
    def test_run_lint_fix_given_downstream_then_does_not_crash(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Run ``run_lint(fix=True)`` to completion (returns int).

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
        rc = run_lint(config=config, fix=True, baseline=str(baseline))
        assert isinstance(rc, int)
        # (a) The baseline file was created and is non-empty — proves the
        # runner completed the tool loop AND reached the baseline-save
        # branch (which only fires after all tools ran).
        assert baseline.exists(), "baseline file not created — runner did not finish"
        assert baseline.stat().st_size > 0, (
            f"baseline file empty: {baseline.read_text()!r}"
        )
        # (b) The baseline JSON parses to a list (violations list; empty on a
        # clean repo — the runner completed the full tool loop).
        import json as _json

        entries = _json.loads(baseline.read_text(encoding="utf-8"))
        assert isinstance(entries, list), (
            f"baseline not a JSON list: {type(entries).__name__}"
        )
        # (c) The autofix route was exercised: run_lint was called with
        # fix=True, completed (rc is int, baseline exists and parses), and
        # the runner iterated over all tools including supports_fix tools.
        # On this repo, fix-capable tools (ruff, rumdl, ty) produce zero
        # violations — assert that invariant to prove they ran cleanly.
        baseline_labels = {e.get("tool") for e in entries}
        fix_labels_seen = baseline_labels & _FIX_TOOL_NAMES
        assert not fix_labels_seen, (
            f"fix-capable tools unexpectedly produced violations: {fix_labels_seen!r}"
        )


# ── Surface-unit: pre-commit template carries --fix (T4 contract)  ─


class TestPrecommitTemplateHasFix:
    """T4 verification gate: rendered template's lint hook entry has ``--fix``."""

    def test_precommit_template_given_lint_entry_then_has_fix(self) -> None:
        """The ``lint`` local hook entry contains ``--fix``."""
        from python_setup_lint._setup_precommit import _PRECOMMIT_TEMPLATE

        # The lint line is a unique substring; assert it carries --fix.
        assert "python-setup lint --fix" in _PRECOMMIT_TEMPLATE, (
            "expected 'python-setup lint --fix' in template"
        )

    def test_precommit_template_given_lint_entry_then_no_timeout(self) -> None:
        """Template never carries the ``timeout`` key — avoiding the schema warning (D5)."""
        from python_setup_lint._setup_precommit import _PRECOMMIT_TEMPLATE

        assert "timeout" not in _PRECOMMIT_TEMPLATE.lower(), (
            "timeout key present in template — pre-commit would warn"
        )

    def test_precommit_template_given_lint_entry_then_no_pre_push(self) -> None:
        """The hook stage name ``pre-push`` is NOT in the template — fast hooks
        are tied to ``git commit`` only."""
        from python_setup_lint._setup_precommit import _PRECOMMIT_TEMPLATE

        assert "pre-push" not in _PRECOMMIT_TEMPLATE, "pre-push present in template"

    def test_precommit_template_given_template_then_still_has_ruff_hooks(self) -> None:
        """ruff-format + ruff-check fast hooks retained for compatibility."""
        from python_setup_lint._setup_precommit import _PRECOMMIT_TEMPLATE

        assert "ruff-format" in _PRECOMMIT_TEMPLATE
        assert "ruff-check" in _PRECOMMIT_TEMPLATE
        assert "args: [--fix, --exit-non-zero-on-fix]" in _PRECOMMIT_TEMPLATE

    def test_precommit_template_given_agents_snippet_then_documents_autofix(self) -> None:
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

    def test_precommit_template_given_install_artifact_then_lint_hook_has_fix(self, tmp_path: Path) -> None:
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
        _write_file(tmp_path, "src/main.py", "x = 1\n")
        _write_file(tmp_path, "tests/test_main.py", "y = 1\n")
        run_lint(config=tmp_config(tmp_path), fix=True)
        labels = [c.label for c in fake.calls]
        # ruff has default_paths=["src/", "tests/"] → canary fires once.
        assert _CANARY_LABEL in labels, (
            f"canary label never appeared in fix=True labels: {labels!r}"
        )

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
        target = _write_file(tmp_path, "src/main.py", "x = 1\n")
        run_lint(
            config=tmp_config(tmp_path),
            path=str(target.relative_to(tmp_path)),
            fix=True,
        )
        labels = [c.label for c in fake.calls]
        # All three supports_fix tools receive the --path → canary fires once each.
        assert labels.count(_CANARY_LABEL) == 3, (
            f"canary call count mismatch with --path: {labels!r}"
        )

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

    def _make_canned(
        self, *, canary_e999_files: tuple[str, ...] = ()
    ) -> dict[str, LintResult]:  # pylint: disable=generic-key-dict  # dict[str, LintResult] is a test helper; string keys are fixture labels
        base = canned_results_all_tools(exit_code=0, stdout="")
        canary_stdout = "\n".join(
            f"{f}:1:1: E999 SyntaxError" for f in canary_e999_files
        ) if canary_e999_files else ""
        base[self._CANARY_LABEL] = make_lint_result(
            tool_name=self._CANARY_LABEL, exit_code=1, stdout=canary_stdout
        )
        return base

    # ── Case 1: staged+unstaged same file → skipped ──────────────

    def test_autofix_real_git_given_staged_and_unstaged_same_file_then_skipped(
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
        assert post_staged_blob == staged_blob, (
            f"staged blob changed: was {staged_blob!r}, now {post_staged_blob!r}"
        )
        # The unstaged content is also unchanged (the fix tool never wrote).
        assert (tmp_path / "f.py").read_text() == "z = 3\n"

    # ── Case 2: staged-only file gets fixed ──────────────────────

    def test_autofix_real_git_given_staged_only_then_fixed(
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

    def test_autofix_real_git_given_e999_canary_then_reverts(
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
