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
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from python_setup_lint.runner import TOOLS, RunnerConfig, run_lint
from python_setup_lint.runner._config import _SHIPPED_CONFIG_FILES
from python_setup_lint.setup import install
from python_setup_lint.testing import (
    assert_precommit_config_valid,
    assert_precommit_hooks_shape,
)

# ── Helpers ────────────────────────────────────────────────────────────

def _copy_sample(tmp_path: Path) -> Path:
    """Copy the minimal sample project to *tmp_path* and return the path."""
    sample = Path("tests/data/minimal_sample_project")
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
        Path("tests/data/minimal_sample_project/violations.txt").read_text().splitlines()
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
        rc = run_lint(config=config, path=".")
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

        # ── Brush-off suppression is detected ─────────────────────────
        assert "pre-existing" in output, (
            "Expected brush-off suppression 'pre-existing' to trigger W9704.\n"
            f"Output excerpt:\n{output[:3000]}"
        )

        # Carry-from external library should NOT be flagged as unjustified-suppression
        carry_from_violations = [
            l for l in output.splitlines()
            if "_carry_from_external" in l and "unjustified-suppression" in l
        ]
        assert not carry_from_violations, f"Carry-from should NOT trigger W9704:\n{carry_from_violations}"

        # ── All tool sections appear ──────────────────────────────────
        tool_names = {t.name for t in TOOLS}
        for name in sorted(tool_names):
            assert f"[{name}]" in output, (
                f"Expected tool section [{name}] not found in lint output.\n"
                f"Output excerpt:\n{output[:3000]}"
            )

        # ── No tool crashed ────────────────────────────────────────────
        assert "[CRASH]" not in output, (
            f"Tool crash detected in lint output:\n{output}\n"
            f"This must be fixed before committing."
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
        # Remove use-structlog from the enable list programmatically (robust against enable list churn).
        enable_match = re.search(r"^enable=(.+)", pylintrc_content, re.MULTILINE)
        assert enable_match, "Could not find enable= line in pylintrc"
        enable_items = enable_match.group(1).split(",")
        filtered = [item for item in enable_items if item != "use-structlog"]
        new_enable = "enable=" + ",".join(filtered)
        pylintrc_content = pylintrc_content[:enable_match.start()] + new_enable + pylintrc_content[enable_match.end():]
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
        rc = run_lint(config=config)
        assert isinstance(rc, int)

        captured = capsys.readouterr()
        output = captured.out + captured.err

        # The disabled rule must NOT appear in the pylint section.
        # (pylint-pyi has its own rcfile resolution that doesn't use config_paths.)
        pylint_section_start = output.find("[pylint] FAILED")
        pylint_pyi_start = output.find("[pylint-pyi]")
        pylint_output = output[pylint_section_start:pylint_pyi_start] if 0 <= pylint_section_start < pylint_pyi_start else output

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
        except (FileNotFoundError, subprocess.CalledProcessError):
            logging.warning("pre-commit not available, skipping test")
            pytest.skip("pre-commit not available")

        project = _copy_sample(tmp_path)
        _init_git(project)

        # Create .pre-commit-config.yaml from the template.
        from python_setup_lint._setup_precommit import _PRECOMMIT_TEMPLATE

        (project / ".pre-commit-config.yaml").write_text(_PRECOMMIT_TEMPLATE)

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
        d.mkdir()
        (d / "src/consumer").mkdir(parents=True)
        (d / "src/consumer/__init__.py").write_text("# c\n")
        (d / "tests").mkdir()
        (d / "tests/__init__.py").write_text("# t\n")
        (d / "pyproject.toml").write_text(
            textwrap.dedent("""\
            [project]
            name = "consumer"
            version = "0.1.0"
            requires-python = ">=3.14"
            [dependency-groups]
            dev = ["ruff>=0.5", "python-setup"]
        """)
        )
        (d / "AGENTS.md").write_text("# C\n")
        _init_git(d)
        (d / ".secrets.baseline").write_text(
            '{"version":"1.0","plugins_used":[],"filters_used":[],'
            '"results":{},"generated_at":"2025-01-01T00:00:00Z"}\n'
        )
        (d / "tach.toml").write_text(
            '[[modules]]\npath = "src/consumer"\ndepends_on = []\n'
        )

        # Install
        rc = install(d, dev_path=str(Path.cwd()))
        assert rc == 0, f"install failed with exit code {rc}"

        # Verify install artifacts
        assert (d / ".pre-commit-config.yaml").exists()
        assert (d / "CodingRules.md").exists()
        assert "<!-- python-setup:pre-commit -->" in (d / "AGENTS.md").read_text()

        # Run lint
        rc = run_lint(
            config=RunnerConfig(
                cwd=d,
                tools_override=[
                    "ruff check",
                    "mypy",
                    "pylint",
                ],
            )
        )
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
        try:
            subprocess.run(
                ["pre-commit", "--version"],
                capture_output=True,
                check=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            logging.warning("pre-commit not available, skipping test")
            pytest.skip("pre-commit not available")

        d = tmp_path / "hooks"
        d.mkdir()
        (d / "src/consumer").mkdir(parents=True)
        (d / "src/consumer/__init__.py").write_text("# c\n")
        (d / "tests").mkdir()
        (d / "tests/__init__.py").write_text("# t\n")
        (d / "pyproject.toml").write_text(
            textwrap.dedent("""\
            [project]
            name = "consumer"
            version = "0.1.0"
            requires-python = ">=3.14"
            [dependency-groups]
            dev = ["ruff>=0.5", "python-setup"]
        """)
        )
        (d / "AGENTS.md").write_text("# C\n")
        _init_git(d)
        (d / ".secrets.baseline").write_text(
            '{"version":"1.0","plugins_used":[],"filters_used":[],'
            '"results":{},"generated_at":"2025-01-01T00:00:00Z"}\n'
        )
        (d / "tach.toml").write_text(
            '[[modules]]\npath = "src/consumer"\ndepends_on = []\n'
        )

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
            logging.debug("pre-commit dry-run exited with code %d (expected 0 or 1)", exc.returncode)
            result = exc
        # Dry-run should succeed (exit 0) or report hooks would change files (exit 1)
        assert result.returncode in (0, 1), (
            f"pre-commit dry-run failed (exit {result.returncode}):\n"
            f"{result.stdout}\n{result.stderr}"
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
        project = _copy_sample(tmp_path)
        _init_git(project)

        config = _make_config(project)
        baseline_file = tmp_path / "lint.baseline"
        rc = run_lint(config=config, path=".", baseline=str(baseline_file), overwrite_baseline=True)
        assert isinstance(rc, int)

        assert baseline_file.exists(), "Baseline file was not created"
        data = json.loads(baseline_file.read_text())
        assert isinstance(data, list), f"Expected list, got {type(data)}"

        for entry in data:
            file_val = entry.get("file")
            if file_val is not None:
                assert not str(file_val).startswith("/"), (
                    f"Expected relative path, got absolute: {file_val!r}\n"
                    f"Full entry: {entry}"
                )
