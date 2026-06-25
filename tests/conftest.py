"""Shared pytest fixtures for python-setup runner tests.

Pure factory functions (used by ``@pytest.mark.parametrize`` rows at
collection time) live in ``tests/runner/_factories.py`` — pytest auto-
discovers ``conftest.py`` for fixtures only, not module-level callables.

This file holds:

- ``tmp_baseline`` — builder bound to the test's ``tmp_path``.
- ``runner_config_factory`` — ``RunnerConfig`` builder with sane defaults.
- ``isolated_runner_registries`` — snapshot+restore ``LINT_TOOLS``/``STRATEGIES``
  around any test that mutates them (extras-merge, register_lint_tool).
- ``empty_project`` / ``configured_project`` — setup-test project dirs.
"""

from __future__ import annotations

import textwrap
from collections.abc import Callable, Iterable
from pathlib import Path

import pytest

from python_setup_lint.runner import (
    LINT_TOOLS,
    STRATEGIES,
    RunnerConfig,
    _reset_extra_tools_cache,
)

# ── Project fixtures for setup tests ────────────────────────────────


@pytest.fixture
def empty_project(tmp_path: Path) -> Path:
    """Create a temp dir with a minimal pyproject.toml and AGENTS.md."""
    d = tmp_path
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
    from python_setup_lint.setup import install

    rc = install(empty_project, dev_path="/home/slava/aiexp/python-setup")
    assert rc == 0
    return empty_project


@pytest.fixture
def tmp_baseline(tmp_path: Path) -> Callable[..., Path]:
    """Return ``write_baseline`` (from ``tests.runner._factories``) bound to *tmp_path*."""
    from tests.runner._factories import write_baseline

    def _write(entries: list[dict[str, object]], name: str = "baseline.json") -> Path:
        return write_baseline(tmp_path, entries, name=name)
    return _write


@pytest.fixture
def runner_config_factory(tmp_path: Path) -> Callable[..., RunnerConfig]:
    """Build a ``RunnerConfig`` rooted at *tmp_path* with sensible test defaults."""
    def _make(
        *,
        cwd: Path | None = None,
        package_name: str | None = "python_setup_lint",
        default_py_dirs: list[str] | None = None,
        tools_override: list[str] | None = None,
        config_paths: dict[str, Path] | None = None,
    ) -> RunnerConfig:
        return RunnerConfig(
            cwd=cwd if cwd is not None else tmp_path,
            package_name=package_name,
            default_py_dirs=default_py_dirs if default_py_dirs is not None else ["src", "scripts", "tests"],
            tools_override=tools_override,
            config_paths=config_paths or {},
        )
    return _make


@pytest.fixture
def isolated_runner_registries() -> Iterable[None]:
    """Snapshot + restore ``LINT_TOOLS``/``STRATEGIES`` + extras cache around each test.

    Required for any test that mutates ``LINT_TOOLS`` or ``STRATEGIES``
    (e.g. ``register_lint_tool`` extras-merge tests, T8 fail-fast
    clean-pyproject test). Without isolation, leaked mutations corrupt
    the fake-count assertions of later tests in the same process.
    """
    baseline_tools = list(LINT_TOOLS)
    baseline_strategies = dict(STRATEGIES)
    _reset_extra_tools_cache()
    yield
    LINT_TOOLS[:] = baseline_tools
    STRATEGIES.clear()
    STRATEGIES.update(baseline_strategies)
    _reset_extra_tools_cache()
