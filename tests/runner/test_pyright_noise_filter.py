"""Guard against pyright noise filter regression.

Runs ``run_lint`` with pyright verify types against the python-setup repo root
with the shipped config.  Asserts the runner's printed output contains no
undesired noise patterns that the filter should have stripped.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from python_setup_lint.runner import RunnerConfig, run_lint
from tests.conftest import shipped_config_paths

pytestmark = pytest.mark.slow


def test_pyright_noise_filter(capsys: pytest.CaptureFixture[str]) -> None:
    """Run ``run_lint`` with pyright verify types and assert the filter strips noise.

    The pyright noise filter (``_summarize_pyright_verify_types`` in
    ``output.py``) extracts only the ``completenessScore`` from the raw JSON
    blob.  This test asserts that undesired patterns do NOT appear in the
    runner's printed output (post-filter).
    """
    repo_root = Path(__file__).resolve().parents[2]
    config_paths = shipped_config_paths()
    config = RunnerConfig(
        cwd=repo_root,
        package_name="python_setup_lint",
        config_paths=config_paths,
        tools_override=["pyright verify types"],
    )

    rc = run_lint(config=config)

    # Exit code may be non-zero (partial type completeness) — that's fine;
    # we only care about the printed output.
    _ = rc

    captured = capsys.readouterr()
    out = captured.out
    err = captured.err

    # The summary line *should* be present (e.g. "completenessScore=0.6").
    assert "  pyright verify types: " in out, "Expected pyright verify types summary line in output"

    # ── Assert noise is absent ──────────────────────────────────────

    # 1. No `symbols` key (the referenceCount metadata array)
    assert '"symbols"' not in out, "Found 'symbols' key in output — noise filter bypassed"

    # 2. No missing docstring/param count keys
    assert "missingFunctionDocStringCount" not in out, "Found 'missingFunctionDocStringCount' in output — noise filter bypassed"
    assert "missingClassDocStringCount" not in out, "Found 'missingClassDocStringCount' in output — noise filter bypassed"
    assert "missingDefaultParamCount" not in out, "Found 'missingDefaultParamCount' in output — noise filter bypassed"

    # 3. No raw completenessScore JSON dump.
    #    The summary line uses "completenessScore=" (no quotes, equals sign);
    #    the raw JSON uses '"completenessScore":' (with quotes, colon).
    assert '"completenessScore"' not in out, "Found raw 'completenessScore' JSON key in output — noise filter bypassed"

    # 4. No .pyi docstring warnings
    assert "No docstring found for function" not in out, (
        "Found 'No docstring found for function' in output — noise filter bypassed"
    )

    # 5. No default-values warnings for .pyi files
    assert "default values" not in out, "Found 'default values' in output — noise filter bypassed"


def test_pyright_noise_filter_bites_when_bypassed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Confirm the noise filter assertions fire when the filter is bypassed.

    Bypass ``_summarize_pyright_verify_types`` by patching it to return None,
    which triggers the else branch that prints raw JSON.  The assertions
    should all find their noise patterns present.
    """
    import python_setup_lint.runner.output as output_mod

    monkeypatch.setattr(output_mod, "_summarize_pyright_verify_types", lambda _stdout: None)

    repo_root = Path(__file__).resolve().parents[2]
    config_paths = shipped_config_paths()
    config = RunnerConfig(
        cwd=repo_root,
        package_name="python_setup_lint",
        config_paths=config_paths,
        tools_override=["pyright verify types"],
    )

    rc = run_lint(config=config)
    _ = rc

    captured = capsys.readouterr()
    out = captured.out

    # When the filter is bypassed, the summary line should NOT be present
    assert "  pyright verify types: " not in out, "Summary line should not appear when filter is bypassed"

    # All noise patterns should be present in the raw JSON
    assert '"symbols"' in out, "Expected 'symbols' key when filter bypassed; test won't guard against regression"
    assert "missingFunctionDocStringCount" in out, "Expected missingFunctionDocStringCount when filter bypassed"
    assert "missingClassDocStringCount" in out, "Expected missingClassDocStringCount when filter bypassed"
    assert "missingDefaultParamCount" in out, "Expected missingDefaultParamCount when filter bypassed"
    assert '"completenessScore"' in out, "Expected raw completenessScore JSON key when filter bypassed"
    assert "No docstring found for function" in out, "Expected .pyi docstring warnings when filter bypassed"
    assert "default values" in out, "Expected default-values warnings when filter bypassed"
