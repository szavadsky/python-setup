"""Integration tests for the full lint pipeline on the minimal sample project.

These tests exercise the real lint pipeline end-to-end on a planted-violation
project, verifying that all custom checkers fire, config overlays work, setup
is idempotent, and pre-commit hooks validate.

All tests are non-slow and network-free — they use ``run_lint`` / ``install``
programmatically (not subprocess), mock ``uv`` calls, and skip pre-commit if
the binary is unavailable.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import textwrap
from pathlib import Path

import pytest

from python_setup_lint.runner import TOOLS, RunnerConfig, run_lint
from python_setup_lint.setup import install
from python_setup_lint.testing import (
    assert_precommit_config_valid,
    assert_precommit_hooks_shape,
)
from tests._golden import (
    SEMANTIC_ENV,
    UPDATE_ENV,
    Finding,
    assert_golden_byte_identical,
    assert_matches_golden,
    assert_oracle_coverage,
    assert_tool_coverage,
    finding_key,
    read_oracle_rules,
    slice_tool_section,
    tool_counts_path,
)
from tests._project_helpers import (
    build_pylint_overlay_config,
    collect_sample_findings,
    copy_sample_project,
    ensure_precommit_or_skip,
    git_init_and_stage,
    install_twice_assert_idempotent,
    make_clean_consumer_project,
    make_runner_config,
)

GOLDEN_FINDINGS = Path(__file__).resolve().parent / "data" / "golden" / "minimal_sample_project_findings.json"


class TestMinimalSampleProject:
    """Integration tests exercising the full lint pipeline on the sample project."""

    def test_setup_new_and_lint(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        isolated_runner_registries: None,
    ) -> None:
        """Run lint on the sample project and pin every finding in the golden snapshot.

        Asserts:
        - The first run exits non-zero, reports every tool section, does not
          crash, does not skip for unexpected reasons and fires W9705.
        - A dedicated capture on a pristine copy matches the committed golden
          as a multiset, covers every oracle rule and meets per-tool minimums.
        - Brush-off suppression is reported where planted while the carry-from
          justification is not flagged as unjustified.
        - In-memory drift is reported precisely as added and removed keys.
        """
        project = copy_sample_project(tmp_path)
        git_init_and_stage(project)

        config = make_runner_config(project)
        rc = run_lint(config=config, path=".")
        assert rc != 0, f"Expected non-zero exit (sample project has planted violations), got rc={rc}"

        captured = capsys.readouterr()
        output = captured.out + captured.err

        # ── All tool sections appear ──────────────────────────────────
        tool_names = {t.name for t in TOOLS}
        for name in sorted(tool_names):
            assert f"[{name}]" in output, (
                f"Expected tool section [{name}] not found in lint output.\nOutput excerpt:\n{output[:3000]}"
            )

        # ── No tool crashed ────────────────────────────────────────────
        assert "[CRASH]" not in output, f"Tool crash detected in lint output:\n{output}\nThis must be fixed before committing."
        # ── All tools executed (no SKIPPED for non-package_name reasons) ──
        skipped_lines = [l for l in output.splitlines() if "SKIPPED:" in l]
        unexpected_skipped = [l for l in skipped_lines if "package_name" not in l]
        assert not unexpected_skipped, (
            "Expected no tools to be skipped for non-package_name reasons.\n"
            "Unexpected SKIPPED lines:\n" + "\n".join(unexpected_skipped)
        )
        # ── W9705 fires end-to-end ────────────────────────────────────────
        assert "generic-return-requires-returns" in output, (
            f"Expected W9705 (generic-return-requires-returns) in lint output.\nOutput excerpt:\n{output[:3000]}"
        )

        # ── Dedicated capture on a pristine copy ──────────────────────
        # The first run lets ``ruff format`` rewrite its copy; the snapshot
        # must observe the committed source, so it captures its own copy.
        monkeypatch.setenv(SEMANTIC_ENV, "0")
        findings = collect_sample_findings(tmp_path / "golden")
        assert findings, "collect_findings returned no findings for the planted-violation sample project"
        assert_matches_golden(findings, golden_path=GOLDEN_FINDINGS)
        assert_oracle_coverage(findings, read_oracle_rules())
        minimums = json.loads(tool_counts_path(GOLDEN_FINDINGS).read_text(encoding="utf-8"))
        assert_tool_coverage(findings, minimums)

        # ── Determinism: a fresh-copy replay serializes byte-identically ──
        replay = collect_sample_findings(tmp_path / "golden-replay")
        assert_golden_byte_identical(GOLDEN_FINDINGS, findings, replay)

        # ── Brush-off is flagged, carry-from is not ───────────────────
        mod_findings = [f for f in findings if f["tool"] == "pylint" and f["file"] == "src/minimal_sample/mod.py"]
        brushoff = [f for f in mod_findings if f["line"] == 49 and f["rule"] == "unjustified-suppression"]
        carry_from = [f for f in mod_findings if f["line"] == 56 and f["rule"] == "unjustified-suppression"]
        assert brushoff, f"Expected brush-off suppression at mod.py:49, got:\n{mod_findings}"
        assert not carry_from, f"Carry-from should NOT trigger W9704: {carry_from}"

        # ── Drift injection stays in memory ───────────────────────────
        if os.environ.get(UPDATE_ENV) != "1":
            injected = Finding(
                tool="pylint",
                file="src/minimal_sample/mod.py",
                line=1,
                col=1,
                rule="injected-drift",
            )
            with pytest.raises(pytest.fail.Exception, match="added") as added_exc:
                assert_matches_golden([*findings, injected], golden_path=GOLDEN_FINDINGS)
            assert repr(finding_key(injected)) in str(added_exc.value)
            with pytest.raises(pytest.fail.Exception, match="removed") as removed_exc:
                assert_matches_golden(findings[1:], golden_path=GOLDEN_FINDINGS)
            assert repr(finding_key(findings[0])) in str(removed_exc.value)

    def test_config_overlay(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        isolated_runner_registries: None,
    ) -> None:
        """Modify a config file to disable a rule and verify it no longer fires.

        Creates a project-local ``.pylintrc`` that disables ``use-structlog``
        and passes it via ``config_paths``.  The ``use-structlog`` violation
        must disappear from the pylint output.
        """
        project = copy_sample_project(tmp_path)
        git_init_and_stage(project)

        # Build a project-local .pylintrc that disables use-structlog.
        config = make_runner_config(project)
        config_paths = config.config_paths
        assert config_paths is not None
        config_paths["pylint"] = build_pylint_overlay_config(project, "use-structlog")
        rc = run_lint(config=config)
        assert isinstance(rc, int)

        captured = capsys.readouterr()
        output = captured.out + captured.err

        # The disabled rule must NOT appear in the pylint section.
        # (pylint-pyi has its own rcfile resolution that doesn't use config_paths.)
        pylint_output = slice_tool_section(output, "[pylint]", "[pylint-pyi]")

        assert "use-structlog" not in pylint_output, (
            "Expected 'use-structlog' to be disabled by config overlay in pylint output, but it still appears."
        )

        # Other violations should still be present in pylint output.
        assert "unnamed-tuple-dict-value" in pylint_output, "Expected other violations to remain after config overlay."

    def test_resetup_idempotent(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Run setup twice and verify the second run is idempotent (no errors).

        Mocks ``_run_uv`` to avoid network calls.
        """
        project = copy_sample_project(tmp_path)
        git_init_and_stage(project)
        install_twice_assert_idempotent(project, monkeypatch)

    def test_dry_run_hooks(
        self,
        tmp_path: Path,
    ) -> None:
        """Run pre-commit validate-config on the sample project and verify it passes.

        Skips the test if ``pre-commit`` is not available.
        """
        ensure_precommit_or_skip()
        project = copy_sample_project(tmp_path)
        git_init_and_stage(project)

        # Create .pre-commit-config.yaml from the template with a known rev.
        from python_setup_lint._setup_precommit import _PRECOMMIT_TEMPLATE

        (project / ".pre-commit-config.yaml").write_text(_PRECOMMIT_TEMPLATE.format(ruff_rev="v0.15.17"))

        # Run pre-commit validate-config.
        subprocess.run(
            ["pre-commit", "validate-config"],
            cwd=project,
            capture_output=True,
            text=True,
            check=True,
        )

    def test_install_then_lint_clean_project(
        self,
        tmp_path: Path,
    ) -> None:
        """Create a clean project, run install, then run lint.

        Verifies install artifacts are created and lint runs without crashing.
        """
        d = tmp_path / "consumer"
        make_clean_consumer_project(d)
        # Install
        rc = install(d, dev_path=str(Path.cwd()))
        assert rc == 0, f"install failed with exit code {rc}"

        # Verify install artifacts
        assert (d / ".pre-commit-config.yaml").exists()
        assert (d / "CodingRules.md").exists()
        assert "<!-- python-setup:pre-commit -->" in (d / "AGENTS.md").read_text()

        # Run lint
        rc = run_lint(config=RunnerConfig(cwd=d, tools_override=["ruff check", "mypy", "pylint"]))
        # Lint may find violations in the minimal consumer project;
        # we only assert it ran without crashing (exit code 0 or 2
        # for pylint-found issues, not a crash).
        assert rc in (0, 2), f"lint crashed with exit code {rc}"

    def test_pre_commit_dry_run(
        self,
        tmp_path: Path,
    ) -> None:
        """Install, validate pre-commit config, run dry-run.

        Skips the test if ``pre-commit`` is not available.
        """
        ensure_precommit_or_skip()
        d = tmp_path / "hooks"
        make_clean_consumer_project(d)

        # Install
        rc = install(d, dev_path=str(Path.cwd()))
        assert rc == 0, f"install failed with exit code {rc}"

        # Validate pre-commit config shape
        assert_precommit_config_valid(d)
        assert_precommit_hooks_shape(d)

        # Dry-run: pre-commit run --all-files --show-diff-on-failure
        result: subprocess.CompletedProcess[str] | subprocess.CalledProcessError
        try:
            result = subprocess.run(
                ["pre-commit", "run", "--all-files", "--show-diff-on-failure"],
                cwd=d,
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            logging.debug(
                "pre-commit dry-run exited with code %d (expected 0 or 1)",
                exc.returncode,
            )
            result = exc
        # Dry-run should succeed (exit 0) or report hooks would change files (exit 1)
        assert result.returncode in (0, 1), (
            f"pre-commit dry-run failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        )
        # Output should mention the hooks we expect
        assert "ruff-format" in result.stdout or "ruff" in result.stdout, (
            f"Expected ruff hooks in dry-run output:\n{result.stdout}"
        )

    def test_baseline_relative_paths(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        isolated_runner_registries: None,
    ) -> None:
        """Create a baseline and verify all ``file`` values are relative paths.

        Asserts:
        - Every ``file`` value in the baseline JSON is either ``None`` or a
          relative path (does not start with ``/``).
        """
        project = copy_sample_project(tmp_path)
        git_init_and_stage(project)

        config = make_runner_config(project)
        baseline_file = tmp_path / "lint.baseline"
        rc = run_lint(
            config=config,
            path=".",
            baseline=str(baseline_file),
            overwrite_baseline=True,
        )
        assert isinstance(rc, int)

        assert baseline_file.exists(), "Baseline file was not created"
        data = json.loads(baseline_file.read_text())
        assert isinstance(data, list), f"Expected list, got {type(data)}"

        for entry in data:
            file_val = entry.get("file")
            if file_val is not None:
                assert not str(file_val).startswith("/"), (
                    f"Expected relative path, got absolute: {file_val!r}\nFull entry: {entry}"
                )

    def test_individual_tool_parity(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        isolated_runner_registries: None,
    ) -> None:
        """Verify that the runner's ruff invocation and direct ``ruff check``
        produce the same set of violation rule symbols.

        Guards against regressions where the runner's tool command diverges
        from the standalone tool invocation (single-source-of-truth broken).
        """
        project = copy_sample_project(tmp_path)
        git_init_and_stage(project)

        # ── Run ruff through the runner ──────────────────────────────
        config = make_runner_config(project)
        config.tools_override = ["ruff check"]
        rc = run_lint(config=config, path=".")
        assert isinstance(rc, int)

        captured = capsys.readouterr()
        runner_output = captured.out + captured.err

        # Extract rule symbols from ``file:line:col: CODE message`` lines.
        runner_rules = set(re.findall(r"^.*?:\d+:\d+: (\w+)", runner_output, re.MULTILINE))

        # ── Run ruff directly as a subprocess ───────────────────────
        ruff_config = (Path("config") / "ruff.toml").resolve()
        assert ruff_config.is_file(), f"Shipped ruff config not found: {ruff_config}"

        result = subprocess.run(
            [
                "ruff",
                "check",
                "--output-format",
                "concise",
                "--config",
                str(ruff_config),
                ".",
            ],
            capture_output=True,
            text=True,
            cwd=project,
            check=False,
        )

        direct_output = result.stdout + result.stderr
        direct_rules = set(re.findall(r"^.*?:\d+:\d+: (\w+)", direct_output, re.MULTILINE))

        # ── Assert parity ───────────────────────────────────────────
        assert runner_rules == direct_rules, (
            f"Rule symbol mismatch between runner and direct ruff check.\n"
            f"Runner only: {runner_rules - direct_rules}\n"
            f"Direct only: {direct_rules - runner_rules}\n"
            f"Runner output:\n{runner_output[:2000]}\n"
            f"Direct output:\n{direct_output[:2000]}"
        )

    def test_rumdl_disabled_rules_guard(
        self,
        tmp_path: Path,
    ) -> None:
        """Verify rumdl respects disabled rules (MD013, MD040) from config/rumdl.toml.

        The runner uses ``rumdl check --fix`` (not ``rumdl fmt``). This test
        exercises that exact invocation path against a fixture that would be
        modified by MD013 and MD040 if they were enabled.

        Asserts:
        - ``rumdl check --fix --config config/rumdl.toml`` leaves the fixture
          unchanged (disabled rules are not applied).
        - A mutation (re-enabling MD040) causes the fixture to be modified —
          confirms the guard actually bites.
        """
        # ── Fixture: lines that would trigger MD013 (line-length >80) and
        #    MD040 (bare fenced code block without language tag).
        fixture_text = textwrap.dedent("""\
        # Test

        This is a long line that exceeds 80 characters and would normally trigger MD013 line-length enforcement by rumdl.

        ```
        x = 1
        ```
        """)
        config_path = Path("config/rumdl.toml").resolve()
        assert config_path.is_file(), "Shipped rumdl.toml not found"

        # ── Primary: rumdl check --fix with shipped config (runner path) ─────
        md_file = tmp_path / "test.md"
        md_file.write_text(fixture_text)

        proc = subprocess.run(
            ["rumdl", "check", "--fix", "--config", str(config_path), str(md_file)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        # Exit 0 means no issues found — the disabled rules stay silent.
        assert proc.returncode == 0, (
            f"rumdl check --fix with shipped config exited {proc.returncode}:\nstdout:{proc.stdout}\nstderr:{proc.stderr}"
        )
        assert md_file.read_text() == fixture_text, (
            "Fixture was modified by rumdl check --fix with shipped config.\n"
            "MD013 and/or MD040 appear to be active despite being in the disable list."
        )

        # ── Mutation: re-enable MD040 (auto-fixable) in a copy of the config ──
        #    MD013 is not auto-fixable (rumdl reports it but doesn't fix it),
        #    so we use MD040 which IS auto-fixable (injects a language tag).
        #    The shipped config uses ``enable`` as a whitelist, so we must
        #    both remove MD040 from ``disable`` and add it to ``enable``.
        mutated_config = config_path.read_text()
        mutated_config = mutated_config.replace(
            '    "MD040",  # fenced-code-language',
            '    # "MD040",  # fenced-code-language — re-enabled for mutation test',
        )
        mutated_config = mutated_config.replace(
            '    "MD009",  # no-trailing-spaces',
            '    "MD040",  # fenced-code-language\n    "MD009",  # no-trailing-spaces',
        )
        mutated = tmp_path / "mutated_rumdl.toml"
        mutated.write_text(mutated_config)

        md_file2 = tmp_path / "test_mutate.md"
        md_file2.write_text(fixture_text)

        proc2 = subprocess.run(
            ["rumdl", "check", "--fix", "--config", str(mutated), str(md_file2)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        # MD040 is auto-fixable — the file content should change (language tag
        # injected).  If it doesn't, the guard is not catching regressions.
        assert md_file2.read_text() != fixture_text, (
            "Mutation test failed: re-enabling MD040 did not cause rumdl to "
            "modify the fixture. The guard test would not catch a regression.\n"
            f"rumdl stdout: {proc2.stdout}\nstderr: {proc2.stderr}"
        )

        # ── Optional: rumdl fmt standalone ──────────────────────────────────
        #    Document whether it also respects the config (it does, as of
        #    rumdl 0.2.28 — both paths honor the disable list).
        md_file3 = tmp_path / "test_fmt.md"
        md_file3.write_text(fixture_text)
        proc3 = subprocess.run(
            ["rumdl", "fmt", "--config", str(config_path), str(md_file3)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc3.returncode == 0 and md_file3.read_text() == fixture_text:
            pass  # rumdl fmt also respects the disable list — consistent.
        else:
            # Log the behavioral difference without failing the primary test.
            # As of rumdl 0.2.28 the fmt subcommand does honor the config,
            # but this guard is not authoritative for ``fmt`` (the runner
            # uses ``check --fix``).
            logging.info(
                "rumdl fmt behavior differs from check --fix (exit %d): %s",
                proc3.returncode,
                proc3.stdout or proc3.stderr,
            )
