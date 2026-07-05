"""Guard against python-setup's own self-lint regression.

Runs the full lint pipeline (all 13 tools) against the python-setup repo root
with the shipped config.  A self-lint regression (new violation, crash, or
unexpected skip) fails this test rather than slipping into CI.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from python_setup_lint.runner import RunnerConfig, run_lint
from python_setup_lint.runner._config import _SHIPPED_CONFIG_FILES

pytestmark = pytest.mark.slow


def _shipped_config_paths() -> dict[str, Path]:
    """Build config_paths dict from the python-setup project root config/ dir."""
    config_root = Path("config")
    paths: dict[str, Path] = {}
    for tool_label, filename in _SHIPPED_CONFIG_FILES.items():
        candidate = config_root / filename
        if candidate.is_file():
            paths[tool_label] = candidate.resolve()
    return paths


def test_self_lint_clean(capsys: pytest.CaptureFixture[str]) -> None:
    """Run ``run_lint`` against the real python-setup repo with shipped config.

    Asserts:
    - Exit code == 0
    - No ``[CRASH]`` in captured output
    - No ``SKIPPED:`` lines for reasons other than ``--package-name not set``
    - Pylint score is 10.0 (all checks pass)
    """
    repo_root = Path(__file__).resolve().parents[2]
    config_paths = _shipped_config_paths()
    config = RunnerConfig(
        cwd=repo_root,
        package_name="python_setup_lint",
        config_paths=config_paths,
    )

    rc = run_lint(config=config)

    # Exit code must be 0
    assert rc == 0, f"Expected exit code 0, got {rc}"

    captured = capsys.readouterr()
    out = captured.out
    err = captured.err

    # No [CRASH]
    assert "[CRASH]" not in out, "Unexpected [CRASH] in lint output"
    assert "[CRASH]" not in err, "Unexpected [CRASH] in stderr"

    # No SKIPPED: for non--package-name reasons
    for line in out.split("\n") + err.split("\n"):
        stripped = line.strip()
        if "SKIPPED:" in stripped and "--package-name not set" not in stripped:
            pytest.fail(f"Unexpected SKIPPED line: {stripped}")

    # Pylint score: 10.0 (JSON output: "score": 10.0)
    assert '"score": 10.0' in out or '"score":10.0' in out, (
        "Pylint score not 10.0 in output.  A lint violation or warning was introduced."
    )
