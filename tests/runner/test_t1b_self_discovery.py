"""Unit tests for T1b self-discovery helpers.

Covers ``_default_config_paths`` and ``_infer_package_name`` as pure
functions, plus the yamllint ``_config_flag_for`` entry.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from python_setup_lint.runner._config import _default_config_paths, _infer_package_name
from python_setup_lint.runner.cmd_build import _config_flag_for


class TestDefaultConfigPaths:
    """``_default_config_paths(cwd)`` resolves shipped config files."""

    def _make_fake_package(self, tmp_path: Path, config_files: list[str]) -> Path:
        """Create a fake python_setup_lint package with a config/ dir.

        Returns the path to the fake ``__init__.py`` so callers can
        monkeypatch ``python_setup_lint.__file__``.
        """
        pkg_dir = tmp_path / "python_setup_lint"
        pkg_dir.mkdir(parents=True)
        init = pkg_dir / "__init__.py"
        init.write_text("")
        config_dir = pkg_dir / "config"
        config_dir.mkdir()
        for fname in config_files:
            (config_dir / fname).write_text("")
        return init

    def test_default_config_paths_given_shipped_configs_then_returns_all(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """When config dir has all shipped files, returns all labels."""
        import python_setup_lint

        init = self._make_fake_package(
            tmp_path,
            [
                "ruff.toml",
                "mypy.ini",
                ".pylintrc",
                "pyrightconfig.json",
                "rumdl.toml",
                "ty.toml",
                ".yamllint",
            ],
        )
        monkeypatch.setattr(python_setup_lint, "__file__", str(init))
        result = _default_config_paths(Path.cwd())
        expected_labels = {
            "ruff check",
            "mypy",
            "pylint",
            "pyright check",
            "rumdl check",
            "ty check",
            "yamllint",
        }
        assert expected_labels.issubset(result.keys()), (
            f"Missing shipped configs. Got: {set(result)}"
        )
        for label, path in result.items():
            assert path.is_file(), f"Config {label} -> {path} does not exist"

    def test_default_config_paths_given_yamllint_config_then_present(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """yamllint shipped config is discovered."""
        import python_setup_lint

        init = self._make_fake_package(tmp_path, [".yamllint"])
        monkeypatch.setattr(python_setup_lint, "__file__", str(init))
        result = _default_config_paths(Path.cwd())
        assert "yamllint" in result
        assert result["yamllint"].name == ".yamllint"

    def test_default_config_paths_given_package_not_installed_then_empty(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """When ``python_setup_lint.__file__`` is ``None``, returns empty dict."""
        import python_setup_lint

        monkeypatch.setattr(python_setup_lint, "__file__", None)
        result = _default_config_paths(tmp_path)
        assert result == {}

    def test_default_config_paths_given_config_dir_missing_then_empty(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """When the config dir does not exist, returns empty dict."""
        import python_setup_lint

        # Point __file__ to a fake location with no config/ sibling.
        fake_pkg = tmp_path / "python_setup_lint" / "__init__.py"
        fake_pkg.parent.mkdir(parents=True)
        fake_pkg.write_text("")
        monkeypatch.setattr(python_setup_lint, "__file__", str(fake_pkg))
        result = _default_config_paths(tmp_path)
        assert result == {}


class TestInferPackageName:
    """``_infer_package_name(cwd)`` reads pyproject.toml hatch packages."""

    def test_infer_package_name_given_hatch_packages_then_infers(self, tmp_path: Path) -> None:
        """Strips ``src/`` prefix from hatch packages[0]."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""\
[tool.hatch.build.targets.wheel]
packages = ["src/python_setup_lint"]
""")
        assert _infer_package_name(tmp_path) == "python_setup_lint"

    def test_infer_package_name_given_no_src_prefix_then_infers(self, tmp_path: Path) -> None:
        """Returns raw package name when no ``src/`` prefix."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""\
[tool.hatch.build.targets.wheel]
packages = ["my_package"]
""")
        assert _infer_package_name(tmp_path) == "my_package"

    def test_infer_package_name_given_no_pyproject_then_none(self, tmp_path: Path) -> None:
        """Returns ``None`` when pyproject.toml is missing."""
        assert _infer_package_name(tmp_path) is None

    def test_infer_package_name_given_no_hatch_table_then_none(self, tmp_path: Path) -> None:
        """Returns ``None`` when hatch table is absent."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("[project]\nname = 'foo'\n")
        assert _infer_package_name(tmp_path) is None

    def test_infer_package_name_given_empty_packages_then_none(self, tmp_path: Path) -> None:
        """Returns ``None`` when packages list is empty."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("""\
[tool.hatch.build.targets.wheel]
packages = []
""")
        assert _infer_package_name(tmp_path) is None

    def test_infer_package_name_given_malformed_toml_then_none(self, tmp_path: Path) -> None:
        """Returns ``None`` on unparseable pyproject.toml."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("[[[invalid toml")
        assert _infer_package_name(tmp_path) is None


class TestYamllintConfigFlag:
    """``_config_flag_for`` returns yamllint ``--config-file``."""

    def test_config_flag_for_given_yamllint_then_returns_flag(self) -> None:
        """yamllint entry produces ``--config-file <path>``."""
        path = Path("/some/config/.yamllint")
        result = _config_flag_for("yamllint", path)
        assert result == ["--config-file", str(path)]

    def test_config_flag_for_given_yamllint_none_then_none(self) -> None:
        """Returns empty list when config_path is None."""
        assert _config_flag_for("yamllint", None) == []

    def test_config_flag_for_given_other_tool_then_unaffected(self) -> None:
        """Adding yamllint does not break existing entries."""
        path = Path("/cfg/ruff.toml")
        assert _config_flag_for("ruff check", path) == ["--config", str(path)]
