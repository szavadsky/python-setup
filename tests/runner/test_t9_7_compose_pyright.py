"""Unit + integration tests for T9.7 — ``_compose_pyright_config`` + ``run_lint`` pyright wire.

Coverage mapping (envelope ``T9.7.envelope.md``):

* **surface-unit** — ``_compose_pyright_config`` writes a verbatim copy to
  ``cwd/.pyrightconfig-composed.json`` (no path rewriting); no-rewrite fast
  path returns the shared path unchanged when the config already lives in cwd
  (no file written); read-only cwd falls back to returning shared config.
* **private-complex-unit** — the helper's "passthrough on unreadable file /
  passthrough on non-JSON file" branches.
* **downstream-integration** — ``run_lint`` with no consumer opt-in
  (``pyright_project_override is None``) composes the pyright config in cwd
  and dispatches the composed path via ``--project`` (verified via a
  fake ``_run_cmd`` capturing the constructed command); consumer opt-in
  (``pyright_project_override`` set) still takes precedence over the new default
  compose path (T5 regression-preserving).
* **regress-pass-preserved** — ``tests/runner/test_t1b_self_discovery.py::
  TestDefaultConfigPaths`` unaffected (the compose helper doesn't touch config
  discovery); ruff-compose wire + ruff/pyright override fields still work.
* **downstream-integration (live)** — see ``test_t9_7_compose_pyright_live.py``.
* **observability** — the live smoke records ``summary`` + ``.venv`` diagnostic
  count + the raw constructed command in the per-test artifact dir.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import python_setup_lint.runner.output as _output_module
from python_setup_lint.runner import RunnerConfig, run_lint
from python_setup_lint.runner.cmd_build import _compose_pyright_config
from python_setup_lint.testing import fake_run_cmd_factory

pytestmark = pytest.mark.no_external_api

# ── _compose_pyright_config surface-unit ─────────────────────────


def _write_shipped_config(path: Path, *, body: str) -> Path:
    """Write a hand-authored shipped ``pyrightconfig.json`` body to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


_SHIPPED_BODY = (
    "{\n"
    '    "venvPath": ".",\n'
    '    "venv": ".venv",\n'
    '    "reportAttributeAccessIssue": "none",\n'
    '    "exclude": [\n'
    '        ".venv",\n'
    '        "**/__pycache__",\n'
    '        "**/node_modules",\n'
    '        "**/.*",\n'
    '        "build/",\n'
    '        "tests/data/"\n'
    "    ]\n"
    "}\n"
)


class TestComposePyrightConfigNoRewrite:
    """No-rewrite fast paths return *shared_config* unchanged (no file written)."""

    def test_returns_shared_when_config_already_in_cwd(self, tmp_path: Path) -> None:
        """Config already in cwd ⇒ returned unchanged regardless of path absoluteness."""
        shared = tmp_path / "shared_pyrightconfig.json"
        shared.write_text(
            json.dumps(
                {
                    "venvPath": str(tmp_path),
                    "exclude": [str(tmp_path / ".venv"), str(tmp_path / "build")],
                }
            )
        )
        # shared is in tmp_path, which IS cwd → fast path.
        assert _compose_pyright_config(tmp_path, shared) == shared

    def test_returns_shared_when_no_venvpath_no_exclude(self, tmp_path: Path) -> None:
        """Config in cwd with neither ``venvPath`` nor ``exclude`` ⇒ returned unchanged."""
        shared = tmp_path / "shared_pyrightconfig.json"
        shared.write_text(json.dumps({"venv": ".venv"}))
        # shared is in tmp_path (cwd) → fast path.
        assert _compose_pyright_config(tmp_path, shared) == shared

    def test_compose_pyright_config_given_unreadable_file_then_returns_shared(self, tmp_path: Path) -> None:
        """Missing or unreadable shipped config ⇒ shared returned unchanged."""
        shared = tmp_path / "does_not_exist.json"
        # The helper must not crash the runner; pyright surfaces the missing
        # config downstream, preserving the prior tool-dispatch behaviour.
        assert _compose_pyright_config(tmp_path, shared) == shared

    def test_compose_pyright_config_given_non_json_mapping_then_returns_shared(self, tmp_path: Path) -> None:
        """A pyright ``--project`` pointed at a non-JSON config (e.g. a
        ``pyproject.toml`` override target) is passed through verbatim."""
        shared = tmp_path / "pyproject.toml"
        shared.write_text("[project]\nname = 'x'\n")
        assert _compose_pyright_config(tmp_path, shared) == shared
        shared_json_array = tmp_path / "array.json"
        shared_json_array.write_text("[]")
        assert _compose_pyright_config(tmp_path, shared_json_array) == shared_json_array

    def test_no_temp_file_written_on_fast_path(self, tmp_path: Path) -> None:
        """Config in cwd ⇒ no ``.pyrightconfig-composed.json`` written."""
        shared = tmp_path / "shared_pyrightconfig.json"
        shared.write_text("{}")
        _compose_pyright_config(tmp_path, shared)
        assert not (tmp_path / ".pyrightconfig-composed.json").exists()


class TestComposePyrightConfigCopiesToCwd:
    """Config outside cwd gets copied verbatim to ``cwd/.pyrightconfig-composed.json``."""

    def _assert_in_cwd(self, path: Path, cwd: Path) -> None:
        """Assert *path* is ``cwd / ".pyrightconfig-composed.json"``."""
        assert path == cwd / ".pyrightconfig-composed.json", f"{path} not in cwd"

    def test_composed_is_verbatim_copy(self, tmp_path: Path) -> None:
        """Composed file content is identical to the shipped config (no rewriting)."""
        shared = _write_shipped_config(tmp_path / "shared", body=_SHIPPED_BODY)
        cwd = tmp_path / "project"
        cwd.mkdir()
        composed = _compose_pyright_config(cwd, shared)
        self._assert_in_cwd(composed, cwd)
        assert composed.read_text() == shared.read_text()

    def test_composed_in_cwd_not_tempdir(self, tmp_path: Path) -> None:
        """Composed file lands in cwd, not a temp directory."""
        shared = _write_shipped_config(tmp_path / "shared", body=_SHIPPED_BODY)
        cwd = tmp_path / "project"
        cwd.mkdir()
        composed = _compose_pyright_config(cwd, shared)
        self._assert_in_cwd(composed, cwd)
        assert composed.is_file()

    def test_no_temp_file_in_tempdir(self, tmp_path: Path) -> None:
        """No tempfile.mkdtemp directory is created — composed goes straight to cwd."""
        shared = _write_shipped_config(tmp_path / "shared", body=_SHIPPED_BODY)
        cwd = tmp_path / "project"
        cwd.mkdir()
        _compose_pyright_config(cwd, shared)
        # The composed file is in cwd, not in a temp directory.
        assert (cwd / ".pyrightconfig-composed.json").is_file()

    def test_read_only_cwd_falls_back_to_shared(self, tmp_path: Path) -> None:
        """Read-only cwd (write_text raises OSError) ⇒ returns shared_config unchanged."""
        shared = _write_shipped_config(tmp_path / "shared", body=_SHIPPED_BODY)
        cwd = tmp_path / "project"
        cwd.mkdir()
        # Make cwd read-only so write_text fails.
        cwd.chmod(0o444)
        try:
            result = _compose_pyright_config(cwd, shared)
            assert result == shared
        finally:
            cwd.chmod(0o755)  # restore for cleanup

    def test_output_is_valid_json(self, tmp_path: Path) -> None:
        """The composed file is JSON-parseable (pyright requires JSON)."""
        shared = _write_shipped_config(tmp_path / "shared", body=_SHIPPED_BODY)
        cwd = tmp_path / "project"
        cwd.mkdir()
        composed = _compose_pyright_config(cwd, shared)
        # Must parse without error.
        json.loads(composed.read_text())


# ── run_lint consumers the new default compose path ─────────────


class TestRunLintConsumesPyrightDefaultCompose:
    """``run_lint`` with ``pyright_project_override is None`` composes a cwd config.

    Symmetric with the existing ruff compose block; replaces
    ``config.config_paths["pyright check"]`` with the composed path before
    the tool dispatch loop constructs the pyright command.
    """

    def _config_with_shipped(self, tmp_path: Path) -> RunnerConfig:
        shipped = _write_shipped_config(tmp_path / "shared" / "pyrightconfig.json", body=_SHIPPED_BODY)
        return RunnerConfig(
            cwd=tmp_path,
            tools_override=["pyright check"],
            config_paths={"pyright check": shipped},
        )

    def test_run_lint_pyright_compose_given_default_then_config_replaced(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """After ``run_lint``, ``config.config_paths["pyright check"]`` ≠ shipped."""
        config = self._config_with_shipped(tmp_path)
        shipped_before = config.config_paths["pyright check"]  # type: ignore[index]  # config_paths is dict[str, Path]; index access is valid at runtime
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_output_module, "_run_cmd", fake)
        run_lint(config=config)
        composed = config.config_paths["pyright check"]  # type: ignore[index]  # config_paths is dict[str, Path]; index access is valid at runtime
        assert composed != shipped_before
        assert composed == tmp_path / ".pyrightconfig-composed.json"
        assert (tmp_path / ".pyrightconfig-composed.json").exists()

    def test_run_lint_pyright_compose_given_default_then_command_uses_composed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The pyright ``--project`` flag points at the composed path."""
        config = self._config_with_shipped(tmp_path)
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_output_module, "_run_cmd", fake)
        run_lint(config=config)
        pyright_rec = next((r for r in fake.calls if r.cmd[:1] == ["pyright"]), None)
        assert pyright_rec is not None, f"pyright not dispatched; calls={[r.cmd[:2] for r in fake.calls[:3]]}"
        proj_idx = pyright_rec.cmd.index("--project")
        composed_path = pyright_rec.cmd[proj_idx + 1]
        assert composed_path == str(tmp_path / ".pyrightconfig-composed.json")
        assert Path(composed_path).is_file()
        assert (tmp_path / ".pyrightconfig-composed.json").exists()

    def test_run_lint_pyright_compose_given_override_set_then_no_compose(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Consumer opt-in (``pyright_project_override``) wins over the default compose."""
        config = self._config_with_shipped(tmp_path)
        override = tmp_path / "pyproject.toml"
        override.write_text("[project]\nname = 'x'\n")
        config.pyright_project_override = override
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_output_module, "_run_cmd", fake)
        run_lint(config=config)
        # Override takes precedence — config_paths now points at the override.
        assert config.config_paths["pyright check"] == override  # type: ignore[index]  # config_paths is dict[str, Path]; index access is valid at runtime
        # And the dispatched cmd uses the override, not a composed path.
        pyright_rec = next((r for r in fake.calls if r.cmd[:1] == ["pyright"]), None)
        assert pyright_rec is not None
        proj_idx = pyright_rec.cmd.index("--project")
        assert pyright_rec.cmd[proj_idx + 1] == str(override)

    def test_run_lint_pyright_compose_given_no_config_entry_then_no_compose(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No ``pyright check`` entry in ``config_paths`` => no compose, no KeyError."""
        config = RunnerConfig(
            cwd=tmp_path,
            tools_override=["pyright check"],
            config_paths={"ruff check": tmp_path / "ruff.toml"},
        )
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_output_module, "_run_cmd", fake)
        run_lint(config=config)
        # No composed pyright config written.
        assert "pyright check" not in config.config_paths  # type: ignore[operator]  # config_paths is dict[str, Path]; 'in' check is valid at runtime
        assert not (tmp_path / ".pyrightconfig-composed.json").exists()

    def test_run_lint_pyright_compose_given_ruff_wire_then_preserves(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """T5 ruff-overrides wire + the new pyright wire can both fire in a single run."""
        shared_ruff = tmp_path / "shared_ruff.toml"
        shared_ruff.write_text("line-length = 130\n")
        pp = tmp_path / "pyproject.toml"
        pp.write_text('[project]\nname = "x"\n[tool.ruff.lint.flake8-tidy-imports]\nbanned-api."foo.bar" = { msg = "no" }\n')
        pyright_shipped = _write_shipped_config(tmp_path / "shared" / "pyrightconfig.json", body=_SHIPPED_BODY)
        config = RunnerConfig(
            cwd=tmp_path,
            ruff_project_overrides=True,
            tools_override=["ruff check", "pyright check"],
            config_paths={
                "ruff check": shared_ruff,
                "pyright check": pyright_shipped,
            },
        )
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_output_module, "_run_cmd", fake)
        run_lint(config=config)
        # Both composed paths land.
        assert "python_setup_lint_ruff_" in str(config.config_paths["ruff check"])  # type: ignore[index]  # config_paths is dict[str, Path]; index access is valid at runtime
        composed_pyright = config.config_paths["pyright check"]  # type: ignore[index]  # config_paths is dict[str, Path]; index access is valid at runtime
        assert composed_pyright == tmp_path / ".pyrightconfig-composed.json"
        assert (tmp_path / ".pyrightconfig-composed.json").exists()
