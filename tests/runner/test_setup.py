"""Unit tests for ``python_setup_lint.setup``."""
from __future__ import annotations
import inspect
import json
import os
import re
import textwrap
from pathlib import Path
import pytest

from python_setup_lint._setup_precommit import (
    _AGENTS_SENTINEL, _AGENTS_SENTINEL_END, _AGENTS_SNIPPET, _PRECOMMIT_TEMPLATE,
    _atomic_write, _step_agents_snippet, _step_precommit,
)
from python_setup_lint.setup import (
    _STATE_FILE, SetupState, _compute_checksums, _discover_checkers, _get_dev_deps,
    _get_package_dir, _get_pylint_load_plugins, _has_python_setup_dep, _read_pyproject_toml,
    _run_uv, _save_state, _set_pylint_load_plugins, _step_add_dep, _step_coding_rules,
    _step_pylint_plugins, _write_pyproject_toml, install, main, update,
)

# ── Helper ──────────────────────────────────────────────────────────

class _UvCallRecorder:
    """Context manager replacing _run_uv with a recording fake."""
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self._orig = None
    def fake(self, args: list[str], *, cwd: Path) -> tuple[int, str, str]:
        self.calls.append(args)
        return 0, "", ""
    def __enter__(self) -> _UvCallRecorder:
        import python_setup_lint.setup as _m
        self._orig = _m._run_uv
        _m._run_uv = self.fake
        return self
    def __exit__(self, *a: object) -> None:
        import python_setup_lint.setup as _m
        _m._run_uv = self._orig


# ── Parametrize tables ──────────────────────────────────────────────

ATOMIC_WRITE_CASES = [
    pytest.param("hello", None, False, id="writes_content"),
    pytest.param("new", "old", False, id="overwrites_existing"),
    pytest.param("content", None, True, id="tmp_cleaned_on_error"),
]
CHECKSUM_CASES = [
    pytest.param(["a.txt", "b.txt"], 2, id="returns_checksums"),
    pytest.param(["a.txt", "missing.txt"], 1, id="skips_missing"),
]
HAS_DEP_CASES = [
    pytest.param(["python-setup"], True, id="exact"),
    pytest.param(["ruff", "python-setup>=0.1.0"], True, id="with_version"),
    pytest.param(["python-setup[extra]"], True, id="with_extra"),
    pytest.param(["python-setup@git+https://..."], True, id="git_url"),
    pytest.param(["ruff", "python-setup @ git+https://..."], True, id="git_url_with_sep"),
    pytest.param(["python-setup @ file:///path"], True, id="path_dep"),
    pytest.param(["python-setup~=0.1"], True, id="tilde_eq"),
    pytest.param(["ruff", "mypy"], False, id="not_present"),
    pytest.param([], False, id="empty"),
    pytest.param(["python-setup-tools"], False, id="similar_prefix"),
    pytest.param(["my-python-setup"], False, id="similar_suffix"),
    pytest.param(["python-setup-extra"], False, id="similar_suffix2"),
]
TEMPLATE_CASES = [
    pytest.param(_PRECOMMIT_TEMPLATE, ["ruff-format", "ruff-check", "python-setup lint"],
                 ["pre-push"], id="precommit"),
    pytest.param(_AGENTS_SNIPPET.format(open_sentinel=_AGENTS_SENTINEL,
                 close_sentinel=_AGENTS_SENTINEL_END),
                 [_AGENTS_SENTINEL, _AGENTS_SENTINEL_END, "pre-commit"], [], id="agents"),
]
TOML_TYPE_CASES = [
    pytest.param("_get_dev_deps", {"dependency-groups": "not_a_dict"}, [], id="gdeps_nd"),
    pytest.param("_get_dev_deps", {"dependency-groups": {"dev": "not_a_list"}}, [], id="gdeps_nl"),
    pytest.param("_get_pylint_load_plugins", {"tool": "not_a_dict"}, [], id="gpp_nd"),
    pytest.param("_get_pylint_load_plugins", {"tool": {"pylint": "not_a_dict"}}, [], id="gpp_nd2"),
    pytest.param("_get_pylint_load_plugins", {"tool": {"pylint": {"main": "not_a_dict"}}}, [], id="gpp_nd3"),
]
SET_PLUGINS_CASES = [
    pytest.param(["a.b", "c.d"], ["a.b", "c.d", "e.f"], ["a.b", "c.d", "e.f"], id="no_dup"),
    pytest.param("not_a_list", ["a.b"], ["a.b"], id="non_list"),
]

# Install artifact check functions
def _ck_dep(p: Path) -> None:
    d = _read_pyproject_toml(p)
    assert d and _has_python_setup_dep(_get_dev_deps(d))
def _ck_pylint(p: Path) -> None:
    d = _read_pyproject_toml(p)
    assert d
    plugs = _get_pylint_load_plugins(d)
    assert len(plugs) >= 4
    assert "python_setup_lint.checkers.beartype_checker" in plugs
def _ck_precommit(p: Path) -> None:
    c = (p / ".pre-commit-config.yaml").read_text()
    assert "ruff-pre-commit" in c and "python-setup lint" in c
def _ck_coding(p: Path) -> None:
    assert "Python Coding Rules" in (p / "CodingRules.md").read_text()
def _ck_agents(p: Path) -> None:
    c = (p / "AGENTS.md").read_text()
    assert _AGENTS_SENTINEL in c and _AGENTS_SENTINEL_END in c
def _ck_state(p: Path) -> None:
    sd = json.loads((p / _STATE_FILE).read_text())
    assert "config_checksums" in sd and len(sd["config_checksums"]) > 0
INSTALL_ARTIFACT_CASES = [
    pytest.param(_ck_dep, id="adds_dep"),
    pytest.param(_ck_pylint, id="adds_pylint_plugins"),
    pytest.param(_ck_precommit, id="writes_precommit"),
    pytest.param(_ck_coding, id="copies_coding_rules"),
    pytest.param(_ck_agents, id="appends_agents_snippet"),
    pytest.param(_ck_state, id="saves_state_file"),
]

# Step setup helpers
def _s_noop(d: Path, mp: pytest.MonkeyPatch) -> None: pass
def _s_pyproject(d: Path, mp: pytest.MonkeyPatch) -> None:
    (d / "pyproject.toml").write_text(textwrap.dedent("""\
        [project]
        name = "test"
        version = "0.1.0"
        requires-python = ">=3.14"
        [dependency-groups]
        dev = ["ruff>=0.5"]
    """))
def _s_precommit(d: Path, mp: pytest.MonkeyPatch) -> None:
    (d / ".pre-commit-config.yaml").write_text("# existing")
def _s_agents_sentinel(d: Path, mp: pytest.MonkeyPatch) -> None:
    (d / "AGENTS.md").write_text(f"# P\n\n{_AGENTS_SENTINEL}\nx\n{_AGENTS_SENTINEL_END}\n")
def _s_pyproject_plugins(d: Path, mp: pytest.MonkeyPatch) -> None:
    _s_pyproject(d, mp)
    (d / "pyproject.toml").write_text(textwrap.dedent("""\
        [project]
        name = "test"
        version = "0.1.0"
        requires-python = ">=3.14"
        [tool.pylint.main]
        load-plugins = ["existing.plugin"]
    """))
def _s_all_plugins(d: Path, mp: pytest.MonkeyPatch) -> None:
    plist = ", ".join(f'"{p}"' for p in _discover_checkers())
    (d / "pyproject.toml").write_text(textwrap.dedent(f"""\
        [project]
        name = "test"
        version = "0.1.0"
        requires-python = ">=3.14"
        [tool.pylint.main]
        load-plugins = [{plist}]
    """))
def _s_fake_pkg(d: Path, mp: pytest.MonkeyPatch) -> None:
    import python_setup_lint.setup as _m
    fake = d / "fake-pkg"
    fake.mkdir()
    mp.setattr(_m, "_get_package_dir", lambda: fake)
def _s_failing_uv(d: Path, mp: pytest.MonkeyPatch) -> None:
    import python_setup_lint.setup as _m
    _s_pyproject(d, mp)
    mp.setattr(_m, "_run_uv", lambda args, *, cwd: (1, "", "uv add failed: network error"))
def _s_empty_bundled(d: Path, mp: pytest.MonkeyPatch) -> None:
    import python_setup_lint.setup as _m
    mp.setattr(_m, "_BUNDLED_CONFIGS", ())

STEP_CASES = [
    pytest.param(_step_pylint_plugins, _s_noop,
                 lambda s, _: len(s.errors) > 0 and "pyproject.toml" in s.errors[0], id="pp_mp"),
    pytest.param(_step_coding_rules, _s_fake_pkg,
                 lambda s, _: len(s.errors) > 0 and "CodingRules.md" in s.errors[0], id="cr_ms"),
    pytest.param(_step_agents_snippet, _s_noop,
                 lambda s, _: s.agents_skipped and len(s.errors) == 0, id="as_ma"),
    pytest.param(_step_add_dep, _s_noop,
                 lambda s, _: len(s.errors) > 0 and "pyproject.toml" in s.errors[0], id="ad_mp"),
    pytest.param(_step_agents_snippet, _s_agents_sentinel,
                 lambda s, _: s.agents_skipped and not s.agents_appended and len(s.errors) == 0, id="as_ahs"),
    pytest.param(_step_precommit, _s_precommit,
                 lambda s, _: s.precommit_skipped and not s.precommit_written, id="pc_sk"),
    pytest.param(_step_precommit, _s_noop,
                 lambda s, d: s.precommit_written and (d / ".pre-commit-config.yaml").exists(), id="pc_wr"),
    pytest.param(_step_pylint_plugins, _s_pyproject_plugins,
                 lambda s, d: (
                     s.pylint_plugins_added
                     and "existing.plugin" in _get_pylint_load_plugins(_read_pyproject_toml(d))
                     and "python_setup_lint.checkers.beartype_checker" in _get_pylint_load_plugins(_read_pyproject_toml(d))
                 ), id="pp_mg"),
    pytest.param(_step_pylint_plugins, _s_all_plugins,
                 lambda s, _: s.pylint_plugins_skipped and not s.pylint_plugins_added, id="pp_sk"),
    pytest.param(_step_add_dep, _s_failing_uv,
                 lambda s, _: len(s.errors) > 0 and "uv add" in s.errors[0] and "network error" in s.errors[0], id="ad_uvf"),
    pytest.param(lambda s, d: _save_state(d, s), _s_empty_bundled,
                 lambda s, d: len(json.loads((d / _STATE_FILE).read_text())["config_checksums"]) == 0, id="ss_efl"),
]


# ── Tests ──────────────────────────────────────────────────────────

class TestAtomicWrite:
    @pytest.mark.parametrize("content,existing,should_raise", ATOMIC_WRITE_CASES)
    def test_cases(self, tmp_path: Path, content: str, existing: str | None, should_raise: bool) -> None:
        d, p = tmp_path, tmp_path / "test.txt"
        if existing is not None:
            p.write_text(existing)
        if should_raise:
            with pytest.raises(FileNotFoundError):
                _atomic_write(p / "nope", content)
        else:
            _atomic_write(p, content)
            assert p.read_text() == content
        assert not list(d.glob("*.tmp"))

    def test_mid_write_failure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def failing_replace(*a: object, **kw: object) -> None:
            raise OSError("replace failed")
        monkeypatch.setattr(os, "replace", failing_replace)
        with pytest.raises(OSError, match="replace failed"):
            _atomic_write(tmp_path / "test.txt", "x")
        assert not list(tmp_path.glob("*.tmp"))
        assert not (tmp_path / "test.txt").exists()

class TestComputeChecksums:
    @pytest.mark.parametrize("files,expected_count", CHECKSUM_CASES)
    def test_cases(self, tmp_path: Path, files: list[str], expected_count: int) -> None:
        d = tmp_path
        for f in ["a.txt", "b.txt"]:
            (d / f).write_text(f"c-{f}")
        assert len(_compute_checksums(d, files)) == expected_count

    def test_diff_hash(self, tmp_path: Path) -> None:
        p = tmp_path / "a.txt"
        p.write_text("v1")
        h1 = _compute_checksums(tmp_path, ["a.txt"])["a.txt"]
        p.write_text("v2")
        assert _compute_checksums(tmp_path, ["a.txt"])["a.txt"] != h1

class TestDiscoverCheckers:
    def test_finds_register_modules(self) -> None:
        m = _discover_checkers()
        for n in ("beartype_checker", "no_try_import_checker", "stub_checker",
                  "stub_docstring_checker", "tmp_path_checker"):
            assert f"python_setup_lint.checkers.{n}" in m
        for n in ("stub_coverage", "stub_fidelity", "stub_import_contract", "stub_normalizer"):
            assert f"python_setup_lint.checkers.{n}" not in m

    def test_sorted(self) -> None:
        assert _discover_checkers() == sorted(_discover_checkers())

class TestPyprojectTomlHelpers:
    def test_read_missing(self, tmp_path: Path) -> None:
        assert _read_pyproject_toml(tmp_path) is None

    def test_read_and_get(self, empty_project: Path) -> None:
        d = _read_pyproject_toml(empty_project)
        assert d and d["project"]["name"] == "test-project"
        assert "ruff>=0.5" in _get_dev_deps(d)

    def test_get_dev_deps_missing(self) -> None:
        assert _get_dev_deps({"project": {"name": "x"}}) == []

    def test_get_pylint_empty(self) -> None:
        assert _get_pylint_load_plugins({"project": {"name": "x"}}) == []

    def test_get_pylint_present(self) -> None:
        assert _get_pylint_load_plugins({"tool": {"pylint": {"main": {"load-plugins": ["a.b"]}}}}) == ["a.b"]

    def test_set_pylint_creates(self) -> None:
        d: dict = {"project": {"name": "x"}}
        _set_pylint_load_plugins(d, ["p.q"])
        assert _get_pylint_load_plugins(d) == ["p.q"]

    def test_write_read_roundtrip(self, empty_project: Path) -> None:
        d = _read_pyproject_toml(empty_project)
        _set_pylint_load_plugins(d, ["a.b"])
        _write_pyproject_toml(empty_project, d)
        assert _get_pylint_load_plugins(_read_pyproject_toml(empty_project)) == ["a.b"]

class TestHasPythonSetupDep:
    @pytest.mark.parametrize("deps,expected", HAS_DEP_CASES)
    def test_cases(self, deps: list[str], expected: bool) -> None:
        assert _has_python_setup_dep(deps) is expected

class TestSetupState:
    def test_all_ok(self) -> None:
        assert SetupState().all_ok
        assert not SetupState(errors=["x"]).all_ok

class TestInstallFresh:
    @pytest.mark.parametrize("check_fn", INSTALL_ARTIFACT_CASES)
    def test_artifacts(self, empty_project: Path, check_fn: object) -> None:
        assert install(empty_project, dev_path="/home/slava/aiexp/python-setup") == 0
        check_fn(empty_project)

class TestInstallIdempotent:
    def test_second_install_skips_dep(self, configured_project: Path) -> None:
        deps_before = _get_dev_deps(_read_pyproject_toml(configured_project))
        assert install(configured_project, dev_path="/home/slava/aiexp/python-setup") == 0
        assert _get_dev_deps(_read_pyproject_toml(configured_project)) == deps_before

    def test_second_install_agets_no_dup(self, configured_project: Path) -> None:
        assert (configured_project / "AGENTS.md").read_text().count(_AGENTS_SENTINEL) == 1

class TestInstallExistingPrecommit:
    def test_skips(self, empty_project: Path) -> None:
        p = empty_project / ".pre-commit-config.yaml"
        p.write_text("# e")
        m = p.stat().st_mtime
        assert install(empty_project, dev_path="/home/slava/aiexp/python-setup") == 0
        assert p.stat().st_mtime == m and p.read_text() == "# e"

class TestInstallMissingPyproject:
    def test_returns_error(self, tmp_path: Path) -> None:
        assert install(tmp_path, dev_path="/home/slava/aiexp/python-setup") == 1

class TestUpdate:
    def test_runs_sync_and_refresh(self, configured_project: Path) -> None:
        with _UvCallRecorder() as r:
            assert update(configured_project) == 0
        assert any(c == ["sync"] for c in r.calls)
        assert any(c == ["add", "--refresh-package", "python-setup"] for c in r.calls)

    def test_no_drift_and_missing_state(self, configured_project: Path, empty_project: Path) -> None:
        with _UvCallRecorder():
            assert update(configured_project) == 0
            assert update(empty_project) == 0

class TestMainCLI:
    def test_install(self, empty_project: Path) -> None:
        assert main(["install", "--path", str(empty_project), "--dev-path", "/home/slava/aiexp/python-setup"]) == 0
        assert (empty_project / ".pre-commit-config.yaml").exists()

    def test_install_default_cwd(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(textwrap.dedent("""\
            [project]
            name = "t"
            version = "0.1.0"
            requires-python = ">=3.14"
            [dependency-groups]
            dev = ["ruff>=0.5"]
        """))
        assert main(["install", "--path", str(tmp_path), "--dev-path", "/home/slava/aiexp/python-setup"]) == 0

    def test_update(self, configured_project: Path) -> None:
        with _UvCallRecorder():
            assert main(["update", "--path", str(configured_project)]) == 0
    @pytest.mark.parametrize("args", [[], ["unknown"]])
    def test_bad_subcommand(self, args: list[str]) -> None:
        with pytest.raises(SystemExit):
            main(args)

class TestTemplates:
    @pytest.mark.parametrize("content,present,absent", TEMPLATE_CASES)
    def test_content(self, content: str, present: list[str], absent: list[str]) -> None:
        for s in present:
            assert s in content
        for s in absent:
            assert s not in content

class TestRunUv:
    def test_uv_not_found(self, tmp_path: Path) -> None:
        import python_setup_lint.setup as _m
        orig = _m.subprocess.run
        def fake_run(*a: object, **kw: object) -> object:
            raise FileNotFoundError("uv not found")
        _m.subprocess.run = fake_run  # type: ignore[assignment]
        try:
            rc, _, err = _run_uv(["sync"], cwd=tmp_path)
            assert rc == 1 and "uv not found" in err
        finally:
            _m.subprocess.run = orig

class TestGetPackageDir:
    def test_returns_project_root(self) -> None:
        p = _get_package_dir()
        assert (p / "pyproject.toml").exists()
        assert (p / "src" / "python_setup_lint").is_dir()

class TestModuleSizeGates:
    def test_setup_py_loc(self) -> None:
        import python_setup_lint.setup as m
        assert len(inspect.getsource(m).splitlines()) <= 500

    def test_setup_precommit_loc(self) -> None:
        import python_setup_lint._setup_precommit as m
        assert len(inspect.getsource(m).splitlines()) <= 200

    def test_pyi_declares_all(self) -> None:
        import python_setup_lint.setup as m
        pyi = Path(m.__file__).with_suffix(".pyi").read_text()
        defs = len(re.findall(r'^def ', pyi, re.MULTILINE))
        consts = len(re.findall(r'^[A-Z_]+:', pyi, re.MULTILINE))
        assert defs + consts >= 19

class TestStepErrorPaths:
    @pytest.mark.parametrize("step_fn,setup_fn,assert_fn", STEP_CASES)
    def test_cases(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                   step_fn: object, setup_fn: object, assert_fn: object) -> None:
        d = tmp_path
        setup_fn(d, monkeypatch)
        state = SetupState()
        step_fn(state, d)
        assert assert_fn(state, d)

class TestTomlHelperTypeSafety:
    @pytest.mark.parametrize("fn_name,data,expected", TOML_TYPE_CASES)
    def test_gets(self, fn_name: str, data: dict, expected: object) -> None:
        fns = {"_get_dev_deps": _get_dev_deps, "_get_pylint_load_plugins": _get_pylint_load_plugins}
        assert fns[fn_name](data) == expected

    def test_set_non_dict(self) -> None:
        for d in ({"tool": "nd"}, {"tool": {"pylint": "nd"}}, {"tool": {"pylint": {"main": "nd"}}}):
            cp = dict(d)
            _set_pylint_load_plugins(cp, ["a.b"])
            assert _get_pylint_load_plugins(cp) == []

class TestSetPylintLoadPluginsMerge:
    @pytest.mark.parametrize("existing,new,expected", SET_PLUGINS_CASES)
    def test_cases(self, existing: object, new: list[str], expected: list[str]) -> None:
        d = {"tool": {"pylint": {"main": {"load-plugins": existing}}}}
        _set_pylint_load_plugins(d, new)
        assert _get_pylint_load_plugins(d) == expected

class TestDownstreamIntegration:
    @pytest.mark.slow
    def test_install_then_lint(self) -> None:
        import subprocess
        import shutil
        c = Path.home() / ".tmp" / "t15-downstream"
        if c.exists():
            shutil.rmtree(c)
        c.mkdir(parents=True)
        (c / "src/consumer").mkdir(parents=True)
        (c / "src/consumer/__init__.py").write_text("# c\n")
        (c / "tests").mkdir()
        (c / "tests/__init__.py").write_text("# t\n")
        (c / "pyproject.toml").write_text(textwrap.dedent("""\
            [project]
            name = "consumer"
            version = "0.1.0"
            requires-python = ">=3.14"
            [dependency-groups]
            dev = ["ruff>=0.5", "python-setup"]
        """))
        (c / "AGENTS.md").write_text("# C\n")
        subprocess.run(["git", "init"], cwd=c, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=c, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=c, capture_output=True, check=True)
        subprocess.run(["git", "add", "."], cwd=c, capture_output=True, check=True)
        (c / ".secrets.baseline").write_text(
            '{"version":"1.0","plugins_used":[],"filters_used":[],'
            '"results":{},"generated_at":"2025-01-01T00:00:00Z"}\n'
        )
        (c / "tach.toml").write_text('[[modules]]\npath = "src/consumer"\ndepends_on = []\n')
        assert install(c, dev_path="/home/slava/aiexp/python-setup") == 0
        assert (c / ".pre-commit-config.yaml").exists()
        assert (c / "CodingRules.md").exists()
        assert "<!-- python-setup:pre-commit -->" in (c / "AGENTS.md").read_text()
        from python_setup_lint.runner import run_lint, RunnerConfig
        assert run_lint(config=RunnerConfig(cwd=c, tools_override=["tach check", "ruff check", "mypy", "ty check", "pyright check", "pylint"]), no_fail_fast=True) == 0
