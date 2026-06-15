"""Unit tests for ``python_setup_lint.setup``.

Covers install idempotency, update drift detection, CLI entry points,
and helper functions.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

import pytest

from python_setup_lint.setup import (
    _AGENTS_SENTINEL,
    _AGENTS_SENTINEL_END,
    _AGENTS_SNIPPET,
    _PRECOMMIT_TEMPLATE,
    _STATE_FILE,
    SetupState,
    _atomic_write,
    _compute_checksums,
    _discover_checkers,
    _get_dev_deps,
    _get_package_dir,
    _get_pylint_load_plugins,
    _has_python_setup_dep,
    _read_pyproject_toml,
    _run_uv,
    _set_pylint_load_plugins,
    _step_add_dep,
    _step_agents_snippet,
    _step_coding_rules,
    _step_precommit,
    _step_pylint_plugins,
    _write_pyproject_toml,
    install,
    main,
    update,
)


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def empty_project() -> Path:
    """Create a temp dir with a minimal pyproject.toml and AGENTS.md."""
    d = Path(tempfile.mkdtemp(prefix="t15-test-"))
    pyproject = d / "pyproject.toml"
    pyproject.write_text(
        textwrap.dedent("""\
        [project]
        name = "test-project"
        version = "0.1.0"
        requires-python = ">=3.14"

        [dependency-groups]
        dev = ["ruff>=0.5"]
        """)
    )
    agents = d / "AGENTS.md"
    agents.write_text("# Test Project\n\nSome content.\n")
    return d


@pytest.fixture
def configured_project(empty_project: Path) -> Path:
    """Run install once on empty_project, return the configured dir."""
    # Use dev_path to avoid network calls
    rc = install(empty_project, dev_path="/home/slava/aiexp/python-setup")
    assert rc == 0
    return empty_project


# ── Helper unit tests ───────────────────────────────────────────────


class TestAtomicWrite:
    def test_writes_content(self) -> None:
        d = Path(tempfile.mkdtemp(prefix="t15-aw-"))
        p = d / "test.txt"
        _atomic_write(p, "hello")
        assert p.read_text() == "hello"
        # No tmp file left behind
        assert not list(d.glob("*.tmp"))

    def test_overwrites_existing(self) -> None:
        d = Path(tempfile.mkdtemp(prefix="t15-aw-"))
        p = d / "test.txt"
        p.write_text("old")
        _atomic_write(p, "new")
        assert p.read_text() == "new"

    def test_tmp_cleaned_on_error(self) -> None:
        d = Path(tempfile.mkdtemp(prefix="t15-aw-"))
        p = d / "readonly" / "test.txt"
        # Parent doesn't exist — write will fail
        with pytest.raises(FileNotFoundError):
            _atomic_write(p, "content")
        # No tmp file left
        assert not list(d.glob("*.tmp"))


class TestComputeChecksums:
    def test_returns_checksums_for_existing_files(self) -> None:
        d = Path(tempfile.mkdtemp(prefix="t15-cs-"))
        (d / "a.txt").write_text("hello")
        (d / "b.txt").write_text("world")
        result = _compute_checksums(d, ["a.txt", "b.txt"])
        assert len(result) == 2
        assert "a.txt" in result
        assert "b.txt" in result
        assert result["a.txt"] != result["b.txt"]

    def test_skips_missing_files(self) -> None:
        d = Path(tempfile.mkdtemp(prefix="t15-cs-"))
        (d / "a.txt").write_text("hello")
        result = _compute_checksums(d, ["a.txt", "missing.txt"])
        assert len(result) == 1
        assert "a.txt" in result

    def test_different_content_different_hash(self) -> None:
        d = Path(tempfile.mkdtemp(prefix="t15-cs-"))
        p = d / "a.txt"
        p.write_text("v1")
        h1 = _compute_checksums(d, ["a.txt"])["a.txt"]
        p.write_text("v2")
        h2 = _compute_checksums(d, ["a.txt"])["a.txt"]
        assert h1 != h2


class TestDiscoverCheckers:
    def test_finds_register_modules(self) -> None:
        modules = _discover_checkers()
        # At least the 4 known checker modules with register()
        assert "python_setup_lint.checkers.beartype_checker" in modules
        assert "python_setup_lint.checkers.no_try_import_checker" in modules
        assert "python_setup_lint.checkers.stub_checker" in modules
        assert "python_setup_lint.checkers.stub_docstring_checker" in modules
        # Does NOT include modules without register (stub_coverage, stub_fidelity, etc.)
        assert "python_setup_lint.checkers.stub_coverage" not in modules
        assert "python_setup_lint.checkers.stub_fidelity" not in modules
        assert "python_setup_lint.checkers.stub_import_contract" not in modules
        assert "python_setup_lint.checkers.stub_normalizer" not in modules

    def test_returns_sorted(self) -> None:
        modules = _discover_checkers()
        assert modules == sorted(modules)


class TestPyprojectTomlHelpers:
    def test_read_missing(self) -> None:
        d = Path(tempfile.mkdtemp(prefix="t15-toml-"))
        assert _read_pyproject_toml(d) is None

    def test_read_existing(self, empty_project: Path) -> None:
        data = _read_pyproject_toml(empty_project)
        assert data is not None
        assert data["project"]["name"] == "test-project"

    def test_get_dev_deps(self, empty_project: Path) -> None:
        data = _read_pyproject_toml(empty_project)
        assert data is not None
        deps = _get_dev_deps(data)
        assert "ruff>=0.5" in deps

    def test_get_dev_deps_missing_section(self) -> None:
        data: dict[str, object] = {"project": {"name": "x"}}
        assert _get_dev_deps(data) == []

    def test_has_python_setup_dep_true(self) -> None:
        assert _has_python_setup_dep(["python-setup"])
        assert _has_python_setup_dep(["ruff", "python-setup>=0.1.0"])
        assert _has_python_setup_dep(["python-setup[extra]"])

    def test_has_python_setup_dep_false(self) -> None:
        assert not _has_python_setup_dep(["ruff", "mypy"])
        assert not _has_python_setup_dep([])

    def test_get_pylint_load_plugins_empty(self) -> None:
        data: dict[str, object] = {"project": {"name": "x"}}
        assert _get_pylint_load_plugins(data) == []

    def test_get_pylint_load_plugins_present(self) -> None:
        data: dict[str, object] = {
            "tool": {
                "pylint": {
                    "main": {
                        "load-plugins": ["a.b", "c.d"],
                    }
                }
            }
        }
        assert _get_pylint_load_plugins(data) == ["a.b", "c.d"]

    def test_set_pylint_load_plugins_creates_sections(self) -> None:
        data: dict[str, object] = {"project": {"name": "x"}}
        _set_pylint_load_plugins(data, ["p.q"])
        assert _get_pylint_load_plugins(data) == ["p.q"]

    def test_write_and_read_roundtrip(self, empty_project: Path) -> None:
        data = _read_pyproject_toml(empty_project)
        assert data is not None
        _set_pylint_load_plugins(data, ["a.b"])
        _write_pyproject_toml(empty_project, data)
        data2 = _read_pyproject_toml(empty_project)
        assert data2 is not None
        assert _get_pylint_load_plugins(data2) == ["a.b"]


# ── SetupState tests ────────────────────────────────────────────────


class TestSetupState:
    def test_all_ok_no_errors(self) -> None:
        s = SetupState()
        assert s.all_ok

    def test_all_ok_with_errors(self) -> None:
        s = SetupState(errors=["something failed"])
        assert not s.all_ok

    def test_defaults_all_false(self) -> None:
        s = SetupState()
        assert not s.dep_added
        assert not s.dep_skipped
        assert not s.pylint_plugins_added
        assert not s.pylint_plugins_skipped
        assert not s.precommit_written
        assert not s.precommit_skipped
        assert not s.coding_rules_copied
        assert not s.coding_rules_skipped
        assert not s.agents_appended
        assert not s.agents_skipped


# ── Install surface tests ───────────────────────────────────────────


class TestInstallFresh:
    """Install into an empty project — all steps should execute."""

    def test_install_adds_dep(self, empty_project: Path) -> None:
        rc = install(empty_project, dev_path="/home/slava/aiexp/python-setup")
        assert rc == 0
        data = _read_pyproject_toml(empty_project)
        assert data is not None
        deps = _get_dev_deps(data)
        assert _has_python_setup_dep(deps)

    def test_install_adds_pylint_plugins(self, empty_project: Path) -> None:
        rc = install(empty_project, dev_path="/home/slava/aiexp/python-setup")
        assert rc == 0
        data = _read_pyproject_toml(empty_project)
        assert data is not None
        plugins = _get_pylint_load_plugins(data)
        assert len(plugins) >= 4
        assert "python_setup_lint.checkers.beartype_checker" in plugins

    def test_install_writes_precommit(self, empty_project: Path) -> None:
        rc = install(empty_project, dev_path="/home/slava/aiexp/python-setup")
        assert rc == 0
        precommit = empty_project / ".pre-commit-config.yaml"
        assert precommit.exists()
        content = precommit.read_text()
        assert "ruff-pre-commit" in content
        assert "python-setup lint" in content

    def test_install_copies_coding_rules(self, empty_project: Path) -> None:
        rc = install(empty_project, dev_path="/home/slava/aiexp/python-setup")
        assert rc == 0
        cr = empty_project / "CodingRules.md"
        assert cr.exists()
        content = cr.read_text()
        assert "Python Coding Rules" in content

    def test_install_appends_agents_snippet(self, empty_project: Path) -> None:
        rc = install(empty_project, dev_path="/home/slava/aiexp/python-setup")
        assert rc == 0
        agents = empty_project / "AGENTS.md"
        content = agents.read_text()
        assert _AGENTS_SENTINEL in content
        assert _AGENTS_SENTINEL_END in content
        assert "pre-commit" in content

    def test_install_saves_state_file(self, empty_project: Path) -> None:
        rc = install(empty_project, dev_path="/home/slava/aiexp/python-setup")
        assert rc == 0
        state_path = empty_project / _STATE_FILE
        assert state_path.exists()
        state_data = json.loads(state_path.read_text())
        assert "config_checksums" in state_data
        assert len(state_data["config_checksums"]) > 0


class TestInstallIdempotent:
    """Second install on already-configured project — all steps skip."""

    def test_second_install_skips_dep(self, configured_project: Path) -> None:
        # Capture state before second install
        data_before = _read_pyproject_toml(configured_project)
        assert data_before is not None
        deps_before = _get_dev_deps(data_before)

        rc = install(configured_project, dev_path="/home/slava/aiexp/python-setup")
        assert rc == 0

        data_after = _read_pyproject_toml(configured_project)
        assert data_after is not None
        deps_after = _get_dev_deps(data_after)
        # No duplicate entries
        assert deps_after == deps_before

    def test_second_install_skips_precommit(self, configured_project: Path) -> None:
        precommit = configured_project / ".pre-commit-config.yaml"
        mtime_before = precommit.stat().st_mtime

        rc = install(configured_project, dev_path="/home/slava/aiexp/python-setup")
        assert rc == 0

        # File unchanged
        assert precommit.stat().st_mtime == mtime_before

    def test_second_install_skips_coding_rules(self, configured_project: Path) -> None:
        cr = configured_project / "CodingRules.md"
        mtime_before = cr.stat().st_mtime

        rc = install(configured_project, dev_path="/home/slava/aiexp/python-setup")
        assert rc == 0

        assert cr.stat().st_mtime == mtime_before

    def test_second_install_does_not_duplicate_agents_snippet(
        self, configured_project: Path
    ) -> None:
        agents = configured_project / "AGENTS.md"
        content_before = agents.read_text()
        sentinel_count_before = content_before.count(_AGENTS_SENTINEL)

        rc = install(configured_project, dev_path="/home/slava/aiexp/python-setup")
        assert rc == 0

        content_after = agents.read_text()
        sentinel_count_after = content_after.count(_AGENTS_SENTINEL)
        assert sentinel_count_after == sentinel_count_before
        assert sentinel_count_after == 1  # exactly one block

    def test_second_install_exits_zero(self, configured_project: Path) -> None:
        rc = install(configured_project, dev_path="/home/slava/aiexp/python-setup")
        assert rc == 0


class TestInstallWithExistingPrecommit:
    """Install into project that already has .pre-commit-config.yaml."""

    def test_skips_precommit_when_exists(self, empty_project: Path) -> None:
        precommit = empty_project / ".pre-commit-config.yaml"
        precommit.write_text("# existing config")
        mtime_before = precommit.stat().st_mtime

        rc = install(empty_project, dev_path="/home/slava/aiexp/python-setup")
        assert rc == 0
        assert precommit.stat().st_mtime == mtime_before
        assert precommit.read_text() == "# existing config"


class TestInstallMissingPyproject:
    """Install into a dir without pyproject.toml."""

    def test_returns_error(self) -> None:
        d = Path(tempfile.mkdtemp(prefix="t15-nopy-"))
        rc = install(d, dev_path="/home/slava/aiexp/python-setup")
        assert rc == 1


# ── Update tests ────────────────────────────────────────────────────


class TestUpdate:
    def test_update_runs_sync_and_refresh(self, configured_project: Path) -> None:
        """update should run uv sync + uv add --refresh-package without errors."""
        import python_setup_lint.setup as setup_mod
        original = setup_mod._run_uv
        calls: list[list[str]] = []

        def fake_run_uv(args: list[str], *, cwd: Path) -> tuple[int, str, str]:
            calls.append(args)
            return 0, "", ""

        setup_mod._run_uv = fake_run_uv
        try:
            rc = update(configured_project)
            assert rc == 0
            # Should have called uv sync and uv add --refresh-package
            sync_calls = [c for c in calls if c == ["sync"]]
            refresh_calls = [c for c in calls if c == ["add", "--refresh-package", "python-setup"]]
            assert len(sync_calls) >= 1, "Expected uv sync to be called"
            assert len(refresh_calls) >= 1, "Expected uv add --refresh-package to be called"
        finally:
            setup_mod._run_uv = original

    def test_update_reports_no_drift_when_fresh(self, configured_project: Path) -> None:
        """After fresh install, update should report no config drift."""
        import python_setup_lint.setup as setup_mod
        original = setup_mod._run_uv

        def fake_run_uv(args: list[str], *, cwd: Path) -> tuple[int, str, str]:
            return 0, "", ""

        setup_mod._run_uv = fake_run_uv
        try:
            rc = update(configured_project)
            assert rc == 0
        finally:
            setup_mod._run_uv = original

    def test_update_handles_missing_state_file(self, empty_project: Path) -> None:
        """update without prior install should skip drift check gracefully."""
        import python_setup_lint.setup as setup_mod
        original = setup_mod._run_uv

        def fake_run_uv(args: list[str], *, cwd: Path) -> tuple[int, str, str]:
            return 0, "", ""

        setup_mod._run_uv = fake_run_uv
        try:
            rc = update(empty_project)
            assert rc == 0
        finally:
            setup_mod._run_uv = original


# ── CLI entry point tests ───────────────────────────────────────────


class TestMainCLI:
    def test_main_install(self, empty_project: Path) -> None:
        rc = main(["install", "--path", str(empty_project),
                   "--dev-path", "/home/slava/aiexp/python-setup"])
        assert rc == 0
        assert (empty_project / ".pre-commit-config.yaml").exists()

    def test_main_install_default_cwd(self) -> None:
        """install without --path uses cwd."""
        # Just verify it parses without error — actual install would
        # modify cwd which we don't want in tests
        d = Path(tempfile.mkdtemp(prefix="t15-cli-"))
        pyproject = d / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "test-project"
            version = "0.1.0"
            requires-python = ">=3.14"

            [dependency-groups]
            dev = ["ruff>=0.5"]
            """)
        )
        rc = main(["install", "--path", str(d),
                   "--dev-path", "/home/slava/aiexp/python-setup"])
        assert rc == 0

    def test_main_update(self, configured_project: Path) -> None:
        import python_setup_lint.setup as setup_mod
        original = setup_mod._run_uv

        def fake_run_uv(args: list[str], *, cwd: Path) -> tuple[int, str, str]:
            return 0, "", ""

        setup_mod._run_uv = fake_run_uv
        try:
            rc = main(["update", "--path", str(configured_project)])
            assert rc == 0
        finally:
            setup_mod._run_uv = original

    def test_main_no_subcommand(self) -> None:
        with pytest.raises(SystemExit):
            main([])

    def test_main_unknown_subcommand(self) -> None:
        with pytest.raises(SystemExit):
            main(["unknown"])


# ── Template content tests ──────────────────────────────────────────


class TestTemplates:
    def test_precommit_template_has_ruff_hooks(self) -> None:
        assert "ruff-format" in _PRECOMMIT_TEMPLATE
        assert "ruff-check" in _PRECOMMIT_TEMPLATE
        assert "python-setup lint" in _PRECOMMIT_TEMPLATE
        assert "pre-push" not in _PRECOMMIT_TEMPLATE  # G0: lint on pre-commit, not pre-push

    def test_agents_snippet_has_sentinels(self) -> None:
        formatted = _AGENTS_SNIPPET.format(
            open_sentinel=_AGENTS_SENTINEL,
            close_sentinel=_AGENTS_SENTINEL_END,
        )
        assert _AGENTS_SENTINEL in formatted
        assert _AGENTS_SENTINEL_END in formatted
        assert "pre-commit" in formatted


# ── RunUv tests ─────────────────────────────────────────────────────


class TestRunUv:
    def test_uv_not_found_returns_error(self) -> None:
        """When uv is not on PATH, _run_uv returns exit code 1."""
        d = Path(tempfile.mkdtemp(prefix="t15-uv-"))
        # Use a temp dir with no uv binary
        import python_setup_lint.setup as setup_mod
        import subprocess as sp_subprocess

        original_run = setup_mod.subprocess.run
        def fake_run(*args, **kwargs):
            raise FileNotFoundError("uv not found")
        setup_mod.subprocess.run = fake_run
        try:
            rc, out, err = _run_uv(["sync"], cwd=d)
            assert rc == 1
            assert "uv not found" in err
        finally:
            setup_mod.subprocess.run = original_run


# ── GetPackageDir tests ──────────────────────────────────────────────


class TestGetPackageDir:
    def test_returns_project_root(self) -> None:
        """_get_package_dir returns the project root (two levels up from src/python_setup_lint)."""
        pkg_dir = _get_package_dir()
        assert (pkg_dir / "pyproject.toml").exists()
        assert (pkg_dir / "src" / "python_setup_lint").is_dir()


# ── Step-level error path tests ─────────────────────────────────────


class TestStepErrorPaths:
    def test_step_pylint_plugins_missing_pyproject(self) -> None:
        """_step_pylint_plugins appends error when pyproject.toml missing."""
        d = Path(tempfile.mkdtemp(prefix="t15-step-"))
        state = SetupState()
        _step_pylint_plugins(state, d)
        assert len(state.errors) > 0
        assert "pyproject.toml" in state.errors[0]

    def test_step_coding_rules_missing_source(self) -> None:
        """_step_coding_rules appends error when bundled CodingRules.md missing."""
        d = Path(tempfile.mkdtemp(prefix="t15-step-"))
        state = SetupState()
        # Temporarily patch _get_package_dir to return a dir without CodingRules.md
        import python_setup_lint.setup as setup_mod

        original = setup_mod._get_package_dir
        try:
            fake_dir = Path(tempfile.mkdtemp(prefix="t15-fake-"))
            setup_mod._get_package_dir = lambda: fake_dir
            _step_coding_rules(state, d)
            assert len(state.errors) > 0
            assert "CodingRules.md" in state.errors[0]
        finally:
            setup_mod._get_package_dir = original

    def test_step_agents_snippet_missing_agents(self) -> None:
        """_step_agents_snippet skips when AGENTS.md doesn't exist (no error)."""
        d = Path(tempfile.mkdtemp(prefix="t15-step-"))
        state = SetupState()
        _step_agents_snippet(state, d)
        assert state.agents_skipped
        assert len(state.errors) == 0

    def test_step_precommit_skips_when_exists(self) -> None:
        """_step_precommit skips when .pre-commit-config.yaml already exists."""
        d = Path(tempfile.mkdtemp(prefix="t15-step-"))
        (d / ".pre-commit-config.yaml").write_text("# existing")
        state = SetupState()
        _step_precommit(state, d)
        assert state.precommit_skipped
        assert not state.precommit_written

    def test_step_precommit_writes_when_missing(self) -> None:
        """_step_precommit writes template when .pre-commit-config.yaml missing."""
        d = Path(tempfile.mkdtemp(prefix="t15-step-"))
        state = SetupState()
        _step_precommit(state, d)
        assert state.precommit_written
        assert (d / ".pre-commit-config.yaml").exists()

    def test_step_pylint_plugins_merges_existing_and_discovered(self) -> None:
        """_step_pylint_plugins merges existing plugins with discovered ones."""
        d = Path(tempfile.mkdtemp(prefix="t15-step-"))
        pyproject = d / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "test"
            version = "0.1.0"
            requires-python = ">=3.14"
            [tool.pylint.main]
            load-plugins = ["existing.plugin"]
            """)
        )
        state = SetupState()
        _step_pylint_plugins(state, d)
        assert state.pylint_plugins_added
        data = _read_pyproject_toml(d)
        assert data is not None
        plugins = _get_pylint_load_plugins(data)
        assert "existing.plugin" in plugins
        assert "python_setup_lint.checkers.beartype_checker" in plugins

    def test_step_pylint_plugins_skips_when_all_present(self) -> None:
        """_step_pylint_plugins skips when all discovered plugins already registered."""
        d = Path(tempfile.mkdtemp(prefix="t15-step-"))
        discovered = _discover_checkers()
        plugins_list = ", ".join(f'"{p}"' for p in discovered)
        pyproject = d / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent(f"""\
            [project]
            name = "test"
            version = "0.1.0"
            requires-python = ">=3.14"
            [tool.pylint.main]
            load-plugins = [{plugins_list}]
            """)
        )
        state = SetupState()
        _step_pylint_plugins(state, d)
        assert state.pylint_plugins_skipped
        assert not state.pylint_plugins_added


# ── Downstream integration test ────────────────────────────────────


class TestDownstreamIntegration:
    """End-to-end: create consumer project, install, run lint."""

    def test_install_then_lint_works(self) -> None:
        """After install, ``uv run lint --no-fail-fast`` works in consumer project."""
        import subprocess
        import shutil as _shutil

        consumer = Path.home() / ".tmp" / "t15-downstream"
        if consumer.exists():
            _shutil.rmtree(consumer)
        consumer.mkdir(parents=True)

        # Create a proper consumer project structure
        (consumer / "src" / "consumer").mkdir(parents=True)
        (consumer / "src" / "consumer" / "__init__.py").write_text("# consumer\n")
        (consumer / "tests").mkdir()
        (consumer / "tests" / "__init__.py").write_text("# tests\n")

        # Pre-populate pyproject with python-setup dep so install skips uv add
        pyproject = consumer / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
            [project]
            name = "consumer"
            version = "0.1.0"
            requires-python = ">=3.14"
            [dependency-groups]
            dev = ["ruff>=0.5", "python-setup"]
            """)
        )
        agents = consumer / "AGENTS.md"
        agents.write_text("# Consumer\n")

        # Init git so detect-secrets-hook works
        subprocess.run(["git", "init"], cwd=consumer, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=consumer, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=consumer, capture_output=True, check=True)
        subprocess.run(["git", "add", "."], cwd=consumer, capture_output=True, check=True)

        # Create minimal .secrets.baseline so detect-secrets passes
        secrets_baseline = consumer / ".secrets.baseline"
        secrets_baseline.write_text(
            '{"version": "1.0", "plugins_used": [], "filters_used": [], "results": {}, "generated_at": "2025-01-01T00:00:00Z"}\n'
        )

        # Create tach.toml so tach check passes
        tach_toml = consumer / "tach.toml"
        tach_toml.write_text(
            '[[modules]]\npath = "src/consumer"\ndepends_on = []\n'
        )

        # Install — dep step will skip since python-setup already in dev deps
        rc = install(consumer, dev_path="/home/slava/aiexp/python-setup")
        assert rc == 0, f"install failed with rc={rc}"

        # Verify files created
        assert (consumer / ".pre-commit-config.yaml").exists()
        assert (consumer / "CodingRules.md").exists()
        agents_content = agents.read_text()
        assert "<!-- python-setup:pre-commit -->" in agents_content

        # Run lint directly via run_lint (avoids uv run which needs venv creation)
        from python_setup_lint.runner import run_lint, RunnerConfig
        rc = run_lint(
            config=RunnerConfig(
                cwd=consumer,
                tools_override=["tach check", "ruff check",
                                "mypy", "ty check", "pyright check", "pylint"],
            ),
            no_fail_fast=True,
        )
        assert rc == 0, f"run_lint failed with rc={rc}"


# ── HasPythonSetupDep edge cases ────────────────────────────────────


class TestHasPythonSetupDepEdgeCases:
    def test_handles_git_url(self) -> None:
        assert _has_python_setup_dep(["python-setup@git+https://..."])
        assert _has_python_setup_dep(["ruff", "python-setup @ git+https://..."])

    def test_handles_path_dep(self) -> None:
        assert _has_python_setup_dep(["python-setup @ file:///path"])
        assert _has_python_setup_dep(["python-setup~=0.1"])

    def test_does_not_match_similar_names(self) -> None:
        assert not _has_python_setup_dep(["python-setup-tools"])
        assert not _has_python_setup_dep(["my-python-setup"])
        assert not _has_python_setup_dep(["python-setup-extra"])


# ── SetPylintLoadPlugins merge behavior ─────────────────────────────



# ── SetPylintLoadPlugins merge behavior ─────────────────────────────


class TestSetPylintLoadPluginsMerge:
    def test_does_not_duplicate_existing(self) -> None:
        data: dict[str, object] = {
            "tool": {
                "pylint": {
                    "main": {
                        "load-plugins": ["a.b", "c.d"],
                    }
                }
            }
        }
        _set_pylint_load_plugins(data, ["a.b", "c.d", "e.f"])
        plugins = _get_pylint_load_plugins(data)
        assert plugins == ["a.b", "c.d", "e.f"]
        assert plugins.count("a.b") == 1

    def test_handles_non_list_load_plugins(self) -> None:
        data: dict[str, object] = {
            "tool": {
                "pylint": {
                    "main": {
                        "load-plugins": "not_a_list",
                    }
                }
            }
        }
        _set_pylint_load_plugins(data, ["a.b"])
        plugins = _get_pylint_load_plugins(data)
        assert plugins == ["a.b"]


# ── Type safety for TOML helpers ────────────────────────────────────
class TestTomlHelperTypeSafety:
    def test_get_dev_deps_non_dict_dependency_groups(self) -> None:
        data: dict[str, object] = {"dependency-groups": "not_a_dict"}
        assert _get_dev_deps(data) == []

    def test_get_dev_deps_non_list_dev(self) -> None:
        data: dict[str, object] = {"dependency-groups": {"dev": "not_a_list"}}
        assert _get_dev_deps(data) == []

    def test_get_pylint_load_plugins_non_dict_tool(self) -> None:
        data: dict[str, object] = {"tool": "not_a_dict"}
        assert _get_pylint_load_plugins(data) == []

    def test_get_pylint_load_plugins_non_dict_pylint(self) -> None:
        data: dict[str, object] = {"tool": {"pylint": "not_a_dict"}}
        assert _get_pylint_load_plugins(data) == []

    def test_get_pylint_load_plugins_non_dict_main(self) -> None:
        data: dict[str, object] = {"tool": {"pylint": {"main": "not_a_dict"}}}
        assert _get_pylint_load_plugins(data) == []

    def test_set_pylint_load_plugins_non_dict_tool(self) -> None:
        data: dict[str, object] = {"tool": "not_a_dict"}
        # Should not raise
        _set_pylint_load_plugins(data, ["a.b"])
        assert _get_pylint_load_plugins(data) == []

    def test_set_pylint_load_plugins_non_dict_pylint(self) -> None:
        data: dict[str, object] = {"tool": {"pylint": "not_a_dict"}}
        _set_pylint_load_plugins(data, ["a.b"])
        assert _get_pylint_load_plugins(data) == []

    def test_set_pylint_load_plugins_non_dict_main(self) -> None:
        data: dict[str, object] = {"tool": {"pylint": {"main": "not_a_dict"}}}
        _set_pylint_load_plugins(data, ["a.b"])
        assert _get_pylint_load_plugins(data) == []
