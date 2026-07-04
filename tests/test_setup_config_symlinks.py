"""Unit tests for ``_step_config_symlinks`` in ``python_setup_lint.setup``."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from python_setup_lint.setup import (
    _BUNDLED_CONFIGS,
    SetupState,
    _step_config_symlinks,
)

# ── Helpers ──────────────────────────────────────────────────────────


def _s_fake_pkg(d: Path, mp: pytest.MonkeyPatch) -> Path:
    """Create a fake package dir with ``config/`` subdir containing bundled config files.

    Returns the fake package dir path.
    """
    import python_setup_lint.setup as _m

    fake = d / "fake-pkg"
    fake.mkdir()
    config_dir = fake / "config"
    config_dir.mkdir()

    for fname in _BUNDLED_CONFIGS:
        (config_dir / fname).write_text(f"# {fname} content\n")

    mp.setattr(_m, "_get_package_dir", lambda: fake)
    return fake


# ── Tests ────────────────────────────────────────────────────────────


class TestConfigSymlinks:
    """Tests for ``_step_config_symlinks``."""

    def test_creates_symlinks(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Given a fake project dir and fake package dir with config files,
        calling _step_config_symlinks should create symlinks at the project root.
        """
        _s_fake_pkg(tmp_path, monkeypatch)
        state = SetupState()

        _step_config_symlinks(state, tmp_path)

        assert state.config_symlinks_created == len(_BUNDLED_CONFIGS)
        assert state.config_symlinks_skipped == 0

        for fname in _BUNDLED_CONFIGS:
            target = tmp_path / fname
            assert target.is_symlink(), f"{fname} should be a symlink"
            source = tmp_path / "fake-pkg" / "config" / fname
            assert target.resolve() == source.resolve(), (
                f"{fname} should point to {source}"
            )

    def test_skip_if_symlink_exists_and_matches(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If a symlink already exists pointing to the right source, it should be skipped."""
        _s_fake_pkg(tmp_path, monkeypatch)
        state = SetupState()

        # Create a matching symlink for the first config file
        fname = _BUNDLED_CONFIGS[0]
        source = tmp_path / "fake-pkg" / "config" / fname
        target = tmp_path / fname
        target.symlink_to(str(source.resolve()))

        _step_config_symlinks(state, tmp_path)

        assert state.config_symlinks_skipped >= 1
        assert state.config_symlinks_created == len(_BUNDLED_CONFIGS) - 1

    def test_skip_if_content_matches(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If a regular file exists with matching content, it should be skipped."""
        _s_fake_pkg(tmp_path, monkeypatch)
        state = SetupState()

        # Create a regular file with matching content for the first config file
        fname = _BUNDLED_CONFIGS[0]
        source = tmp_path / "fake-pkg" / "config" / fname
        target = tmp_path / fname
        target.write_text(source.read_text())

        _step_config_symlinks(state, tmp_path)

        assert state.config_symlinks_skipped >= 1
        assert state.config_symlinks_created == len(_BUNDLED_CONFIGS) - 1
        # Should remain a regular file, not a symlink
        assert not target.is_symlink()

    def test_skip_tach_toml_if_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """tach.toml should be skipped if it already exists (even if content differs)."""
        _s_fake_pkg(tmp_path, monkeypatch)
        state = SetupState()

        # Create tach.toml with different content
        target = tmp_path / "tach.toml"
        target.write_text("different content")

        _step_config_symlinks(state, tmp_path)

        assert state.config_symlinks_skipped >= 1
        # tach.toml should not be a symlink
        assert not target.is_symlink()
        # Content should remain unchanged
        assert target.read_text() == "different content"

    def test_fallback_to_copy_on_symlink_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If os.symlink raises OSError, it should fall back to shutil.copy2."""
        _s_fake_pkg(tmp_path, monkeypatch)
        state = SetupState()

        # Monkey-patch os.symlink to raise OSError
        def failing_symlink(src: str, dst: str, **kwargs: object) -> None:
            raise OSError(1, "Operation not permitted")

        monkeypatch.setattr(os, "symlink", failing_symlink)

        _step_config_symlinks(state, tmp_path)

        assert state.config_symlinks_created == len(_BUNDLED_CONFIGS)
        assert state.config_symlinks_skipped == 0

        for fname in _BUNDLED_CONFIGS:
            target = tmp_path / fname
            assert target.exists(), f"{fname} should exist"
            # Should be a regular file (copy), not a symlink
            assert not target.is_symlink(), f"{fname} should be a copy, not a symlink"
            source = tmp_path / "fake-pkg" / "config" / fname
            assert target.read_bytes() == source.read_bytes(), (
                f"{fname} content should match"
            )

    def test_s_fake_pkg_creates_config_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_s_fake_pkg must create a config/ subdir with bundled config files
        so the step doesn't silently produce 0/0.
        """
        _s_fake_pkg(tmp_path, monkeypatch)
        config_dir = tmp_path / "fake-pkg" / "config"
        assert config_dir.is_dir()
        for fname in _BUNDLED_CONFIGS:
            assert (config_dir / fname).is_file(), (
                f"{fname} should exist in config/"
            )

    def test_works_with_real_bundled_configs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The step should work with the real bundled configs
        (not _BUNDLED_CONFIGS=()).
        """
        _s_fake_pkg(tmp_path, monkeypatch)
        state = SetupState()

        _step_config_symlinks(state, tmp_path)

        # Must create symlinks with the real bundled configs, not an empty tuple
        assert state.config_symlinks_created > 0, (
            "Should create symlinks with real bundled configs"
        )
        assert state.config_symlinks_created == len(_BUNDLED_CONFIGS)
