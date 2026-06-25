"""Shared test infrastructure for pylint checker tests and lint-runner fakes.

Checker helpers:
- ``_make_tc`` — creates a ``CheckerTestCase`` for a given checker class.
- ``_walk_and_release`` — parses code, walks checker, returns released messages.

Lint-runner fakes:
- ``make_lint_result`` — convenience factory for ``LintResult``.
- ``fake_run_cmd_factory`` — builds a callable that returns canned ``LintResult``
  by tool label or call order, capturing every ``cmd`` it receives.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import astroid
from pylint.testutils import CheckerTestCase

if TYPE_CHECKING:
    from pylint.checkers import BaseChecker

    from python_setup_lint.runner import LintResult


def _make_tc(checker_class: type[BaseChecker]) -> CheckerTestCase:
    """Create a ``CheckerTestCase`` for *checker_class*.

    Sets ``CHECKER_CLASS``, calls ``setup_method()``, returns the test case.
    """
    tc = CheckerTestCase()
    tc.CHECKER_CLASS = checker_class
    tc.setup_method()
    return tc


def _walk_and_release(
    code: str,
    checker_class: type[BaseChecker],
    *,
    file_path: str | None = None,
    module_name: str = "",
) -> list[Any]:
    """Parse *code*, walk *checker_class* over it, return released messages.

    Optionally set *file_path* for path-dependent logic (source-roots,
    test classification) and *module_name* for the astroid module name.
    """
    tc = _make_tc(checker_class)
    module = astroid.parse(code, module_name=module_name)
    if file_path is not None:
        module.file = file_path
    tc.walk(module)
    return tc.linter.release_messages()


# ── Lint-runner fakes ──────────────────────────────────────────────


def make_lint_result(
    tool_name: str = "ruff check",
    exit_code: int = 0,
    stdout: str = "",
    stderr: str = "",
    elapsed: float = 0.0,
) -> LintResult:
    """Build a ``LintResult`` with defaults for test convenience.

    Parameters are identical to ``LintResult`` fields; only *tool_name*
    and *exit_code* are commonly varied in tests.
    """
    # late import to avoid circular dependency at module level
    from python_setup_lint.runner import LintResult as _LintResult

    return _LintResult(
        tool_name=tool_name,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        elapsed=elapsed,
    )


@dataclass
class _FakeRunCmdRecord:
    """Record of a single call captured by a fake ``_run_cmd``.

    Attributes:
        cmd: The full command list the runner constructed.
        label: The tool name (``spec.name``) passed as the ``label`` kwarg.
    """

    cmd: list[str]
    label: str


@dataclass
class FakeRunCmd:
    """Callable that replaces ``_run_cmd`` in tests.

    Dispatches by ``label`` (tool name) when constructed from a dict, or by
    call order when constructed from a list.  Every call is recorded in
    :attr:`calls` so tests can assert on constructed commands.

    Dict mode — unknown labels return a zero-exit empty result (implicit
    skip, e.g. when ``package_name`` is ``None`` and stubtest/verifytypes
    are not run).
    """

    results: dict[str, LintResult] | list[LintResult]
    calls: list[_FakeRunCmdRecord] = field(default_factory=list)

    def __call__(
        self, cmd: list[str], *, cwd: Path = Path(), label: str = ""
    ) -> LintResult:
        """Match ``_run_cmd(cmd, *, cwd, label) -> LintResult`` signature."""
        self.calls.append(_FakeRunCmdRecord(cmd=cmd, label=label))
        if isinstance(self.results, dict):
            return self.results.get(
                label,
                make_lint_result(tool_name=label),
            )
        # list mode — pop front
        idx = len(self.calls) - 1
        if idx < len(self.results):
            return self.results[idx]
        return make_lint_result(tool_name=label)


def fake_run_cmd_factory(
    results: dict[str, LintResult] | list[LintResult],
) -> FakeRunCmd:
    """Build a ``FakeRunCmd`` that returns canned ``LintResult`` values.

    * Dict mode — keys are tool labels (``spec.name``).  Unknown labels
      return a zero-exit empty result (implicit skip).
    * List mode — results are returned in call order.  Extra calls beyond
      the list length return a zero-exit empty result.

    The returned ``FakeRunCmd`` is a callable matching the ``_run_cmd``
    signature.  Attach it via::

        monkeypatch.setattr(
            python_setup_lint.runner, "_run_cmd", fake_run_cmd_factory(...)
        )

    After the test, inspect ``fake.calls`` to assert on constructed commands.
    """
    return FakeRunCmd(results=results)


# ── Consumer-agnostic health checks ───────────────────────────────
#
# ``test_checked_main`` and the ``assert_*_precommit_*`` validators are
# intended for reuse by any ``python-setup`` consumer.  They contain no
# project-specific paths; the consumer supplies ``repo_root`` and
# (optionally) the baseline filename, so the same code validates every
# project's ``.pre-commit-config.yaml`` generated from the shared template.


def test_checked_main() -> None:
    """Run pytest with typeguard enabled (consumer-agnostic).

    Equivalent to ``pytest -p typeguard -q tests/unit`` with trailing
    ``sys.argv`` passthrough.  Uses the ``typeguard`` pytest plugin
    (``-p typeguard``) rather than ``--typeguard-packages=<name>`` so the
    entry point does not hardcode any package name — any consumer can
    wire ``test-checked = "python_setup_lint.testing:test_checked_main"``
    in its ``[project.scripts]`` and delete its local wrapper.

    Consumers that want typeguard scoped to a single package may keep a
    ``typeguard-packages`` key in ``[tool.pytest.ini_options]``; the plugin
    honours that ini value when present and instruments every package
    otherwise.
    """
    import sys

    import pytest

    args = ["-p", "typeguard", "-q", "tests/unit"]
    args.extend(sys.argv[1:])
    sys.exit(pytest.main(args))


def _load_precommit_config(repo_root: Path) -> dict[str, Any]:
    """Load and return ``repo_root / .pre-commit-config.yaml`` as a dict.

    Raises ``AssertionError`` (with a helpful message) when the file is
    missing or not a YAML mapping with a ``repos`` key, so callers can use
    the return value without re-validating.
    """
    import yaml

    config_path = repo_root / ".pre-commit-config.yaml"
    assert config_path.exists(), f"Missing pre-commit config: {config_path}"
    with open(config_path) as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict), (
        "Expected .pre-commit-config.yaml to be a YAML mapping (dict)"
    )
    assert "repos" in data, "Expected 'repos' key in pre-commit config"
    return data


def assert_precommit_config_valid(repo_root: Path) -> None:
    """Assert ``.pre-commit-config.yaml`` is valid YAML + passes ``validate-config``.

    Consumer-agnostic: works against any ``python-setup``-generated config.
    Runs ``pre-commit validate-config`` against the file (caller's
    responsibility to ensure ``pre-commit`` is installed in the active env).
    """
    config_path = repo_root / ".pre-commit-config.yaml"
    _load_precommit_config(repo_root)  # raises AssertionError on YAML/shape errors
    result = subprocess.run(  # noqa: S603 - path is constructed, not user input
        ["pre-commit", "validate-config", str(config_path)],
        check=False,
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"pre-commit validate-config failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
    )


def assert_precommit_hooks_shape(
    repo_root: Path,
    *,
    baseline_filename: str = "lint.baseline",
) -> None:
    """Assert the pre-commit hook shape matches the shared template contract.

    Checked invariants (consumer-agnostic):
    * a ``lint`` local hook exists, uses ``language: system``, and its entry
      contains ``--no-fail-fast`` and ``--baseline <baseline_filename>``;
    * the ruff fix hook carries ``--fix``;
    * the fast hooks (``ruff-format``, ``ruff``) run on the ``pre-commit`` stage.

    Raises ``AssertionError`` on the first violated invariant.
    """
    config = _load_precommit_config(repo_root)

    def _find_hook(hook_id: str) -> dict[str, Any] | None:
        for repo in config.get("repos", []):
            for hook in repo.get("hooks", []):
                if isinstance(hook, dict) and hook.get("id") == hook_id:
                    return hook
        return None

    lint_hook = _find_hook("lint")
    assert lint_hook is not None, "Missing 'lint' local hook in .pre-commit-config.yaml"
    assert lint_hook.get("language") == "system", (
        "'lint' hook must use language: system"
    )
    lint_entry = lint_hook.get("entry", "")
    assert "--no-fail-fast" in lint_entry, (
        f"'lint' entry must contain --no-fail-fast, got: {lint_entry!r}"
    )
    assert f"--baseline {baseline_filename}" in lint_entry, (
        f"'lint' entry must contain --baseline {baseline_filename}, got: {lint_entry!r}"
    )

    ruff_hook = _find_hook("ruff") or _find_hook("ruff-check")
    assert ruff_hook is not None, "Missing ruff fix hook (id 'ruff' or 'ruff-check')"
    ruff_args = ruff_hook.get("args", [])
    assert "--fix" in ruff_args, (
        f"ruff fix hook must carry --fix, got args: {ruff_args!r}"
    )

    for fast_id in ("ruff-format", "ruff", "ruff-check"):
        fast_hook = _find_hook(fast_id)
        if fast_hook is None:
            continue
        stages = fast_hook.get("stages", [])
        assert "pre-commit" in stages or stages == [], (
            f"fast hook '{fast_id}' must run on the pre-commit stage, got stages: {stages!r}"
        )
