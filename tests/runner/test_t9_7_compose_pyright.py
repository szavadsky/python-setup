"""Unit + integration tests for T9.7 — ``_compose_pyright_config`` + ``run_lint`` pyright wire.

Coverage mapping (envelope ``T9.7.envelope.md``):

* **surface-unit** — ``_compose_pyright_config`` absolute ``venvPath`` rewrite +
  every relative ``exclude`` rewritten to absolute ``cwd``-rooted; no-rewrite
  fast path returns the shared path unchanged (no temp file written); idempotent
  over-write; tmp file lands under
  ``tempfile.gettempdir() / "python_setup_lint_pyright_{cwd_name}"``.
* **private-complex-unit** — the helper's "rewrite only relative entries /
  passthrough on absolute / passthrough on JSON-decode failure / passthrough on
  unreadable file" branches.
* **downstream-integration** — ``run_lint`` with no consumer opt-in
  (``pyright_project_override is None``) composes the tmp pyright config and
  dispatches the composed path via ``--project`` (verified via a fake
  ``_run_cmd`` capturing the constructed command); consumer opt-in
  (``pyright_project_override`` set) still takes precedence over the new
  default compose path (T5 regression-preserving).
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
    """No-rewrite fast paths return *shared_config* unchanged (no temp file)."""

    def test_returns_shared_when_venvpath_and_exclude_already_absolute(
        self, tmp_path: Path
    ) -> None:
        """Already-absolute ``venvPath`` + absolute ``exclude`` ⇒ no rewrite."""
        shared = tmp_path / "shared_pyrightconfig.json"
        shared.write_text(
            json.dumps(
                {
                    "venvPath": str(tmp_path),
                    "exclude": [str(tmp_path / ".venv"), str(tmp_path / "build")],
                }
            )
        )
        cwd = tmp_path / "project"
        cwd.mkdir()
        assert _compose_pyright_config(cwd, shared) == shared

    def test_returns_shared_when_no_venvpath_no_exclude(self, tmp_path: Path) -> None:
        """Config carrying neither ``venvPath`` nor ``exclude`` ⇒ nothing to rewrite."""
        shared = tmp_path / "shared_pyrightconfig.json"
        shared.write_text(json.dumps({"venv": ".venv"}))
        assert _compose_pyright_config(tmp_path, shared) == shared

    def test_returns_shared_unreadable_file_does_not_raise(
        self, tmp_path: Path
    ) -> None:
        """Missing or unreadable shipped config ⇒ shared returned unchanged."""
        shared = tmp_path / "does_not_exist.json"
        # The helper must not crash the runner; pyright surfaces the missing
        # config downstream, preserving the prior tool-dispatch behaviour.
        assert _compose_pyright_config(tmp_path, shared) == shared

    def test_returns_shared_when_not_a_json_mapping(self, tmp_path: Path) -> None:
        """A pyright ``--project`` pointed at a non-JSON config (e.g. a
        ``pyproject.toml`` override target) is passed through verbatim."""
        shared = tmp_path / "pyproject.toml"
        shared.write_text("[project]\nname = 'x'\n")
        assert _compose_pyright_config(tmp_path, shared) == shared
        shared_json_array = tmp_path / "array.json"
        shared_json_array.write_text("[]")
        assert _compose_pyright_config(tmp_path, shared_json_array) == shared_json_array

    def test_no_temp_file_written_on_fast_path(self, tmp_path: Path) -> None:
        shared = tmp_path / "shared_pyrightconfig.json"
        shared.write_text("{}")
        _compose_pyright_config(tmp_path, shared)
        out_dir = _temp_root() / f"python_setup_lint_pyright_{tmp_path.name}"
        assert not out_dir.exists()


def _temp_root() -> Path:
    import tempfile

    return Path(tempfile.gettempdir())


class TestComposePyrightConfigRewrites:
    """Relative ``venvPath``/``exclude`` get rewritten to absolute ``cwd`` paths."""

    def test_rewrites_venvpath_to_absolute_cwd(self, tmp_path: Path) -> None:
        shared = _write_shipped_config(tmp_path / "shared", body=_SHIPPED_BODY)
        cwd = tmp_path / "project"
        cwd.mkdir()
        composed = _compose_pyright_config(cwd, shared)
        assert composed != shared
        assert composed.is_file()
        text = composed.read_text()
        # venvPath rewritten to the absolute resolved cwd.
        assert f'"venvPath": "{cwd.resolve()}"' in text
        # Other settings preserved verbatim.
        assert '"venv": ".venv"' in text
        assert '"reportAttributeAccessIssue": "none"' in text

    def test_rewrites_each_relative_exclude_to_absolute_cwd(
        self, tmp_path: Path
    ) -> None:
        """Every relative ``exclude`` entry becomes an absolute ``cwd`` prefix.

        Includes plain paths (``.venv``, ``build/``, ``tests/data/``) AND
        glob-bearing entries (``**/__pycache__``, ``**/.*``).  The trailing slash
        on ``build/`` is normalised by :class:`pathlib.Path` (it loses its
        separator) — that's an accepted simplification; pyright matches the
        absolute path either way.
        """
        shared = _write_shipped_config(tmp_path / "shared", body=_SHIPPED_BODY)
        cwd = tmp_path / "project"
        cwd.mkdir()
        composed = _compose_pyright_config(cwd, shared)
        data = json.loads(composed.read_text())
        abs_cwd = cwd.resolve()
        expected = [
            f"{abs_cwd}/.venv",
            f"{abs_cwd}/**/__pycache__",
            f"{abs_cwd}/**/node_modules",
            f"{abs_cwd}/**/.*",
            f"{abs_cwd}/build",
            f"{abs_cwd}/tests/data",
        ]
        assert data["exclude"] == expected

    def test_leaves_absolute_exclude_entries_verbatim(self, tmp_path: Path) -> None:
        """An already-absolute exclude stays untouched (still rewritten if its
        relative sibling triggers any rewrite).  No double-join happens."""
        shared = tmp_path / "shared_pyrightconfig.json"
        abs_other = "/other/path/.venv"
        shared.write_text(
            json.dumps({"venvPath": ".", "exclude": [abs_other, ".venv"]})
        )
        cwd = tmp_path / "project"
        cwd.mkdir()
        composed = _compose_pyright_config(cwd, shared)
        data = json.loads(composed.read_text())
        # `.` ⇒ absolute cwd (rewrite triggered ⇒ temp written); abs_other
        # stays verbatim (no double-join).
        assert abs_other in data["exclude"]
        assert f"{cwd.resolve()}/.venv" in data["exclude"]
        assert composed != shared

    def test_skips_non_string_exclude_entries(self, tmp_path: Path) -> None:
        """Non-string exclude entries (e.g. numeric ``42``, ``null``) pass through."""
        shared = tmp_path / "shared_pyrightconfig.json"
        shared.write_text(json.dumps({"venvPath": ".", "exclude": [42, None, ".venv"]}))
        cwd = tmp_path / "project"
        cwd.mkdir()
        composed = _compose_pyright_config(cwd, shared)
        data = json.loads(composed.read_text())
        assert 42 in data["exclude"]
        assert None in data["exclude"]
        assert f"{cwd.resolve()}/.venv" in data["exclude"]
        assert composed != shared

    def test_rewrites_only_when_a_relative_entry_present(self, tmp_path: Path) -> None:
        """``venvPath`` already absolute + relative exclude ⇒ still rewrites excludes."""
        shared = tmp_path / "shared_pyrightconfig.json"
        shared.write_text(json.dumps({"venvPath": str(tmp_path), "exclude": [".venv"]}))
        cwd = tmp_path / "project"
        cwd.mkdir()
        composed = _compose_pyright_config(cwd, shared)
        assert composed != shared
        data = json.loads(composed.read_text())
        # venvPath stays absolute (already), exclude rewritten.
        assert data["venvPath"] == str(tmp_path)
        assert data["exclude"] == [f"{cwd.resolve()}/.venv"]

    def test_temp_file_in_dedicated_dir(self, tmp_path: Path) -> None:
        """Composed file lands under
        ``python_setup_lint_pyright_<cwd_name>/pyrightconfig.json``.
        ``tmp_path.name`` is unique per pytest session so the temp dir is
        fresh per test — and the dir-name embeds the cwd's basename."""
        cwd = _temp_root() / "t97_unique_cwd_xyz"
        cwd.mkdir(parents=True, exist_ok=True)
        try:
            shared = cwd / "shared_pyrightconfig.json"
            shared.write_text(json.dumps({"venvPath": ".", "exclude": [".venv"]}))
            composed = _compose_pyright_config(cwd, shared)
            assert composed.name == "pyrightconfig.json"
            assert composed.parent.name.startswith(f"python_setup_lint_pyright_{cwd.name}")
        finally:
            import shutil as _shutil

            _shutil.rmtree(cwd, ignore_errors=True)
            for d in _temp_root().iterdir():
                if d.name.startswith(f"python_setup_lint_pyright_{cwd.name}"):
                    _shutil.rmtree(d, ignore_errors=True)

    def test_idempotent_overwrite(self, tmp_path: Path) -> None:
        """Each invocation creates a fresh temp dir (mkdtemp guarantees uniqueness).
        The content is identical even though the path differs."""
        shared = _write_shipped_config(tmp_path / "shared", body=_SHIPPED_BODY)
        cwd = tmp_path / "project"
        cwd.mkdir()
        first = _compose_pyright_config(cwd, shared)
        second = _compose_pyright_config(cwd, shared)
        assert first != second  # mkdtemp creates unique dirs
        assert first.read_text() == second.read_text()

    def test_output_is_valid_json(self, tmp_path: Path) -> None:
        """The composed tmp file is JSON-parseable (pyright requires JSON)."""
        shared = _write_shipped_config(tmp_path / "shared", body=_SHIPPED_BODY)
        cwd = tmp_path / "project"
        cwd.mkdir()
        composed = _compose_pyright_config(cwd, shared)
        # Must parse without error.
        json.loads(composed.read_text())


# ── run_lint consumers the new default compose path ─────────────


class TestRunLintConsumesPyrightDefaultCompose:
    """``run_lint`` with ``pyright_project_override is None`` composes a cwd-rooted tmp config.

    Symmetric with the existing ruff compose block; replaces
    ``config.config_paths["pyright check"]`` with the composed path before
    the tool dispatch loop constructs the pyright command.
    """

    def _config_with_shipped(self, tmp_path: Path) -> RunnerConfig:
        shipped = _write_shipped_config(
            tmp_path / "shared" / "pyrightconfig.json", body=_SHIPPED_BODY
        )
        return RunnerConfig(
            cwd=tmp_path,
            tools_override=["pyright check"],
            config_paths={"pyright check": shipped},
        )

    def test_pyright_config_replaced_with_composed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """After ``run_lint``, ``config.config_paths["pyright check"]`` ≠ shipped."""
        config = self._config_with_shipped(tmp_path)
        shipped_before = config.config_paths["pyright check"]  # type: ignore[index]
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_output_module, "_run_cmd", fake)
        run_lint(config=config)
        assert config.config_paths["pyright check"] != shipped_before  # type: ignore[index]
        assert "python_setup_lint_pyright_" in str(config.config_paths["pyright check"])  # type: ignore[index]

    def test_pyright_command_uses_composed_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The pyright ``--project`` flag points at the composed tmp path."""
        config = self._config_with_shipped(tmp_path)
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_output_module, "_run_cmd", fake)
        run_lint(config=config)
        pyright_rec = next((r for r in fake.calls if r.cmd[:1] == ["pyright"]), None)
        assert pyright_rec is not None, (
            f"pyright not dispatched; calls={[r.cmd[:2] for r in fake.calls[:3]]}"
        )
        proj_idx = pyright_rec.cmd.index("--project")
        composed_path = pyright_rec.cmd[proj_idx + 1]
        assert "python_setup_lint_pyright_" in composed_path
        assert Path(composed_path).is_file()

    def test_no_compose_when_pyright_project_override_set(
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
        assert config.config_paths["pyright check"] == override  # type: ignore[index]
        # And the dispatched cmd uses the override, not a tmp path.
        pyright_rec = next((r for r in fake.calls if r.cmd[:1] == ["pyright"]), None)
        assert pyright_rec is not None
        proj_idx = pyright_rec.cmd.index("--project")
        assert pyright_rec.cmd[proj_idx + 1] == str(override)

    def test_no_compose_when_no_pyright_config_entry(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No ``pyright check`` entry in ``config_paths`` ⇒ no compose, no KeyError."""
        config = RunnerConfig(
            cwd=tmp_path,
            tools_override=["pyright check"],
            config_paths={"ruff check": tmp_path / "ruff.toml"},
        )
        fake = fake_run_cmd_factory({})
        monkeypatch.setattr(_output_module, "_run_cmd", fake)
        run_lint(config=config)
        # No tmp pyright config written.
        assert "pyright check" not in config.config_paths  # type: ignore[operator]
        out_dir = _temp_root() / f"python_setup_lint_pyright_{tmp_path.name}"
        assert not out_dir.exists()

    def test_preserves_ruff_compose_wire(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """T5 ruff-overrides wire + the new pyright wire can both fire in a single run."""
        shared_ruff = tmp_path / "shared_ruff.toml"
        shared_ruff.write_text("line-length = 130\n")
        pp = tmp_path / "pyproject.toml"
        pp.write_text(
            '[project]\nname = "x"\n[tool.ruff.lint.flake8-tidy-imports]\n'
            'banned-api."foo.bar" = { msg = "no" }\n'
        )
        pyright_shipped = _write_shipped_config(
            tmp_path / "shared" / "pyrightconfig.json", body=_SHIPPED_BODY
        )
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
        assert "python_setup_lint_ruff_" in str(config.config_paths["ruff check"])  # type: ignore[index]
        assert "python_setup_lint_pyright_" in str(config.config_paths["pyright check"])  # type: ignore[index]


