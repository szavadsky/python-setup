"""Unit tests for ``python_setup_lint.testing`` lint-runner fakes.

Covers ``make_lint_result``, ``fake_run_cmd_factory``, and ``FakeRunCmd``
behaviour: dict dispatch, list dispatch, unknown-label fallback, cmd capture,
and a smoke integration test that exercises ``run_lint(...)`` with the fake
installed (no real subprocess spawned).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import python_setup_lint.runner.output as _output_module
from python_setup_lint.runner import LintResult, RunnerConfig, run_lint
from python_setup_lint.testing import (
    FakeRunCmd,
    _FakeRunCmdRecord,
    fake_run_cmd_factory,
    make_lint_result,
)
from tests.runner._factories import canned_results_all_tools
from tests.runner._factories_extras import (
    CALLS_CAPTURED_CASES,
    DISPATCH_CASES,
    RUN_LINT_FAKE_INVARIANT_CASES,
)

# ── make_lint_result ────────────────────────────────────────────────
# Factory defaults sanity + full-override round-trip; the factory is thin
# enough that exhaustive per-field echo would be tautology (per T12 QA).


def test_make_lint_result_defaults_and_override_apply() -> None:
    r_default = make_lint_result()
    assert isinstance(r_default, LintResult)
    assert (
        r_default.tool_name,
        r_default.exit_code,
        r_default.stdout,
        r_default.stderr,
        r_default.elapsed,
    ) == (
        "ruff check",
        0,
        "",
        "",
        0.0,
    )
    r = make_lint_result(
        tool_name="mypy", exit_code=1, stdout="err", stderr="d", elapsed=2.5
    )
    assert (r.tool_name, r.exit_code, r.stdout, r.stderr, r.elapsed) == (
        "mypy",
        1,
        "err",
        "d",
        2.5,
    )


@pytest.mark.parametrize(("kind", "results", "calls", "expected_exits", "expected_names"), DISPATCH_CASES)
def test_dispatch_returns_expected_result(
    kind: str, results: Any, calls: Any, expected_exits: Any, expected_names: Any
) -> None:
    """Each dispatch-mode row returns the canned ``exit_code``/``tool_name`` for the call."""
    fake = (
        fake_run_cmd_factory(results) if kind == "dict" else FakeRunCmd(results=results)
    )
    for (cmd, label), exp_exit, exp_name in zip(
        calls, expected_exits, expected_names, strict=True
    ):
        out = fake(cmd, label=label)
        assert out.exit_code == exp_exit
        assert out.tool_name == exp_name


def test_list_dispatch_extra_calls_return_zero_exit_empty() -> None:
    """List mode — calls beyond the list return a zero-exit result with the call's label."""
    fake = fake_run_cmd_factory([make_lint_result(tool_name="tool_a", exit_code=1)])
    assert fake(["tool_a"], label="tool_a").exit_code == 1
    for label in ("tool_b", "tool_c"):
        out = fake([label], label=label)
        assert out.exit_code == 0 and out.tool_name == label


@pytest.mark.parametrize(("results", "calls", "expected_records"), CALLS_CAPTURED_CASES)
def test_calls_captured_in_order(
    results: Any, calls: Any, expected_records: Any
) -> None:
    """Both dispatch modes record every call as ``_FakeRunCmdRecord(cmd, label)`` in order."""
    fake = fake_run_cmd_factory(results)
    for cmd, label in calls:
        fake(cmd, label=label)
    assert len(fake.calls) == len(expected_records)
    for record, want in zip(fake.calls, expected_records, strict=True):
        assert isinstance(record, _FakeRunCmdRecord)
        assert record.cmd == want["cmd"]
        assert record.label == want["label"]


def test_dict_empty_dict_multiple_labels_zero_exit() -> None:
    """Empty dict — multiple different labels all get a zero-exit empty result."""
    fake = fake_run_cmd_factory({})
    r1 = fake(["ruff", "check", "."], label="ruff check")
    r2 = fake(["mypy", "."], label="mypy")
    assert r1.exit_code == 0 and r2.exit_code == 0
    assert r1.tool_name == "ruff check" and r2.tool_name == "mypy"


@pytest.mark.parametrize(("results", "label", "expected_exit"), [
    ({"mypy": make_lint_result(tool_name="mypy", exit_code=2)}, "mypy", 2),
    (
        [
            make_lint_result(tool_name="tool_a", exit_code=0),
            make_lint_result(tool_name="tool_b", exit_code=1),
        ],
        "tool_b",
        1,
    ),
],
ids=["dict_direct", "list_direct"],)
def test_fake_run_cmd_direct_construction(
    results: Any, label: str, expected_exit: int
) -> None:
    """``FakeRunCmd(results=...)`` dispatches identically to the factory path."""
    fake = FakeRunCmd(results=results)
    if isinstance(results, list):  # list mode: call the FIRST tool to reach the second
        fake(["tool_a"], label="tool_a")
    assert fake([label], label=label).exit_code == expected_exit


# ── Smoke integration: run_lint with the fake installed ────────────
# Parametrised (kwargs, predicate) invariant table. Each row asserts a
# distinct behavioural invariant of ``run_lint`` with the fake installed
# (tool count, --fix propagation, --exclude propagation, package_name=None
# skip). Uses ``canned_results_all_tools()`` to avoid the 13-key dict literal.


def _install_fake_and_run(
    monkeypatch: pytest.MonkeyPatch, **run_lint_kwargs: Any
) -> FakeRunCmd:
    """Install a 13-tool dict-mode ``FakeRunCmd`` + invoke ``run_lint``.

    ``package_name=None`` ⇒ skip stubtest+verifytypes. Returns ``fake`` for assertion.
    Resets ``LINT_TOOLS`` to built-in ``TOOLS`` to avoid cross-test pollution.
    """
    from python_setup_lint.runner import LINT_TOOLS, TOOLS
    from python_setup_lint.runner.extra_tools import _reset_extra_tools_cache

    LINT_TOOLS[:] = list(TOOLS)
    _reset_extra_tools_cache()
    fake = fake_run_cmd_factory(canned_results_all_tools())
    monkeypatch.setattr(_output_module, "_run_cmd", fake)
    config = RunnerConfig(
        cwd=Path.cwd(),
        package_name=run_lint_kwargs.pop("package_name", "python_setup_lint"),
    )
    rc = run_lint(config=config, **run_lint_kwargs)
    assert isinstance(rc, int)
    return fake


@pytest.mark.parametrize(("run_lint_kwargs", "predicate"), RUN_LINT_FAKE_INVARIANT_CASES)
def test_run_lint_with_fake_dispatch_invariants(
    monkeypatch: pytest.MonkeyPatch,
    run_lint_kwargs: dict[str, Any],
    predicate: Callable[[FakeRunCmd], bool],
    isolated_runner_registries: None,
) -> None:
    """One ``run_lint(...)`` + 13-tool fake; the row's predicate asserts the invariant."""
    fake = _install_fake_and_run(monkeypatch, **run_lint_kwargs)
    assert predicate(fake), f"Invariant failed; calls={[c.label for c in fake.calls]}"


def test_run_lint_with_fake_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the fake returns zero-exit empty results for every tool, ``run_lint`` exits 0."""
    fake = fake_run_cmd_factory(canned_results_all_tools())
    monkeypatch.setattr(_output_module, "_run_cmd", fake)
    config = RunnerConfig(cwd=Path.cwd(), package_name="python_setup_lint")
    assert (
        run_lint(config=config, path="src/python_setup_lint/runner.py")
        == 0
    )


def test_fake_no_subprocess_spawned(monkeypatch: pytest.MonkeyPatch) -> None:
    """No ``subprocess.run`` call for any lint tool reaches the real OS with the fake installed."""
    import subprocess

    original_run = subprocess.run
    spy_calls: list[list[str]] = []

    def spy_run(*args: object, **kwargs: object) -> object:
        cmd = args[0] if args else kwargs.get("args", [])
        spy_calls.append(list(cmd) if isinstance(cmd, (list, tuple)) else [str(cmd)])
        return original_run(*args, **kwargs, check=False)  # type: ignore[call-overload]  # test helper; check=False is valid at runtime

    monkeypatch.setattr(subprocess, "run", spy_run)
    fake = fake_run_cmd_factory(canned_results_all_tools())
    monkeypatch.setattr(_output_module, "_run_cmd", fake)
    config = RunnerConfig(cwd=Path.cwd(), package_name="python_setup_lint")
    run_lint(config=config, path="src/python_setup_lint/runner.py")

    lint_calls = [
        c for c in spy_calls if any(t in c for t in ("ruff", "mypy", "pylint"))
    ]
    assert lint_calls == [], (
        f"Expected no subprocess.run for lint tools; got: {lint_calls}"
    )
