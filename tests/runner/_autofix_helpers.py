"""Shared helpers for autofix conflict tests."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from python_setup_lint.runner import LINT_TOOLS, LintResult
from python_setup_lint.testing import make_lint_result
from tests.runner._factories import canned_results_all_tools
from python_setup_lint.runner import RunnerConfig, ToolSpec
from python_setup_lint.runner._autofix import _apply_autofix_conflict_aware
from python_setup_lint.testing import fake_run_cmd_factory
from tests.runner._factories import tmp_config

_CANARY_LABEL = "python-setup:autofix-canary"

_FIX_TOOL_NAMES: frozenset[str] = frozenset(
    t.name for t in LINT_TOOLS if t.supports_fix
)

assert {"ruff check", "rumdl check", "ty check"} == _FIX_TOOL_NAMES, (
    f"Built-in supports_fix set drifted: {_FIX_TOOL_NAMES!r}"
)


# ── Git scaffolding ───────────────────────────────────────────────


def _git_init(cwd: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=cwd, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=cwd, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=cwd, check=True, capture_output=True,
    )


def _write_file(cwd: Path, rel: str, content: str) -> Path:
    p = cwd / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _stage(cwd: Path, rel: str) -> None:
    subprocess.run(["git", "add", rel], cwd=cwd, check=True, capture_output=True)


def _commit_all(cwd: Path, msg: str = "init") -> None:
    subprocess.run(["git", "add", "."], cwd=cwd, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", msg], cwd=cwd, check=True, capture_output=True,
    )


def _make_canned_fix_results(
    *, canary_e999_files: tuple[str, ...] = (),
) -> dict[str, LintResult]:  # pylint: disable=generic-key-dict  # dict[str, LintResult] is a test helper; string keys are fixture labels
    base = canned_results_all_tools(exit_code=0, stdout="")
    canary_stdout = "\n".join(
        f"{f}:1:1: E999 SyntaxError" for f in canary_e999_files
    ) if canary_e999_files else ""
    base[_CANARY_LABEL] = make_lint_result(
        tool_name=_CANARY_LABEL, exit_code=1, stdout=canary_stdout,
    )
    return base


# ── Helper: post-fix fake that simulates the tool writing bytes to file ─


class _PostFixFakeRunCmd:
    def __init__(
        self,
        inner: Callable[..., LintResult],
        *,
        post_fix_path: Path,
        post_fix_content: str,
    ) -> None:
        self._inner = inner
        self._post_fix_path = post_fix_path
        self._post_fix_content = post_fix_content
        self._post_fix_written = False
        self._post_call_snapshots: list[tuple[str, str | None]] = []

    def __call__(self, cmd: list[str], *, cwd: Path, label: str) -> LintResult:
        if label in _FIX_TOOL_NAMES and not self._post_fix_written:
            self._post_fix_path.write_text(self._post_fix_content, encoding="utf-8")
            self._post_fix_written = True
        try:
            after = self._post_fix_path.read_text(encoding="utf-8")
        except FileNotFoundError:  # pylint: disable=silent-except  # test helper; FileNotFoundError is expected during cleanup
            after = None
        self._post_call_snapshots.append((label, after))
        return self._inner(cmd, cwd=cwd, label=label)

    def snapshots_after_label(self, label: str) -> str | None:
        for seen_label, after in reversed(self._post_call_snapshots):
            if seen_label == label:
                return after
        return None


def _setup_e999_canary_revert(
    tmp_path: Path,
    *,
    original: str,
    post_fix: str,
    target: Path,
    canned: dict[str, LintResult],
    make_spec: Callable[[], ToolSpec],
    config: RunnerConfig | None = None,
) -> _PostFixFakeRunCmd:
    """Set up the E999-canary-revert test scenario and return the wrapped run_cmd.

    The caller must call ``capsys.readouterr()`` after this returns.
    """
    wrapped = _PostFixFakeRunCmd(
        fake_run_cmd_factory(canned),
        post_fix_path=target,
        post_fix_content=post_fix,
    )
    _apply_autofix_conflict_aware(
        make_spec(),
        config=config or tmp_config(tmp_path),
        paths_to_check=["src/main.py"],
        run_cmd=wrapped,
    )
    return wrapped
