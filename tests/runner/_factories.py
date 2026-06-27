"""Shared non-fixture factory functions for python-setup runner tests.

Distinct from ``tests/conftest.py``: pytest auto-discovers and auto-injects
``conftest.py`` fixtures, but module-level functions used by
``@pytest.mark.parametrize`` rows at collection time must be importable.
This module is the import target — all test files do
``from tests.runner._factories import ...`` so collection never depends on
which pytest ``rootdir`` setting is active.

Factories here are pure (no side effects). Registry snapshot/restore lives
in the ``isolated_runner_registries`` fixture in ``tests/conftest.py``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from python_setup_lint.runner import TOOLS, LintResult, RunnerConfig
from python_setup_lint.runner.extra_tools import ExtraToolsConfigError
from python_setup_lint.runner.baseline import _diff_baseline

if TYPE_CHECKING:
    import pytest

# Type alias for parametrise-row callables that mutate a fake-install + runner.
InstallFakeFn = Callable[..., Any]


# The 11 built-in tool names — used both for the canned-results factory
# (dict-mode ``FakeRunCmd``) and for the "every tool dispatched" assertion
# in the orchestration tests.
ALL_TOOL_NAMES: frozenset[str] = frozenset(t.name for t in TOOLS)


def canned_results_all_tools(
    *,
    exit_code: int = 0,
    stdout: str = "",
    overrides: Mapping[str, LintResult] | None = None,
) -> dict[str, LintResult]:
    """Build the 12-tool canned-result dict for ``fake_run_cmd_factory``.

    Every built-in label maps to a ``LintResult`` with defaults; pass
    *overrides* to vary any subset. Used by the orchestration / smoke
    tests so they stop repeating the 12-key dict literal.
    """
    # Late import to avoid any conftest-collection ordering surprise.
    from python_setup_lint.testing import make_lint_result

    base = {
        name: make_lint_result(tool_name=name, exit_code=exit_code, stdout=stdout)
        for name in ALL_TOOL_NAMES
    }
    if overrides:
        base.update(overrides)
    return base


def install_fake_runner(
    monkeypatch: pytest.MonkeyPatch,
    overrides: Mapping[str, LintResult] | None = None,
    *,
    package_name: str | None = "python_setup_lint",
    default_py_dirs: list[str] | None = None,
) -> tuple[Any, RunnerConfig]:
    """Install a fake ``_run_cmd`` on the runner module + build a matching ``RunnerConfig``.

    Replaces the 3-line ``fake = fake_run_cmd_factory({}); monkeypatch.setattr(_runner_module, "_run_cmd", fake)``
    boilerplate duplicated in 25+ runner tests. Returns ``(fake, config)`` so callers
    can introspect ``fake.calls`` after invoking ``run_lint(config=config, ...)`` /
    ``main([..], config=config)``.
    """
    import python_setup_lint.runner.output as _output_module
    from python_setup_lint.testing import fake_run_cmd_factory

    fake = fake_run_cmd_factory(dict(overrides) if overrides else {})
    monkeypatch.setattr(_output_module, "_run_cmd", fake)
    cfg = RunnerConfig(
        cwd=Path.cwd(),
        package_name=package_name,
        default_py_dirs=default_py_dirs
        if default_py_dirs is not None
        else ["src", "scripts", "tests"],
    )
    return fake, cfg


def tmp_config(tmp_path: Path, **overrides: Any) -> RunnerConfig:
    """Build a default test ``RunnerConfig`` rooted at *tmp_path*; *overrides* win."""
    defaults: dict[str, Any] = {
        "cwd": tmp_path,
        "package_name": "python_setup_lint",
        "default_py_dirs": ["src", "scripts", "tests"],
    }
    defaults.update(overrides)
    return RunnerConfig(**defaults)


def write_baseline(
    tmp_path: Path, /, entries: list[dict[str, Any]], name: str = "baseline.json"
) -> Path:
    """Write a JSON baseline file under *tmp_path* and return its path."""
    path = tmp_path / name
    path.write_text(json.dumps(entries))
    return path


def diff_baseline_with(
    tmp_path: Path,
    /,
    saved: dict[str, Any] | list[dict[str, Any]],
    current: Iterable[LintResult],
    *,
    baseline_name: str = "baseline.json",
) -> tuple[list[str], list[dict[str, Any]]]:
    """Write *saved*, run ``_diff_baseline`` against *current*, return ``(violations, reloaded_baseline)``.

    Removes the 4-line write-then-call-then-json.load boilerplate that
    every ``TestBaseline`` test duplicates. The returned ``reloaded`` is
    the post-diff on-disk state (which ``_diff_baseline`` may have mutated
    in place when handling shrinkage).

    Accepts a single saved entry OR a list of saved entries; a single
    dict is wrapped in a list before writing.
    """
    saved_list = [saved] if isinstance(saved, dict) else list(saved)
    baseline_path = write_baseline(tmp_path, saved_list, name=baseline_name)
    violations = _diff_baseline(list(current), baseline_path)
    reloaded = json.loads(baseline_path.read_text())
    return violations, reloaded


def assert_violation_contains_any(violations: list[str], *needles: str) -> None:
    """Assert at least one violation mentions at least one *needle* (case-insensitive)."""
    lowered = [v.lower() for v in violations]
    found = any(any(n in v for v in lowered) for n in needles)
    assert found, (
        f"Expected a violation mentioning any of {needles!r}; got {violations!r}"
    )


def extra_block(entries: str) -> str:
    """Wrap one-or-more ``[[tool.python-setup-lint.extra-tools]]`` body lines."""
    return (
        f"[tool.python-setup-lint]\n[[tool.python-setup-lint.extra-tools]]\n{entries}"
    )


def write_pyproject(tmp_path: Path, body: str) -> Path:
    """Write a synthetic ``pyproject.toml`` body under *tmp_path*, reset extras cache, return resolved path."""
    from python_setup_lint.runner.extra_tools import _reset_extra_tools_cache

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(body, encoding="utf-8")
    _reset_extra_tools_cache()
    return pyproject.resolve()


def lint_config(
    cwd: Path,
    /,
    *,
    package_name: str | None = "python_setup_lint",
    tools_override: list[str] | None = None,
) -> RunnerConfig:
    """Build a test RunnerConfig rooted at *cwd* with optional tools override."""
    return RunnerConfig(
        cwd=cwd, package_name=package_name, tools_override=tools_override
    )


def assert_r4_reason(
    err: ExtraToolsConfigError, /, pyproject: Path, reason_want: str, want_kind: str
) -> None:
    """Assert ``ExtraToolsConfigError.location`` matches *pyproject* + reason by kind."""
    assert err.location == str(pyproject), (
        f"location mismatch: got {err.location!r}, want {str(pyproject)!r}"
    )
    if want_kind == "exact":
        assert err.reason == reason_want, (
            f"reason mismatch: got {err.reason!r}, want {reason_want!r}"
        )
    else:  # starts_with
        assert err.reason.startswith(reason_want), (
            f"reason mismatch: got {err.reason!r}, want prefix {reason_want!r}"
        )


# ── Re-exports from split files ─────────────────────────────────────
