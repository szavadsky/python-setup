"""Consolidated real-pipeline smoke test.

Replaces all per-site real-pipeline slow variants with a single
``@pytest.mark.slow`` test that exercises the full lint pipeline end-to-end
on a minimal synthetic project.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from python_setup_lint.runner import TOOLS, RunnerConfig, run_lint


@pytest.mark.slow
def test_consolidated_real_pipeline_smoke(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """Run the full lint pipeline on a minimal synthetic project.

    Asserts:
    - ``isinstance(rc, int)`` — the pipeline ran to completion.
    - All 11 tools appear in the printed output (captured via capsys).
    """
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "main.py").write_text("def greet(name: str) -> str:\n    return f'hello {name}'\n")

    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'smoke-test'\nversion = '0.1.0'\n")
    (tmp_path / ".secrets.baseline").write_text("{}")

    config = RunnerConfig(cwd=tmp_path, package_name="smoke_test")

    rc = run_lint(config=config, no_fail_fast=True)
    assert isinstance(rc, int), f"Expected int exit code, got {type(rc)}: {rc}"

    captured = capsys.readouterr()
    tool_names = {t.name for t in TOOLS}
    for name in tool_names:
        assert f"[{name}]" in captured.out, (
            f"Expected tool '{name}' output in lint output. "
            f"Missing from: {captured.out[:2000]}"
        )
