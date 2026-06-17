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

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import astroid
from pylint.testutils import CheckerTestCase

if TYPE_CHECKING:
    from pylint.checkers import BaseChecker

    import pytest

    from python_setup_lint.runner import LintResult


def _make_tc(checker_class: type[BaseChecker]) -> CheckerTestCase:
    """Create a ``CheckerTestCase`` for *checker_class*.

    Sets ``CHECKER_CLASS``, calls ``setup_method()``, returns the test case.
    """


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

    def __call__(self, cmd: list[str], *, cwd: Path = Path(), label: str = "") -> LintResult:
        """Match ``_run_cmd(cmd, *, cwd, label) -> LintResult`` signature."""


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