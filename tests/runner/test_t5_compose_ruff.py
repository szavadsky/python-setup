"""Unit tests for T5 — ``_compose_ruff_config`` + ``RunnerConfig`` override fields.

Coverage mapping (envelope ``T5.envelope.md``):

* **surface-unit** — ``_compose_ruff_config`` banned-api + per-file-ignores
  copied; ``extend`` present; temp file written; no-override fast path
  returns shared path unchanged (no temp file)
* **surface-unit** — ``RunnerConfig`` new-field default-off (ps own run
  unchanged) + explicit-on wiring
* **private-complex-unit** — ``_load_pyproject_toml`` mtime-cache hit/miss
  + malformed-pyproject ``SystemExit`` fail-fast
* **downstream-integration** — ``run_lint`` consumes the two override
  fields; composed path lands in ``config_paths["ruff check"]`` and the
  pyright override overwrites ``config_paths["pyright check"]`` (verified
  via the dispatched command captured by a fake ``_run_cmd``).
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

import python_setup_lint.runner.output as _output_module
from python_setup_lint.runner import RunnerConfig, run_lint
from python_setup_lint.runner.cmd_build import _compose_ruff_config, _load_pyproject_toml
from python_setup_lint.testing import fake_run_cmd_factory

pytestmark = pytest.mark.no_external_api

# ── RunnerConfig default-off + explicit-on ──────────────────────


class TestRunnerConfigOverrideFields:
    """``RunnerConfig`` declares the two T5 override fields, both default off."""

    def test_runner_config_override_given_defaults_then_off(self, tmp_path: Path) -> None:
        cfg = RunnerConfig(cwd=tmp_path)
        assert cfg.ruff_project_overrides is False
        assert cfg.pyright_project_override is None

    def test_runner_config_override_given_explicit_then_on(self, tmp_path: Path) -> None:
        pyright_proj = tmp_path / "pyproject.toml"
        pyright_proj.write_text("[project]\nname = 'x'\n")
        cfg = RunnerConfig(
            cwd=tmp_path,
            ruff_project_overrides=True,
            pyright_project_override=pyright_proj,
        )
        assert cfg.ruff_project_overrides is True
        assert cfg.pyright_project_override == pyright_proj

    def test_runner_config_override_given_pyright_override_none_then_accepts(self, tmp_path: Path) -> None:
        cfg = RunnerConfig(cwd=tmp_path, pyright_project_override=None)
        assert cfg.pyright_project_override is None


# ── _compose_ruff_config surface ────────────────────────────────


def _write_pyproject_with_overrides(
    cwd: Path,
    *,
    banned_api: dict[str, str] | None = None,
    per_file_ignores: dict[str, list[str]] | None = None,
    extra_body: str = "",
) -> Path:
    """Write a ``pyproject.toml`` carrying the two project-specific stanzas."""
    pp = cwd / "pyproject.toml"
    parts: list[str] = ["[project]", "name = 'fixture'", ""]
    if banned_api or per_file_ignores:
        parts.append("[tool.ruff.lint]")
        if per_file_ignores:
            cells = ", ".join(
                f'"{pat}" = {codes}' for pat, codes in per_file_ignores.items()
            )
            parts.append(f"per-file-ignores = {{{cells}}}")
        if banned_api:
            parts.append("[tool.ruff.lint.flake8-tidy-imports]")
            for api, msg in banned_api.items():
                parts.append(f'banned-api."{api}" = {{ msg = "{msg}" }}')
        parts.append("")
    if extra_body:
        parts.append(extra_body)
    pp.write_text("\n".join(parts))
    return pp


class TestComposeRuffConfigNoOverride:
    """No-override fast path returns the shared path unchanged (no temp file)."""

    def test_compose_ruff_config_given_no_ruff_table_then_returns_shared(self, tmp_path: Path) -> None:
        shared = tmp_path / "shared_ruff.toml"
        shared.write_text("line-length = 130\n")
        pp = tmp_path / "pyproject.toml"
        pp.write_text("[project]\nname = 'no-ruff'\n")
        assert _compose_ruff_config(tmp_path, shared) == shared

    def test_compose_ruff_config_given_ruff_table_no_overrides_then_returns_shared(
        self, tmp_path: Path
    ) -> None:
        """Empty ``banned-api`` + empty ``per-file-ignores`` ⇒ no-override."""
        shared = tmp_path / "shared_ruff.toml"
        shared.write_text("line-length = 130\n")
        _write_pyproject_with_overrides(tmp_path, banned_api={}, per_file_ignores={})
        assert _compose_ruff_config(tmp_path, shared) == shared

    def test_compose_ruff_config_given_pyproject_missing_then_returns_shared(self, tmp_path: Path) -> None:
        shared = tmp_path / "shared_ruff.toml"
        shared.write_text("line-length = 130\n")
        # No pyproject.toml at cwd at all.
        assert _compose_ruff_config(tmp_path, shared) == shared

    def test_compose_ruff_config_given_fast_path_then_no_temp_file(self, tmp_path: Path) -> None:
        """The ``python_setup_lint_ruff_<cwd>`` temp dir must NOT be created."""
        shared = tmp_path / "shared_ruff.toml"
        shared.write_text("line-length = 130\n")
        _compose_ruff_config(tmp_path, shared)
        out_dir = _temp_root() / f"python_setup_lint_ruff_{tmp_path.name}"
        assert not out_dir.exists()


def _temp_root() -> Path:
    import tempfile

    return Path(tempfile.gettempdir())


class TestComposeRuffConfigWithOverrides:
    """With overrides, the composed temp ``ruff.toml`` carries extend + stanzas."""

    def test_compose_ruff_config_given_banned_api_then_composes(self, tmp_path: Path) -> None:
        shared = tmp_path / "shared_ruff.toml"
        shared.write_text("line-length = 130\n")
        _write_pyproject_with_overrides(
            tmp_path,
            banned_api={
                "consultant_mcp.config": "BOTTOM cannot import MID-BOTTOM (config)",
                "consultant_mcp.llm_proxy": "BOTTOM cannot import MID-BOTTOM (llm_proxy)",
            },
        )
        result = _compose_ruff_config(tmp_path, shared)
        assert result != shared
        assert result.is_file()
        text = result.read_text()
        # extend line points exactly at the shared config.
        assert f'extend = "{shared}"' in text
        assert "[lint.flake8-tidy-imports]" in text
        for api in ("consultant_mcp.config", "consultant_mcp.llm_proxy"):
            assert f'banned-api."{api}"' in text
        # per-file-ignores section absent when only banned-api provided.
        assert "[lint.per-file-ignores]" not in text

    def test_compose_ruff_config_given_per_file_ignores_then_composes(self, tmp_path: Path) -> None:
        shared = tmp_path / "shared_ruff.toml"
        shared.write_text("line-length = 130\n")
        _write_pyproject_with_overrides(
            tmp_path,
            per_file_ignores={
                "src/consultant_mcp/embedding/batch_config.py": ["TCH003"],
                "tests/data/**": ["SIM117", "B904"],
            },
        )
        result = _compose_ruff_config(tmp_path, shared)
        assert result != shared
        text = result.read_text()
        assert f'extend = "{shared}"' in text
        assert "[lint.per-file-ignores]" in text
        for pat, codes in (
            ("src/consultant_mcp/embedding/batch_config.py", ["TCH003"]),
            ("tests/data/**", ["SIM117", "B904"]),
        ):
            assert f'"{pat}" = {codes}' in text
        # banned-api section absent when only per-file-ignores provided.
        assert "[lint.flake8-tidy-imports]" not in text

    def test_compose_ruff_config_given_both_stanzas_then_composes(self, tmp_path: Path) -> None:
        shared = tmp_path / "shared_ruff.toml"
        shared.write_text("line-length = 130\n")
        _write_pyproject_with_overrides(
            tmp_path,
            banned_api={"foo.bar": "no import"},
            per_file_ignores={"src/x.py": ["F401"]},
        )
        result = _compose_ruff_config(tmp_path, shared)
        text = result.read_text()
        assert f'extend = "{shared}"' in text
        assert "[lint.flake8-tidy-imports]" in text
        assert 'banned-api."foo.bar"' in text
        assert "[lint.per-file-ignores]" in text
        assert "\"src/x.py\" = ['F401']" in text

    def test_compose_ruff_config_given_overrides_then_temp_file_in_dedicated_dir(self, tmp_path: Path) -> None:
        """Temp file lands under ``python_setup_lint_ruff_<cwd_name>/ruff.toml``."""
        cwd = _temp_root() / "t5_unique_cwd_xyz"
        cwd.mkdir(parents=True, exist_ok=True)
        try:
            shared = cwd / "shared_ruff.toml"
            shared.write_text("line-length = 130\n")
            _write_pyproject_with_overrides(cwd, banned_api={"a.b": "x"})
            result = _compose_ruff_config(cwd, shared)
            assert result.name == "ruff.toml"
            assert result.parent.name == f"python_setup_lint_ruff_{cwd.name}"
        finally:
            import shutil

            shutil.rmtree(cwd, ignore_errors=True)

    def test_compose_ruff_config_given_idempotent_then_overwrites(self, tmp_path: Path) -> None:
        shared = tmp_path / "shared_ruff.toml"
        shared.write_text("line-length = 130\n")
        _write_pyproject_with_overrides(tmp_path, banned_api={"a.b": "x"})
        first = _compose_ruff_config(tmp_path, shared)
        second = _compose_ruff_config(tmp_path, shared)
        assert first == second
        assert first.read_text() == second.read_text()


# ── _load_pyproject_toml cache + fail-fast ──────────────────────


class TestLoadPyprojectCache:
    """mtime-keyed cache + malformed-pyproject fail-fast (private-complex-unit)."""

    def test_load_pyproject_cache_given_cache_hit_then_avoids_restat(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Use a fresh cache so prior tests don't pollute.
        monkeypatch.setattr("python_setup_lint.runner.cmd_build._PYPROJECT_CACHE", {})
        pp = tmp_path / "pyproject.toml"
        pp.write_text("[project]\nname = 'x'\n")
        first = _load_pyproject_toml(pp)
        second = _load_pyproject_toml(pp)
        assert first is second  # cached — same dict instance
        assert first.get("project", {}).get("name") == "x"  # type: ignore[attr-defined]  # object-typed variable from release_messages()

    def test_load_pyproject_cache_given_mtime_change_then_cache_miss(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("python_setup_lint.runner.cmd_build._PYPROJECT_CACHE", {})
        pp = tmp_path / "pyproject.toml"
        pp.write_text("[project]\nname = 'x'\n")
        first = _load_pyproject_toml(pp)
        # Bump mtime past the filesystem's reported granularity.
        time.sleep(0.01)
        pp.write_text("[project]\nname = 'y'\n")
        os_utime(pp)
        second = _load_pyproject_toml(pp)
        assert first is not second
        assert second.get("project", {}).get("name") == "y"  # type: ignore[attr-defined]  # object-typed variable from release_messages()

    def test_load_pyproject_cache_given_missing_pyproject_then_empty(self, tmp_path: Path) -> None:
        """Missing file → empty dict (caller treats as no-override)."""
        missing = tmp_path / "does_not_exist.toml"
        assert _load_pyproject_toml(missing) == {}

    def test_load_pyproject_cache_given_malformed_pyproject_then_raises(self, tmp_path: Path) -> None:
        """Unparseable TOML → SystemExit (T8 fail-fast on malformed config)."""
        pp = tmp_path / "pyproject.toml"
        pp.write_text("[[[invalid toml")
        with pytest.raises(SystemExit) as exc:
            _load_pyproject_toml(pp)
        assert "malformed or unreadable" in str(exc.value)


def os_utime(path: Path) -> None:
    """Force-update mtime so st_mtime_ns differs across filesystems."""
    import os

    now = time.time()
    os.utime(path, (now, now))


# ── run_lint consumes the declarative override fields ───────────


class TestRunLintConsumesOverrides:
    """``run_lint`` applies ``ruff_project_overrides`` + ``pyright_project_override``."""

    def _config_with_overrides(
        self,
        tmp_path: Path,
    ) -> RunnerConfig:
        shared = tmp_path / "shared_ruff.toml"
        shared.write_text("line-length = 130\n")
        _write_pyproject_with_overrides(
            tmp_path,
            banned_api={"fixture.foo": "no import"},
        )
        pyright_proj = tmp_path / "pyproject.toml"
        return RunnerConfig(
            cwd=tmp_path,
            ruff_project_overrides=True,
            pyright_project_override=pyright_proj,
            config_paths={
                "ruff check": shared,
                "pyright check": tmp_path / "shared_pyrightconfig.json",
            },
        )

    def test_run_lint_consumes_overrides_given_ruff_then_config_replaced(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """After ``run_lint``, ``config.config_paths["ruff check"]`` ≠ shared."""
        config = self._config_with_overrides(tmp_path)
        shared_before = config.config_paths["ruff check"]  # type: ignore[index]  # config_paths is dict[str, Path]; index access is valid at runtime
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_output_module, "_run_cmd", fake)
        run_lint(config=config)
        assert config.config_paths["ruff check"] != shared_before  # type: ignore[index]  # config_paths is dict[str, Path]; index access is valid at runtime
        assert "python_setup_lint_ruff_" in str(config.config_paths["ruff check"])  # type: ignore[index]  # config_paths is dict[str, Path]; index access is valid at runtime

    def test_run_lint_consumes_overrides_given_pyright_then_config_replaced(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config = self._config_with_overrides(tmp_path)
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_output_module, "_run_cmd", fake)
        run_lint(config=config)
        assert config.config_paths["pyright check"] == tmp_path / "pyproject.toml"  # type: ignore[index]  # config_paths is dict[str, Path]; index access is valid at runtime

    def test_run_lint_consumes_overrides_given_ruff_then_command_uses_composed_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The ruff ``--config`` flag points at the composed path."""
        config = self._config_with_overrides(tmp_path)
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_output_module, "_run_cmd", fake)
        run_lint(config=config)
        ruff_rec = next((r for r in fake.calls if r.cmd[:2] == ["ruff", "check"]), None)
        assert ruff_rec is not None, (
            f"ruff check was not dispatched; calls={[r.cmd[:2] for r in fake.calls[:3]]}"
        )
        cfg_idx = ruff_rec.cmd.index("--config")
        assert "python_setup_lint_ruff_" in ruff_rec.cmd[cfg_idx + 1]

    def test_run_lint_consumes_overrides_given_pyright_then_command_uses_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The pyright ``--project`` flag points at the override path."""
        config = self._config_with_overrides(tmp_path)
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_output_module, "_run_cmd", fake)
        run_lint(config=config)
        pyright_rec = next((r for r in fake.calls if r.cmd[:1] == ["pyright"]), None)
        assert pyright_rec is not None, (
            f"pyright not dispatched; calls={[r.cmd[:2] for r in fake.calls[:3]]}"
        )
        # ``pyright check`` (generic ``_build_command``) lands ``--project``
        # after ``--outputjson``; the override replaced the shipped
        # ``config_paths["pyright check"]`` value.
        check_idx = pyright_rec.cmd.index("--project")
        assert pyright_rec.cmd[check_idx + 1] == str(tmp_path / "pyproject.toml")

    def test_run_lint_consumes_overrides_given_fields_off_then_no_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With defaults off, ``config_paths`` stays untouched (regress-preserved)."""
        shared = tmp_path / "shared_ruff.toml"
        shared.write_text("line-length = 130\n")
        pyright_ship = tmp_path / "pyrightconfig.json"
        pyright_ship.write_text("{}")
        config = RunnerConfig(
            cwd=tmp_path,
            config_paths={"ruff check": shared, "pyright check": pyright_ship},
        )
        snapshot_ruff = config.config_paths["ruff check"]  # type: ignore[index]  # config_paths is dict[str, Path]; index access is valid at runtime
        snapshot_pyright = config.config_paths["pyright check"]  # type: ignore[index]  # config_paths is dict[str, Path]; index access is valid at runtime
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_output_module, "_run_cmd", fake)
        run_lint(config=config)
        assert config.config_paths["ruff check"] == snapshot_ruff  # type: ignore[index]  # config_paths is dict[str, Path]; index access is valid at runtime
        assert config.config_paths["pyright check"] == snapshot_pyright  # type: ignore[index]  # config_paths is dict[str, Path]; index access is valid at runtime
