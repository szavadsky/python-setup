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
from beartype import beartype
from pylint.testutils import CheckerTestCase

from python_setup_lint.runner import LintResult  # noqa: TC001

if TYPE_CHECKING:
    from pylint.checkers import BaseChecker

def _make_tc(checker_class: type[BaseChecker]) -> CheckerTestCase:
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
    tc = _make_tc(checker_class)
    module = astroid.parse(code, module_name=module_name)
    if file_path is not None:
        module.file = file_path
    tc.walk(module)
    return tc.linter.release_messages()


# ── Lint-runner fakes ──────────────────────────────────────────────


@beartype
def make_lint_result(
    tool_name: str = "ruff check",
    exit_code: int = 0,
    stdout: str = "",
    stderr: str = "",
    elapsed: float = 0.0,
) -> LintResult:
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


@beartype
def fake_run_cmd_factory(
    results: dict[str, LintResult] | list[LintResult],
) -> FakeRunCmd:
    return FakeRunCmd(results=results)


# ── Consumer-agnostic health checks ───────────────────────────────
#
# ``test_checked_main`` and the ``assert_*_precommit_*`` validators are
# intended for reuse by any ``python-setup`` consumer.  They contain no
# project-specific paths; the consumer supplies ``repo_root`` and
# (optionally) the baseline filename, so the same code validates every
# project's ``.pre-commit-config.yaml`` generated from the shared template.


@beartype
def test_checked_main() -> None:
    import sys

    import pytest

    args = ["-p", "typeguard", "-q", "tests/unit"]
    args.extend(sys.argv[1:])
    sys.exit(pytest.main(args))


def _load_precommit_config(repo_root: Path) -> dict[str, Any]:
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


@beartype
def assert_precommit_config_valid(repo_root: Path) -> None:
    config_path = repo_root / ".pre-commit-config.yaml"
    _load_precommit_config(repo_root)  # raises AssertionError on YAML/shape errors
    result = subprocess.run(  # noqa: S603 - pre-commit is a trusted project tool
        ["pre-commit", "validate-config", str(config_path)],  # noqa: S607 - pre-commit is a trusted project tool
        check=False,
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"pre-commit validate-config failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
    )


@beartype
def assert_precommit_hooks_shape(
    repo_root: Path,
    *,
    baseline_filename: str = "lint.baseline",
) -> None:
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
