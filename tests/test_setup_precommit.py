"""Unit tests for the ruff version resolution logic in ``_step_precommit``.

These tests mock ``shutil.which`` and ``subprocess.run`` to control the ruff
version output and verify the correct ``rev`` is interpolated into the
pre-commit config template.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from python_setup_lint._setup_precommit import (
    _PRECOMMIT_TEMPLATE,
    _RUFF_FALLBACK_REV,
    _step_precommit,
)
from python_setup_lint.setup import SetupState

# ── Helpers ────────────────────────────────────────────────────────────


def _make_mock_run(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    """Build a ``CompletedProcess`` that mimics ``ruff --version`` output."""
    return subprocess.CompletedProcess(
        args=["ruff", "--version"],
        returncode=returncode,
        stdout=stdout,
        stderr="",
    )


def _read_precommit(project_dir: Path) -> str:  # pylint: disable=trivial-wrapper  # test helper for readability
    """Read the written pre-commit config, stripping trailing whitespace per line."""
    return (project_dir / ".pre-commit-config.yaml").read_text()


def _assert_rev_in_config(content: str, expected_rev: str) -> None:
    """Assert the config contains the expected ``rev: <expected_rev>`` line."""
    expected_line = f"    rev: {expected_rev}"
    assert expected_line in content, (
        f"Expected rev line {expected_line!r} not found in:\n{content}"
    )


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def state() -> SetupState:  # pylint: disable=trivial-wrapper  # test helper for readability
    """Fresh ``SetupState`` for each test."""
    return SetupState()


# ── Tests ─────────────────────────────────────────────────────────────


class TestRuffVersionResolution:  # pylint: disable=redefined-outer-name  # fixture parameter shadows module-level state fixture
    """Unit tests for the ruff version resolution in ``_step_precommit``."""

    def test_normal_version(
        self,
        tmp_path: Path,
        state: SetupState,
    ) -> None:
        """Normal ruff version output ``ruff 0.15.17`` → ``rev: v0.15.17``."""
        mock_run = _make_mock_run("ruff 0.15.17\n")

        with (
            patch("shutil.which", return_value="/usr/bin/ruff"),
            patch("subprocess.run", return_value=mock_run),
        ):
            _step_precommit(state, tmp_path)

        content = _read_precommit(tmp_path)
        _assert_rev_in_config(content, "v0.15.17")
        assert state.precommit_written

    def test_version_with_v_prefix(
        self,
        tmp_path: Path,
        state: SetupState,
    ) -> None:
        """Version output ``ruff v0.15.17`` → ``rev: v0.15.17`` (no double v)."""
        mock_run = _make_mock_run("ruff v0.15.17\n")

        with (
            patch("shutil.which", return_value="/usr/bin/ruff"),
            patch("subprocess.run", return_value=mock_run),
        ):
            _step_precommit(state, tmp_path)

        content = _read_precommit(tmp_path)
        _assert_rev_in_config(content, "v0.15.17")
        assert state.precommit_written

    def test_file_not_found_fallback(
        self,
        tmp_path: Path,
        state: SetupState,
    ) -> None:
        """``FileNotFoundError`` when ruff is not installed → fallback rev."""
        with (
            patch("shutil.which", return_value="/usr/bin/ruff"),
            patch("subprocess.run", side_effect=FileNotFoundError()),
        ):
            _step_precommit(state, tmp_path)

        content = _read_precommit(tmp_path)
        _assert_rev_in_config(content, _RUFF_FALLBACK_REV)
        assert state.precommit_written

    def test_non_zero_returncode_fallback(
        self,
        tmp_path: Path,
        state: SetupState,
    ) -> None:
        """Non-zero returncode from ``ruff --version`` → fallback rev."""
        mock_run = _make_mock_run("", returncode=1)

        with (
            patch("shutil.which", return_value="/usr/bin/ruff"),
            patch("subprocess.run", return_value=mock_run),
        ):
            _step_precommit(state, tmp_path)

        content = _read_precommit(tmp_path)
        _assert_rev_in_config(content, _RUFF_FALLBACK_REV)
        assert state.precommit_written

    def test_ruff_not_on_path_fallback(
        self,
        tmp_path: Path,
        state: SetupState,
    ) -> None:
        """``shutil.which`` returns ``None`` (ruff not on PATH) → fallback rev."""
        with patch("shutil.which", return_value=None):
            _step_precommit(state, tmp_path)

        content = _read_precommit(tmp_path)
        _assert_rev_in_config(content, _RUFF_FALLBACK_REV)
        assert state.precommit_written

    def test_existing_config_skips(
        self,
        tmp_path: Path,
        state: SetupState,
    ) -> None:
        """If ``.pre-commit-config.yaml`` already exists, the step is skipped."""
        (tmp_path / ".pre-commit-config.yaml").write_text("existing content\n")

        _step_precommit(state, tmp_path)

        content = _read_precommit(tmp_path)
        assert content == "existing content\n"
        assert state.precommit_skipped
        assert not state.precommit_written

    def test_template_format(
        self,
        tmp_path: Path,
        state: SetupState,
    ) -> None:
        """Verify the written config matches the template format with a known rev."""
        mock_run = _make_mock_run("ruff 1.2.3\n")

        with (
            patch("shutil.which", return_value="/usr/bin/ruff"),
            patch("subprocess.run", return_value=mock_run),
        ):
            _step_precommit(state, tmp_path)

        content = _read_precommit(tmp_path)
        expected = _PRECOMMIT_TEMPLATE.format(ruff_rev="v1.2.3")
        assert content == expected
