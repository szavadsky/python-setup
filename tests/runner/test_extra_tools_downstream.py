"""Downstream-integration + observability + perf-benchmark tests for T11 v1
extra-tools. End-to-end fake-subprocess pipeline, statistics output surfaces,
and startup-overhead benchmark.

Reason strings LOCKED per DESIGN-8 D6 — production code is source-of-truth.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

import python_setup_lint.runner.output as _output_module
from python_setup_lint.runner import RunnerConfig, ViolationCount, run_lint
from python_setup_lint.runner.extra_tools import _reset_extra_tools_cache
from python_setup_lint.runner.output import _aggregate_statistics
from python_setup_lint.testing import fake_run_cmd_factory, make_lint_result
from tests.runner._factories import write_pyproject
from tests.runner._factories_extras import (
    DOWNSTREAM_CASES,
    EXTRA_OBSERV_BLOCK,
    EXTRA_OBSERV_NAME,
    EXTRA_OBSERV_STDOUT,
)

# ── DOWNSTREAM-INTEGRATION ───────────────────────────────────────
# End-to-end fake-subprocess pipeline for extras (NO real subprocess).
# Covers loader → validator → registration → strategy dispatch → fake
# subprocess → parse → aggregate. ``--statistics --format json`` output
# observed via capsys (per-tool banners suppressed under statistics=True).


class TestRunLintExtraDownstreamIntegration:
    """End-to-end fake-subprocess integration of the extras pipeline."""

    @pytest.mark.parametrize(("block", "extra_name", "extra_cmd", "extra_stdout", "expected_counts"), DOWNSTREAM_CASES,)
    def test_extra_downstream_pipeline(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        block: str,
        extra_name: str,
        extra_cmd: list[str],
        extra_stdout: str,
        expected_counts: list[tuple[str, str, int]],
    ) -> None:
        """(a) extra dispatched with its spec command; (b) JSON output has expected triples;
        (c) direct re-aggregation reproduces the same counts/skip path."""
        write_pyproject(
            tmp_path,
            f"[tool.python-setup-lint]\n[[tool.python-setup-lint.extra-tools]]\n{block}",
        )
        fake = fake_run_cmd_factory(
            {extra_name: make_lint_result(tool_name=extra_name, stdout=extra_stdout)}
        )
        monkeypatch.setattr(_output_module, "_run_cmd", fake)

        rc = run_lint(
            config=RunnerConfig(cwd=tmp_path),
            statistics=True,
            statistics_format="json",
        )
        assert isinstance(rc, int), f"run_lint must return int; got {type(rc)}"

        # (a) extra's command reached the fake subprocess verbatim.
        extra_call = next(c for c in fake.calls if c.label == extra_name)
        assert extra_call.cmd == extra_cmd

        # (b) JSON output is the entire stdout under statistics=True.
        data = json.loads(capsys.readouterr().out.strip())
        by_key = {(e["tool"], e["rule"]): e["count"] for e in data}
        if expected_counts:
            for tool, rule, count in expected_counts:
                assert by_key.get((tool, rule)) == count, (
                    f"{tool}/{rule} → got {by_key.get((tool, rule))}. Full: {data}"
                )
        else:  # parse_strategy="none" → the extra's tool name must NOT appear
            leaked = [e for e in data if e.get("tool") == extra_name]
            assert leaked == [], (
                f"parse_strategy=none extra must not contribute rows: {leaked}. Full: {data}"
            )

        # (c) Direct re-aggregation reproduces the expected counts/skip.
        direct = _aggregate_statistics(
            [make_lint_result(tool_name=extra_name, stdout=extra_stdout)]
        )
        if expected_counts:
            for tool, rule, count in expected_counts:
                assert ViolationCount(tool, rule, count) in direct, (
                    f"_aggregate_statistics must emit {tool}/{rule}×{count}; got {direct}"
                )
        else:
            assert all(v.tool != extra_name for v in direct)


# ── PERF-BENCHMARK ─────────────────────────────────────────────────


def _time_run_lint(cwd: Path, *, n: int = 50, clear_cache_each: bool = False) -> float:
    """Run ``run_lint`` *n* times from *cwd* and return the per-iter wall-time."""
    total = 0.0
    for _ in range(n):
        if clear_cache_each:
            _reset_extra_tools_cache()
        start = time.perf_counter()
        run_lint(config=RunnerConfig(cwd=cwd))
        total += time.perf_counter() - start
    return total / n


@pytest.mark.slow
def test_run_lint_with_extras_startup_overhead_within_10_percent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Warm (memoised) t(N=10)/t(N=0) < 1.10 — extras caching stays O(1)."""
    no_extras_dir = tmp_path / "no_extras"
    extras_dir = tmp_path / "extras"
    no_extras_dir.mkdir()
    extras_dir.mkdir()

    (no_extras_dir / "pyproject.toml").write_text("[tool.python-setup-lint]\n")
    lines = ["[tool.python-setup-lint]"]
    for i in range(10):
        lines.append("[[tool.python-setup-lint.extra-tools]]")
        lines.append(f'name = "extra{i}"')
        lines.append(f'command = ["extra{i}"]')
        lines.append('parse_strategy = "none"')
    (extras_dir / "pyproject.toml").write_text("\n".join(lines) + "\n")

    monkeypatch.setattr(_output_module, "_run_cmd", fake_run_cmd_factory({}))

    t_0_cold = _time_run_lint(no_extras_dir, clear_cache_each=True)
    t_10_cold = _time_run_lint(extras_dir, clear_cache_each=True)
    _reset_extra_tools_cache()
    run_lint(config=RunnerConfig(cwd=no_extras_dir))
    t_0_warm = _time_run_lint(no_extras_dir)
    _reset_extra_tools_cache()
    run_lint(config=RunnerConfig(cwd=extras_dir))
    t_10_warm = _time_run_lint(extras_dir)

    warm_ratio = t_10_warm / t_0_warm
    print(
        f"\n[bench] cold t_0={t_0_cold:.6f}s t_10={t_10_cold:.6f}s ratio={t_10_cold / t_0_cold:.4f} | "
        f"warm t_0={t_0_warm:.6f}s t_10={t_10_warm:.6f}s ratio={warm_ratio:.4f}"
    )
    assert warm_ratio < 1.10, (
        f"warm t(N=10)/t(N=0) = {warm_ratio:.4f} >= 1.10 — memoised extras path is non-linear "
        f"(t_0_warm={t_0_warm:.6f}s, t_10_warm={t_10_warm:.6f}s)"
    )


# ── OBSERVABILITY ─────────────────────────────────────────────────


class TestExtraStatisticsObservability:
    """Stats output surfaces for extras — JSON + table format + ``none`` skip."""

    @staticmethod
    def _install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Write the ``regextool`` extra pyproject + monkeypatch fake ``_run_cmd``."""
        write_pyproject(
            tmp_path,
            f"[tool.python-setup-lint]\n[[tool.python-setup-lint.extra-tools]]\n{EXTRA_OBSERV_BLOCK}",
        )
        fake = fake_run_cmd_factory(
            {
                EXTRA_OBSERV_NAME: make_lint_result(
                    tool_name=EXTRA_OBSERV_NAME,
                    exit_code=0,
                    stdout=EXTRA_OBSERV_STDOUT,
                ),
            }
        )
        monkeypatch.setattr(_output_module, "_run_cmd", fake)

    @pytest.mark.parametrize("fmt", ["json", "table"])
    def test_extra_rule_counts_surface_in_statistics_output(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        fmt: str,
    ) -> None:
        """JSON + table output both surface the extra's ``{tool, rule, count}`` triples."""
        self._install(tmp_path, monkeypatch)
        rc = run_lint(
            config=RunnerConfig(cwd=tmp_path),
            statistics=True,
            statistics_format=fmt,
        )
        assert isinstance(rc, int)
        out = capsys.readouterr().out.strip()
        if fmt == "json":
            by_key = {(e["tool"], e["rule"]): e["count"] for e in json.loads(out)}
            assert by_key[("regextool", "RC1")] == 2, (
                f"RC1 wrong: {by_key}. Full: {out}"
            )
            assert by_key.get(("regextool", "RC2")) == 1, (
                f"RC2 wrong: {by_key}. Full: {out}"
            )
        else:
            assert "VIOLATION STATISTICS" in out
            for token in ("regextool", "RC1", "RC2", "1", "2"):
                assert token in out, f"expected {token!r} in table output\n{out}"


# ``parse_strategy="none"`` observability skip is exercised by
# ``test_extra_downstream_pipeline[parse_strategy_none_skips_aggregate]``.
