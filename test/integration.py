"""Integration tests for the full python-setup install/lint pipeline.

Exercises real subprocess calls (uv, pre-commit, pylint, etc.)
across 7 scenarios: setup, lint, violations, config overlay, resetup,
update, and git hooks dry-run.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import textwrap
from pathlib import Path


from python_setup_lint.runner import RunnerConfig, run_lint
from python_setup_lint.setup import install, update
from python_setup_lint.testing import (
    assert_precommit_config_valid,
    assert_precommit_hooks_shape,
)

# ── Helpers ──────────────────────────────────────────────────────────

SAMPLE_PROJECT = Path("test/data/minimal_sample_project")


def _git_init(d: Path) -> None:
    """Initialise a git repo in *d* (required by pre-commit and some tools)."""
    subprocess.run(["git", "init"], cwd=d, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t"],
        cwd=d,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=d,
        capture_output=True,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=d, capture_output=True, check=True)


def _read_violations() -> list[str]:
    """Read expected violation patterns from violations.txt."""
    text = (SAMPLE_PROJECT / "violations.txt").read_text()
    return [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]


def _lint_output_contains_violation(output: str, pattern: str) -> bool:
    """Check if *output* contains a line matching *pattern* (regex)."""
    return bool(re.search(pattern, output, re.IGNORECASE))


# ── Test: install + lint on a clean project ─────────────────────────


class TestInstallAndLint:
    """End-to-end install-then-lint integration."""

    def test_setup_given_clean_project_then_installs_and_runs_lint(
        self, tmp_path: Path
    ) -> None:
        """Create a clean project, run install, then run lint."""
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
        _git_init(d)
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
            ),
            no_fail_fast=True,
        )
        # Lint may find violations in the minimal consumer project;
        # we only assert it ran without crashing (exit code 0 or 2
        # for pylint-found issues, not a crash).
        assert rc in (0, 2), f"lint crashed with exit code {rc}"


# ── Test: planted violations detection ────────────────────────────────


class TestPlantedViolations:
    """Verify that all planted violations are detected by the linters."""

    def test_lint_given_planted_violations_then_all_detected(
        self, tmp_path: Path
    ) -> None:
        """Run lint on the sample project and check all expected violations appear."""
        d = tmp_path / "sample"
        shutil.copytree(SAMPLE_PROJECT, d)
        _git_init(d)

        # Run lint with pylint (which carries our custom checkers)
        rc = run_lint(
            config=RunnerConfig(
                cwd=d,
                tools_override=["pylint"],
                default_py_dirs=["src"],
            ),
            no_fail_fast=True,
        )
        # pylint returns 0 (no issues) or 2 (issues found) or 32 (usage error)
        assert rc in (0, 2, 32), f"pylint crashed with exit code {rc}"

        # Collect pylint output — we need to capture it.
        # run_lint prints to stdout; we re-run with subprocess to capture.
        result = subprocess.run(
            ["python", "-m", "python_setup_lint", "lint", "--no-fail-fast"],
            cwd=d,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout + result.stderr

        expected = _read_violations()
        missing = [p for p in expected if not _lint_output_contains_violation(output, p)]

        assert not missing, (
            f"Expected violations not found in pylint output:\n"
            f"  Missing patterns: {missing}\n"
            f"  Output:\n{output}"
        )


# ── Test: overlay config changes lint result ──────────────────────────


class TestOverlayConfig:
    """Verify that modifying config changes lint results."""

    def test_setup_given_overlay_config_then_lint_result_changes(
        self, tmp_path: Path
    ) -> None:
        """Edit configs and verify lint result changes accordingly."""
        d = tmp_path / "overlay"
        shutil.copytree(SAMPLE_PROJECT, d)
        _git_init(d)

        # Baseline: run lint and capture violations
        result_before = subprocess.run(
            ["python", "-m", "python_setup_lint", "lint", "--no-fail-fast"],
            cwd=d,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output_before = result_before.stdout + result_before.stderr

        # Add a pylintrc that disables the unnamed-tuple-dict checker
        pylintrc = d / ".pylintrc"
        pylintrc.write_text(
            textwrap.dedent("""\
            [MASTER]
            load-plugins=python_setup_lint.checkers

            [MESSAGES CONTROL]
            disable=unnamed-tuple-dict-value
        """)
        )

        # Re-run lint with the overlay config
        result_after = subprocess.run(
            [
                "python",
                "-m",
                "python_setup_lint",
                "lint",
                "--no-fail-fast",
                "--config",
                "pylint=.pylintrc",
            ],
            cwd=d,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output_after = result_after.stdout + result_after.stderr

        # The unnamed-tuple-dict violation should be present before, absent after
        pattern = "unnamed-tuple-dict-value"
        assert re.search(pattern, output_before, re.IGNORECASE), (
            f"Expected '{pattern}' in baseline output:\n{output_before}"
        )
        assert not re.search(pattern, output_after, re.IGNORECASE), (
            f"'{pattern}' should be suppressed by overlay config:\n{output_after}"
        )


# ── Test: resetup / update ────────────────────────────────────────────


class TestResetup:
    """Verify that update works on an already-installed project."""

    def test_resetup_given_existing_install_then_updates(self, tmp_path: Path) -> None:
        """Run install, then run update, verify it succeeds."""
        d = tmp_path / "resetup"
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
        _git_init(d)
        (d / ".secrets.baseline").write_text(
            '{"version":"1.0","plugins_used":[],"filters_used":[],'
            '"results":{},"generated_at":"2025-01-01T00:00:00Z"}\n'
        )
        (d / "tach.toml").write_text(
            '[[modules]]\npath = "src/consumer"\ndepends_on = []\n'
        )

        # First install
        rc = install(d, dev_path=str(Path.cwd()))
        assert rc == 0, f"first install failed with exit code {rc}"

        # Second install (idempotent)
        rc = install(d, dev_path=str(Path.cwd()))
        assert rc == 0, f"re-install failed with exit code {rc}"

        # Update
        rc = update(d)
        assert rc == 0, f"update failed with exit code {rc}"


# ── Test: pre-commit hooks dry run ────────────────────────────────────


class TestGitHooks:
    """Verify pre-commit hooks are correctly generated and valid."""

    def test_git_hooks_given_install_then_dry_run_works(self, tmp_path: Path) -> None:
        """Install, validate pre-commit config, run dry-run."""
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
        _git_init(d)
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

        # Dry-run: pre-commit run --all-files --dry-run
        result = subprocess.run(
            ["pre-commit", "run", "--all-files", "--dry-run"],
            cwd=d,
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Dry-run should succeed (exit 0) or report hooks would change files (exit 1)
        assert result.returncode in (0, 1), (
            f"pre-commit dry-run failed (exit {result.returncode}):\n"
            f"{result.stdout}\n{result.stderr}"
        )
        # Output should mention the hooks we expect
        assert "ruff-format" in result.stdout or "ruff" in result.stdout, (
            f"Expected ruff hooks in dry-run output:\n{result.stdout}"
        )
