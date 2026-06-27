"""Integration tests for the full lint pipeline on the minimal sample project.

These tests exercise the real lint pipeline end-to-end on a planted-violation
project, verifying that all custom checkers fire, config overlays work, setup
is idempotent, and pre-commit hooks validate.

All tests are non-slow and network-free — they use ``run_lint`` / ``install``
programmatically (not subprocess), mock ``uv`` calls, and skip pre-commit if
the binary is unavailable.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from python_setup_lint.runner import TOOLS, RunnerConfig, run_lint
from python_setup_lint.runner._config import _SHIPPED_CONFIG_FILES


# ── Helpers ────────────────────────────────────────────────────────────


def _copy_sample(tmp_path: Path) -> Path:
    """Copy the minimal sample project to *tmp_path* and return the path."""
    sample = Path("test/data/minimal_sample_project")
    dest = tmp_path / "project"
    shutil.copytree(sample, dest)
    return dest


def _init_git(project: Path) -> None:
    """Initialise a git repo in *project* (needed by detect-secrets)."""
    subprocess.run(["git", "init"], cwd=project, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test"],
        cwd=project,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=project,
        capture_output=True,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=project, capture_output=True, check=True)


def _read_violation_rules() -> list[str]:
    """Read expected violation rule names from ``violations.txt``."""
    rules: list[str] = []
    for line in (
        Path("test/data/minimal_sample_project/violations.txt").read_text().splitlines()
    ):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            rules.append(stripped)
    return rules


def _shipped_config_paths() -> dict[str, Path]:
    """Build config_paths dict from the python-setup project root config/ dir."""
    config_root = Path("config")
    paths: dict[str, Path] = {}
    for tool_label, filename in _SHIPPED_CONFIG_FILES.items():
        candidate = config_root / filename
        if candidate.is_file():
            paths[tool_label] = candidate.resolve()
    return paths


def _make_config(project: Path) -> RunnerConfig:
    """Build a ``RunnerConfig`` for the sample project with shipped config paths."""
    return RunnerConfig(
        cwd=project,
        package_name="minimal_sample",
        config_paths=_shipped_config_paths(),
    )


# ── Tests ─────────────────────────────────────────────────────────────


class TestMinimalSampleProject:
    """Integration tests exercising the full lint pipeline on the sample project."""

    def test_setup_new_and_lint(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        isolated_runner_registries: None,
    ) -> None:
        """Run lint on the sample project and verify all planted violations are reported.

        Asserts:
        - Every rule name from ``violations.txt`` appears in the lint output.
        - Every built-in tool section header appears in the lint output.
        """
        project = _copy_sample(tmp_path)
        _init_git(project)

        config = _make_config(project)
        rc = run_lint(config=config, no_fail_fast=True)
        assert isinstance(rc, int), f"Expected int exit code, got {type(rc)}: {rc}"

        captured = capsys.readouterr()
        output = captured.out + captured.err

        # ── All planted violations are reported ──────────────────────
        expected_rules = _read_violation_rules()
        for rule in expected_rules:
            assert rule in output, (
                f"Expected violation rule {rule!r} not found in lint output.\n"
                f"Output excerpt:\n{output[:3000]}"
            )

        # ── All tool sections appear ──────────────────────────────────
        tool_names = {t.name for t in TOOLS}
        for name in sorted(tool_names):
            assert f"[{name}]" in output, (
                f"Expected tool section [{name}] not found in lint output.\n"
                f"Output excerpt:\n{output[:3000]}"
            )

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
        project = _copy_sample(tmp_path)
        _init_git(project)

        # Build a project-local .pylintrc that disables use-structlog.
        config_root = Path("config")
        shipped_pylintrc = config_root / ".pylintrc"
        assert shipped_pylintrc.is_file(), "Shipped pylintrc not found"
        pylintrc_content = shipped_pylintrc.read_text()

        # Add use-structlog to the disable list.
        pylintrc_content = pylintrc_content.replace(
            "disable=",
            "disable=use-structlog,",
        )
        # Remove use-structlog from the enable list.
        pylintrc_content = pylintrc_content.replace(
            "enable=too-many-statements,too-many-branches,too-many-locals,too-many-nested-blocks,too-many-public-methods,too-complex,no-try-import,missing-beartype,tempfile-mkdtemp-in-test,asyncio-timeout,missing-module-stub,missing-import-declaration,missing-module-stub-for-import,star-import-unresolvable,signature-mismatch,annotation-mismatch,impl-missing-annotation,annotation-unverifiable,stub-symbol-missing,symbol-kind-mismatch,duplicate-code,pyi-underscore-symbol,use-structlog,docstring-in-impl,generic-return-requires-returns,internal-helper-docstring-allowed,unjustified-suppression,unnamed-tuple-dict-value,generic-key-dict,use-structured-logging",
            "enable=too-many-statements,too-many-branches,too-many-locals,too-many-nested-blocks,too-many-public-methods,too-complex,no-try-import,missing-beartype,tempfile-mkdtemp-in-test,asyncio-timeout,missing-module-stub,missing-import-declaration,missing-module-stub-for-import,star-import-unresolvable,signature-mismatch,annotation-mismatch,impl-missing-annotation,annotation-unverifiable,stub-symbol-missing,symbol-kind-mismatch,duplicate-code,pyi-underscore-symbol,docstring-in-impl,generic-return-requires-returns,unjustified-suppression,unnamed-tuple-dict-value,generic-key-dict,use-structured-logging",
        )
        local_pylintrc = project / ".pylintrc"
        local_pylintrc.write_text(pylintrc_content)

        # Build config paths from shipped configs, then override pylint.
        config_paths = _shipped_config_paths()
        config_paths["pylint"] = local_pylintrc

        config = RunnerConfig(
            cwd=project,
            package_name="minimal_sample",
            config_paths=config_paths,
        )
        rc = run_lint(config=config, no_fail_fast=True)
        assert isinstance(rc, int)

        captured = capsys.readouterr()
        output = captured.out + captured.err

        # The disabled rule must NOT appear in the pylint section.
        # (pylint-pyi has its own rcfile resolution that doesn't use config_paths.)
        pylint_section_start = output.find("[pylint] FAILED")
        pylint_pyi_start = output.find("[pylint-pyi]")
        if pylint_section_start >= 0 and pylint_pyi_start > pylint_section_start:
            pylint_output = output[pylint_section_start:pylint_pyi_start]
        else:
            pylint_output = output

        assert "use-structlog" not in pylint_output, (
            "Expected 'use-structlog' to be disabled by config overlay in pylint output, "
            "but it still appears."
        )

        # Other violations should still be present in pylint output.
        assert "unnamed-tuple-dict-value" in pylint_output, (
            "Expected other violations to remain after config overlay."
        )

    def test_resetup_idempotent(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Run setup twice and verify the second run is idempotent (no errors).

        Mocks ``_run_uv`` to avoid network calls.
        """
        import python_setup_lint.setup as _setup_mod
        from python_setup_lint.setup import install

        project = _copy_sample(tmp_path)
        _init_git(project)

        # Mock _run_uv to return success without network.
        original_run_uv = _setup_mod._run_uv

        def fake_run_uv(args: list[str], *, cwd: str | Path) -> tuple[int, str, str]:
            return 0, "", ""

        monkeypatch.setattr(_setup_mod, "_run_uv", fake_run_uv)

        try:
            # First install.
            rc1 = install(project)
            assert rc1 == 0, f"First install failed with exit code {rc1}"

            # Second install — should be idempotent.
            rc2 = install(project)
            assert rc2 == 0, (
                f"Second install failed with exit code {rc2} (should be idempotent)"
            )
        finally:
            monkeypatch.setattr(_setup_mod, "_run_uv", original_run_uv)

    def test_dry_run_hooks(
        self,
        tmp_path: Path,
    ) -> None:
        """Run pre-commit validate-config on the sample project and verify it passes.

        Skips the test if ``pre-commit`` is not available.
        """
        try:
            subprocess.run(
                ["pre-commit", "--version"],
                capture_output=True,
                check=True,
            )
        except FileNotFoundError, subprocess.CalledProcessError:
            pytest.skip("pre-commit not available")

        project = _copy_sample(tmp_path)
        _init_git(project)

        # Create .pre-commit-config.yaml from the template.
        from python_setup_lint._setup_precommit import _PRECOMMIT_TEMPLATE

        (project / ".pre-commit-config.yaml").write_text(_PRECOMMIT_TEMPLATE)

        # Run pre-commit validate-config.
        result = subprocess.run(
            ["pre-commit", "validate-config"],
            cwd=project,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"pre-commit validate-config failed (exit={result.returncode}).\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
