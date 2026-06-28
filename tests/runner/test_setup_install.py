"""Install-related tests for ``python_setup_lint.setup``."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Self

import pytest

from python_setup_lint._setup_precommit import (
    _AGENTS_SENTINEL,
    _AGENTS_SENTINEL_END,
    _step_agents_snippet,
    _step_precommit,
)
from python_setup_lint.setup import (
    _STATE_FILE,
    SetupState,
    _discover_checkers,
    _get_dev_deps,
    _get_pylint_load_plugins,
    _has_python_setup_dep,
    _read_pyproject_toml,
    _save_state,
    _step_add_dep,
    _step_coding_rules,
    _step_pylint_plugins,
    install,
)

# ── Helper ──────────────────────────────────────────────────────────


class _UvCallRecorder:
    """Context manager replacing _run_uv with a recording fake."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __enter__(self) -> Self:
        import python_setup_lint.setup as _m

        self._orig = _m._run_uv

        def fake(args: list[str], *, cwd: str | Path) -> tuple[int, str, str]:
            self.calls.append(args)
            return 0, "", ""

        _m._run_uv = fake
        return self

    def __exit__(self, *a: object) -> None:
        import python_setup_lint.setup as _m

        _m._run_uv = self._orig


# ── Install artifact check functions ────────────────────────────────


def _ck_dep(p: Path) -> None:
    d = _read_pyproject_toml(p)
    assert d and _has_python_setup_dep(_get_dev_deps(d))


def _ck_pylint(p: Path) -> None:
    d = _read_pyproject_toml(p)
    assert d
    plugs = _get_pylint_load_plugins(d)
    assert len(plugs) >= 4
    assert "python_setup_lint.checkers.conformance.beartype_checker" in plugs


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


# ── Step setup helpers ──────────────────────────────────────────────


def _s_noop(d: Path, mp: pytest.MonkeyPatch) -> None:
    pass


def _s_pyproject(d: Path, mp: pytest.MonkeyPatch) -> None:
    (d / "pyproject.toml").write_text(
        textwrap.dedent("""\
        [project]
        name = "test"
        version = "0.1.0"
        requires-python = ">=3.14"
        [dependency-groups]
        dev = ["ruff>=0.5"]
    """)
    )


def _s_precommit(d: Path, mp: pytest.MonkeyPatch) -> None:
    (d / ".pre-commit-config.yaml").write_text("# existing")


def _s_agents_sentinel(d: Path, mp: pytest.MonkeyPatch) -> None:
    (d / "AGENTS.md").write_text(
        f"# P\n\n{_AGENTS_SENTINEL}\nx\n{_AGENTS_SENTINEL_END}\n"
    )


def _s_pyproject_plugins(d: Path, mp: pytest.MonkeyPatch) -> None:
    _s_pyproject(d, mp)
    (d / "pyproject.toml").write_text(
        textwrap.dedent("""\
        [project]
        name = "test"
        version = "0.1.0"
        requires-python = ">=3.14"
        [tool.pylint.main]
        load-plugins = ["existing.plugin"]
    """)
    )


def _s_all_plugins(d: Path, mp: pytest.MonkeyPatch) -> None:
    plist = ", ".join(f'"{p}"' for p in _discover_checkers())
    (d / "pyproject.toml").write_text(
        textwrap.dedent(f"""\
        [project]
        name = "test"
        version = "0.1.0"
        requires-python = ">=3.14"
        [tool.pylint.main]
        load-plugins = [{plist}]
    """)
    )


def _s_fake_pkg(d: Path, mp: pytest.MonkeyPatch) -> None:
    import python_setup_lint.setup as _m

    fake = d / "fake-pkg"
    fake.mkdir()
    mp.setattr(_m, "_get_package_dir", lambda: fake)


def _s_failing_uv(d: Path, mp: pytest.MonkeyPatch) -> None:
    import python_setup_lint.setup as _m

    _s_pyproject(d, mp)
    mp.setattr(
        _m, "_run_uv", lambda args, *, cwd: (1, "", "uv add failed: network error")
    )


def _s_empty_bundled(d: Path, mp: pytest.MonkeyPatch) -> None:
    import python_setup_lint.setup as _m

    mp.setattr(_m, "_BUNDLED_CONFIGS", ())


STEP_CASES = [
    pytest.param(
        _step_pylint_plugins,
        _s_noop,
        lambda s, _: len(s.errors) > 0 and "pyproject.toml" in s.errors[0],
        id="pp_mp",
    ),
    pytest.param(
        _step_coding_rules,
        _s_fake_pkg,
        lambda s, _: len(s.errors) > 0 and "CodingRules.md" in s.errors[0],
        id="cr_ms",
    ),
    pytest.param(
        _step_agents_snippet,
        _s_noop,
        lambda s, _: s.agents_skipped and len(s.errors) == 0,
        id="as_ma",
    ),
    pytest.param(
        _step_add_dep,
        _s_noop,
        lambda s, _: len(s.errors) > 0 and "pyproject.toml" in s.errors[0],
        id="ad_mp",
    ),
    pytest.param(
        _step_agents_snippet,
        _s_agents_sentinel,
        lambda s, _: s.agents_skipped and not s.agents_appended and len(s.errors) == 0,
        id="as_ahs",
    ),
    pytest.param(
        _step_precommit,
        _s_precommit,
        lambda s, _: s.precommit_skipped and not s.precommit_written,
        id="pc_sk",
    ),
    pytest.param(
        _step_precommit,
        _s_noop,
        lambda s, d: s.precommit_written and (d / ".pre-commit-config.yaml").exists(),
        id="pc_wr",
    ),
    pytest.param(
        _step_pylint_plugins,
        _s_pyproject_plugins,
        lambda s, d: (
            s.pylint_plugins_added
            and "existing.plugin" in _get_pylint_load_plugins(_read_pyproject_toml(d))  # type: ignore[arg-type]
            and "python_setup_lint.checkers.conformance.beartype_checker"
            in _get_pylint_load_plugins(_read_pyproject_toml(d))  # type: ignore[arg-type]
        ),
        id="pp_mg",
    ),
    pytest.param(
        _step_pylint_plugins,
        _s_all_plugins,
        lambda s, _: s.pylint_plugins_skipped and not s.pylint_plugins_added,
        id="pp_sk",
    ),
    pytest.param(
        _step_add_dep,
        _s_failing_uv,
        lambda s, _: (
            len(s.errors) > 0
            and "uv add" in s.errors[0]
            and "network error" in s.errors[0]
        ),
        id="ad_uvf",
    ),
    pytest.param(
        lambda s, d: _save_state(d),
        _s_empty_bundled,
        lambda s, d: (
            len(json.loads((d / _STATE_FILE).read_text())["config_checksums"]) == 0
        ),
        id="ss_efl",
    ),
]


# ── Tests ──────────────────────────────────────────────────────────


class TestInstall:
    """Fresh install tests."""

    @pytest.mark.parametrize("check_fn", INSTALL_ARTIFACT_CASES)
    def test_artifacts(self, empty_project: Path, check_fn: object) -> None:
        assert install(empty_project, dev_path="/home/slava/aiexp/python-setup") == 0
        check_fn(empty_project)  # type: ignore[operator]


class TestInstallEdgeCases:
    """Install edge cases: idempotency, existing files, missing pyproject."""

    def test_second_install_skips_dep(self, configured_project: Path) -> None:
        deps_before = _get_dev_deps(_read_pyproject_toml(configured_project))  # type: ignore[arg-type]
        assert (
            install(configured_project, dev_path="/home/slava/aiexp/python-setup") == 0
        )
        assert _get_dev_deps(_read_pyproject_toml(configured_project)) == deps_before  # type: ignore[arg-type]

    def test_second_install_agets_no_dup(self, configured_project: Path) -> None:
        assert (configured_project / "AGENTS.md").read_text().count(
            _AGENTS_SENTINEL
        ) == 1

    def test_existing_precommit_skips(self, empty_project: Path) -> None:
        p = empty_project / ".pre-commit-config.yaml"
        p.write_text("# e")
        m = p.stat().st_mtime
        assert install(empty_project, dev_path="/home/slava/aiexp/python-setup") == 0
        assert p.stat().st_mtime == m and p.read_text() == "# e"

    def test_missing_pyproject_returns_error(self, tmp_path: Path) -> None:
        assert install(tmp_path, dev_path="/home/slava/aiexp/python-setup") == 1


class TestStepErrorPaths:
    """Step-level error path coverage."""

    @pytest.mark.parametrize(("step_fn", "setup_fn", "assert_fn"), STEP_CASES)
    def test_cases(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        step_fn: object,
        setup_fn: object,
        assert_fn: object,
    ) -> None:
        d = tmp_path
        setup_fn(d, monkeypatch)  # type: ignore[operator]
        state = SetupState()
        step_fn(state, d)  # type: ignore[operator]
        assert assert_fn(state, d)  # type: ignore[operator]


class TestDownstreamIntegration:
    """End-to-end install-then-lint integration test."""

    @pytest.mark.slow
    def test_install_then_lint(self) -> None:
        import shutil
        import subprocess

        c = Path.home() / ".tmp" / "t15-downstream"
        if c.exists():
            shutil.rmtree(c)
        c.mkdir(parents=True)
        (c / "src/consumer").mkdir(parents=True)
        (c / "src/consumer/__init__.py").write_text("# c\n")
        (c / "tests").mkdir()
        (c / "tests/__init__.py").write_text("# t\n")
        (c / "pyproject.toml").write_text(
            textwrap.dedent("""\
            [project]
            name = "consumer"
            version = "0.1.0"
            requires-python = ">=3.14"
            [dependency-groups]
            dev = ["ruff>=0.5", "python-setup"]
        """)
        )
        (c / "AGENTS.md").write_text("# C\n")
        subprocess.run(["git", "init"], cwd=c, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t"],
            cwd=c,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "t"], cwd=c, capture_output=True, check=True
        )
        subprocess.run(["git", "add", "."], cwd=c, capture_output=True, check=True)
        (c / ".secrets.baseline").write_text(
            '{"version":"1.0","plugins_used":[],"filters_used":[],'
            '"results":{},"generated_at":"2025-01-01T00:00:00Z"}\n'
        )
        (c / "tach.toml").write_text(
            '[[modules]]\npath = "src/consumer"\ndepends_on = []\n'
        )
        assert install(c, dev_path="/home/slava/aiexp/python-setup") == 0
        assert (c / ".pre-commit-config.yaml").exists()
        assert (c / "CodingRules.md").exists()
        assert "<!-- python-setup:pre-commit -->" in (c / "AGENTS.md").read_text()
        from python_setup_lint.runner import RunnerConfig, run_lint

        assert (
            run_lint(
                config=RunnerConfig(
                    cwd=c,
                    tools_override=[
                        "tach check",
                        "ruff check",
                        "mypy",
                        "ty check",
                        "pyright check",
                        "pylint",
                    ],
                ),
            )
            == 0
        )
