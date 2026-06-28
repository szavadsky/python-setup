"""Unit tests for ``python_setup_lint.setup``."""

from __future__ import annotations

import inspect
import re
import textwrap
from pathlib import Path
from typing import Any, Self

import pytest

from python_setup_lint._setup_precommit import (
    _AGENTS_SENTINEL,
    _AGENTS_SENTINEL_END,
    _AGENTS_SNIPPET,
    _PRECOMMIT_TEMPLATE,
    _atomic_write,
)
from python_setup_lint.setup import (
    SetupState,
    _compute_checksums,
    _discover_checkers,
    _get_dev_deps,
    _get_package_dir,
    _get_pylint_load_plugins,
    _has_python_setup_dep,
    _read_pyproject_toml,
    _run_uv,
    _set_pylint_load_plugins,
    _write_pyproject_toml,
    main,
    update,
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

    def __enter__(self) -> Self:
        import python_setup_lint.setup as _m

        self._orig = _m._run_uv  # type: ignore[assignment]  # dynamic import hides type; runtime reference for restoration
        _m._run_uv = self.fake
        return self

    def __exit__(self, *a: object) -> None:
        import python_setup_lint.setup as _m

        _m._run_uv = self._orig  # type: ignore[assignment]  # dynamic import hides type; runtime reference for restoration


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
    pytest.param(
        ["ruff", "python-setup @ git+https://..."], True, id="git_url_with_sep"
    ),
    pytest.param(["python-setup @ file:///path"], True, id="path_dep"),
    pytest.param(["python-setup~=0.1"], True, id="tilde_eq"),
    pytest.param(["ruff", "mypy"], False, id="not_present"),
    pytest.param([], False, id="empty"),
    pytest.param(["python-setup-tools"], False, id="similar_prefix"),
    pytest.param(["my-python-setup"], False, id="similar_suffix"),
    pytest.param(["python-setup-extra"], False, id="similar_suffix2"),
]
TEMPLATE_CASES = [
    pytest.param(
        _PRECOMMIT_TEMPLATE,
        ["ruff-format", "ruff-check", "python-setup lint"],
        ["pre-push"],
        id="precommit",
    ),
    pytest.param(
        _AGENTS_SNIPPET.format(
            open_sentinel=_AGENTS_SENTINEL, close_sentinel=_AGENTS_SENTINEL_END
        ),
        [_AGENTS_SENTINEL, _AGENTS_SENTINEL_END, "pre-commit"],
        [],
        id="agents",
    ),
]
TOML_TYPE_CASES = [
    pytest.param(
        "_get_dev_deps", {"dependency-groups": "not_a_dict"}, [], id="gdeps_nd"
    ),
    pytest.param(
        "_get_dev_deps", {"dependency-groups": {"dev": "not_a_list"}}, [], id="gdeps_nl"
    ),
    pytest.param("_get_pylint_load_plugins", {"tool": "not_a_dict"}, [], id="gpp_nd"),
    pytest.param(
        "_get_pylint_load_plugins", {"tool": {"pylint": "not_a_dict"}}, [], id="gpp_nd2"
    ),
    pytest.param(
        "_get_pylint_load_plugins",
        {"tool": {"pylint": {"main": "not_a_dict"}}},
        [],
        id="gpp_nd3",
    ),
]
SET_PLUGINS_CASES = [
    pytest.param(
        ["a.b", "c.d"], ["a.b", "c.d", "e.f"], ["a.b", "c.d", "e.f"], id="no_dup"
    ),
    pytest.param("not_a_list", ["a.b"], ["a.b"], id="non_list"),
]


# ── Tests ──────────────────────────────────────────────────────────


class TestAtomicWrite:
    @pytest.mark.parametrize(("content", "existing", "should_raise"), ATOMIC_WRITE_CASES)
    def test_cases(
        self, tmp_path: Path, content: str, existing: str | None, should_raise: bool
    ) -> None:
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

    def test_mid_write_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os

        def failing_replace(*a: object, **kw: object) -> None:
            raise OSError("replace failed")

        monkeypatch.setattr(os, "replace", failing_replace)
        with pytest.raises(OSError, match="replace failed"):
            _atomic_write(tmp_path / "test.txt", "x")
        assert not list(tmp_path.glob("*.tmp"))
        assert not (tmp_path / "test.txt").exists()


class TestComputeChecksums:
    @pytest.mark.parametrize(("files", "expected_count"), CHECKSUM_CASES)
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
        for n in (
            "conformance.beartype_checker",
            "conformance.no_try_import_checker",
            "stub.checker",
            "stub.docstring_checker",
            "conformance.tmp_path_checker",
        ):
            assert f"python_setup_lint.checkers.{n}" in m
        for n in (
            "stub.coverage",
            "stub.fidelity",
            "stub.import_contract",
            "stub.normalizer",
        ):
            assert f"python_setup_lint.checkers.{n}" not in m

    def test_sorted(self) -> None:
        assert _discover_checkers() == sorted(_discover_checkers())


class TestPyprojectTomlHelpers:
    def test_read_missing(self, tmp_path: Path) -> None:
        assert _read_pyproject_toml(tmp_path) is None

    def test_read_and_get(self, empty_project: Path) -> None:
        d = _read_pyproject_toml(empty_project)
        assert d and d["project"]["name"] == "test-project"  # type: ignore[index]  # _read_pyproject_toml returns dict[str, object] | None; dict key access on object is valid at runtime
        assert "ruff>=0.5" in _get_dev_deps(d)

    def test_get_dev_deps_missing(self) -> None:
        assert _get_dev_deps({"project": {"name": "x"}}) == []

    def test_get_pylint_empty(self) -> None:
        assert _get_pylint_load_plugins({"project": {"name": "x"}}) == []

    def test_get_pylint_present(self) -> None:
        assert _get_pylint_load_plugins(
            {"tool": {"pylint": {"main": {"load-plugins": ["a.b"]}}}}
        ) == ["a.b"]

    def test_set_pylint_creates(self) -> None:
        d: dict[str, Any] = {"project": {"name": "x"}}  # Any needed for nested mutation; _set_pylint_load_plugins expects dict[str, object]
        _set_pylint_load_plugins(d, ["p.q"])
        assert _get_pylint_load_plugins(d) == ["p.q"]

    def test_write_read_roundtrip(self, empty_project: Path) -> None:
        d = _read_pyproject_toml(empty_project)
        _set_pylint_load_plugins(d, ["a.b"])  # type: ignore[arg-type]  # d is dict[str, object] | None at runtime; _set_pylint_load_plugins expects dict[str, object]
        _write_pyproject_toml(empty_project, d)  # type: ignore[arg-type]  # d is dict[str, object] | None at runtime; _write_pyproject_toml expects dict[str, object]
        assert _get_pylint_load_plugins(_read_pyproject_toml(empty_project)) == ["a.b"]  # type: ignore[arg-type]  # _read_pyproject_toml returns dict[str, object] | None; _get_pylint_load_plugins expects dict[str, object]


class TestHasPythonSetupDep:
    @pytest.mark.parametrize(("deps", "expected"), HAS_DEP_CASES)
    def test_cases(self, deps: list[str], expected: bool) -> None:
        assert _has_python_setup_dep(deps) is expected


class TestSetupState:
    def test_all_ok(self) -> None:
        assert SetupState().all_ok
        assert not SetupState(errors=["x"]).all_ok


class TestUpdate:
    def test_runs_sync_and_refresh(self, configured_project: Path) -> None:
        with _UvCallRecorder() as r:
            assert update(configured_project) == 0
        assert any(c == ["sync"] for c in r.calls)
        assert any(c == ["add", "python-setup", "--refresh-package", "python-setup"] for c in r.calls)

    def test_no_drift_and_missing_state(
        self, configured_project: Path, empty_project: Path
    ) -> None:
        with _UvCallRecorder():
            assert update(configured_project) == 0
            assert update(empty_project) == 0


class TestMainCLI:
    def test_install(self, empty_project: Path) -> None:
        assert (
            main(
                [
                    "install",
                    "--path",
                    str(empty_project),
                    "--dev-path",
                    "/home/slava/aiexp/python-setup",
                ]
            )
            == 0
        )
        assert (empty_project / ".pre-commit-config.yaml").exists()

    def test_install_default_cwd(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            textwrap.dedent("""\
            [project]
            name = "t"
            version = "0.1.0"
            requires-python = ">=3.14"
            [dependency-groups]
            dev = ["ruff>=0.5"]
        """)
        )
        assert (
            main(
                [
                    "install",
                    "--path",
                    str(tmp_path),
                    "--dev-path",
                    "/home/slava/aiexp/python-setup",
                ]
            )
            == 0
        )

    def test_update(self, configured_project: Path) -> None:
        with _UvCallRecorder():
            assert main(["update", "--path", str(configured_project)]) == 0

    @pytest.mark.parametrize("args", [[], ["unknown"]])
    def test_bad_subcommand(self, args: list[str]) -> None:
        with pytest.raises(SystemExit):
            main(args)


class TestTemplates:
    @pytest.mark.parametrize(("content", "present", "absent"), TEMPLATE_CASES)
    def test_content(self, content: str, present: list[str], absent: list[str]) -> None:
        for s in present:
            assert s in content
        for s in absent:
            assert s not in content


class TestRunUv:
    def test_uv_not_found(self, tmp_path: Path) -> None:
        import python_setup_lint.setup as _m

        orig = _m.subprocess.run  # type: ignore[attr-defined]  # dynamic import hides type; subprocess.run accessed via module reference

        def fake_run(*a: object, **kw: object) -> object:
            raise FileNotFoundError("uv not found")

        _m.subprocess.run = fake_run  # type: ignore[attr-defined]  # dynamic import hides type; assigning callable to subprocess.run
        try:
            rc, _, err = _run_uv(["sync"], cwd=tmp_path)
            assert rc == 1 and "uv not found" in err
        finally:
            _m.subprocess.run = orig  # type: ignore[attr-defined]  # dynamic import hides type; restoring original reference


class TestGetPackageDir:
    def test_returns_project_root(self) -> None:
        p = _get_package_dir()
        assert (p / "pyproject.toml").exists()
        assert (p / "src" / "python_setup_lint").is_dir()


class TestModuleSizeGates:
    def test_setup_py_loc(self) -> None:
        import python_setup_lint.setup as m

        assert len(inspect.getsource(m).splitlines()) <= 530

    def test_setup_precommit_loc(self) -> None:
        import python_setup_lint._setup_precommit as m

        assert len(inspect.getsource(m).splitlines()) <= 200

    def test_pyi_declares_all(self) -> None:
        import python_setup_lint.setup as m

        pyi = Path(m.__file__).with_suffix(".pyi").read_text()
        defs = len(re.findall(r"^def ", pyi, re.MULTILINE))
        consts = len(re.findall(r"^[A-Z_]+:", pyi, re.MULTILINE))
        assert defs + consts >= 3


class TestTomlHelperTypeSafety:
    @pytest.mark.parametrize(("fn_name", "data", "expected"), TOML_TYPE_CASES)
    def test_gets(self, fn_name: str, data: dict[str, Any], expected: object) -> None:
        fns = {
            "_get_dev_deps": _get_dev_deps,
            "_get_pylint_load_plugins": _get_pylint_load_plugins,
        }
        assert fns[fn_name](data) == expected

    def test_set_non_dict(self) -> None:
        for d in (
            {"tool": "nd"},
            {"tool": {"pylint": "nd"}},
            {"tool": {"pylint": {"main": "nd"}}},
        ):
            cp = dict(d)
            _set_pylint_load_plugins(cp, ["a.b"])  # type: ignore[arg-type]  # cp is dict[str, str] at runtime; _set_pylint_load_plugins expects dict[str, object]
            assert _get_pylint_load_plugins(cp) == []  # type: ignore[arg-type]  # cp is dict[str, str] at runtime; _get_pylint_load_plugins expects dict[str, object]


class TestSetPylintLoadPluginsMerge:
    @pytest.mark.parametrize(("existing", "new", "expected"), SET_PLUGINS_CASES)
    def test_cases(self, existing: object, new: list[str], expected: list[str]) -> None:
        d = {"tool": {"pylint": {"main": {"load-plugins": existing}}}}
        _set_pylint_load_plugins(d, new)  # type: ignore[arg-type]  # d has nested object values; _set_pylint_load_plugins expects dict[str, object]
        assert _get_pylint_load_plugins(d) == expected  # type: ignore[arg-type]  # d has nested object values; _get_pylint_load_plugins expects dict[str, object]


class TestConfigDrift:
    def test_update_detects_drift(self, configured_project: Path) -> None:
        """Verify that update detects config drift by checking state."""
        from python_setup_lint.setup import _read_pyproject_toml, _save_state

        d = _read_pyproject_toml(configured_project)
        assert d is not None
        _save_state(configured_project)
        (configured_project / "pyproject.toml").write_text(
            (configured_project / "pyproject.toml").read_text() + "\n# drift\n"
        )
        with _UvCallRecorder() as r:
            assert update(configured_project) == 0
        assert any("sync" in c for c in r.calls)
