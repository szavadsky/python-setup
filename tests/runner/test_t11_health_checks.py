"""Unit tests for T11 — consumer-agnostic health checks in ``testing``.

Coverage mapping (envelope ``T11.envelope.md``):

* **surface-unit** — ``test_checked_main`` assembles the typeguard-pytest
  argv (``-p typeguard -q tests/unit`` + passthrough) and exits via
  ``sys.exit(pytest.main(...))``; ``-p typeguard`` is used (NOT
  ``--typeguard-packages=<name>``) so no package name is hardcoded.
* **private-complex-unit** — ``assert_precommit_config_valid`` and
  ``assert_precommit_hooks_shape`` against fabricated temp configs:
  happy-path, missing-file, malformed-YAML, wrong-baseline-filename,
  ruff-hook-without-fix, fast-hook-off-stage.
* **downstream-integration** — against the real ``configured_project``
  fixture (which runs ``install`` to materialise the shared
  ``.pre-commit-config.yaml`` template): the generic validators accept the
  template-generated config, and ``pre-commit validate-config`` is
  actually invoked (real subprocess).
* **observability** — ``assert_precommit_config_valid`` assertion messages
  embed the failing returncode + captured stdout/stderr so a CI failure
  reconstructs what ``pre-commit validate-config`` reported.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

from python_setup_lint.testing import (
    assert_precommit_config_valid,
    assert_precommit_hooks_shape,
)
from python_setup_lint.testing import test_checked_main as _test_checked_main

# ── Helpers ───────────────────────────────────────────────────────


def _write_precommit(repo_root: Path, *, repos_yaml: str) -> Path:
    """Write a fabricated ``.pre-commit-config.yaml`` to *repo_root*."""
    path = repo_root / ".pre-commit-config.yaml"
    path.write_text(textwrap.dedent(repos_yaml), encoding="utf-8")
    return path


_VALID_CONFIG = """\
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.10
    hooks:
      - id: ruff-format
        stages: [pre-commit]
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
        stages: [pre-commit]
  - repo: local
    hooks:
      - id: lint
        name: lint (full pipeline, baseline-gated)
        entry: python-setup lint --fix --baseline lint.baseline
        language: system
        pass_filenames: false
        args: []
"""


# ── test_checked_main — surface-unit ──────────────────────────────


class TestTestCheckedMainArgv:
    """``test_checked_main`` builds the consumer-agnostic typeguard argv."""

    def test_assembles_typeguard_plugin_argv(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def _fake_pytest_main(args: list[str]) -> int:
            captured["args"] = list(args)
            return 0

        # ``pytest`` is imported lazily inside ``test_checked_main``; patch the
        # real pytest module's ``main`` so the lazy ``import pytest`` sees the stub.
        import pytest as _real_pytest

        monkeypatch.setattr(_real_pytest, "main", _fake_pytest_main)
        monkeypatch.setattr("sys.argv", ["test-checked"])

        with pytest.raises(SystemExit) as exc:
            _test_checked_main()
        assert exc.value.code == 0
        assert captured["args"][:4] == ["-p", "typeguard", "-q", "tests/unit"]

    def test_passthrough_extra_argv(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}

        def _fake_pytest_main(args: list[str]) -> int:
            captured["args"] = list(args)
            return 0

        import pytest as _real_pytest

        monkeypatch.setattr(_real_pytest, "main", _fake_pytest_main)
        monkeypatch.setattr("sys.argv", ["test-checked", "tests/integration", "-x"])

        with pytest.raises(SystemExit):
            _test_checked_main()
        assert captured["args"][-2:] == ["tests/integration", "-x"]

    def test_no_hardcoded_package_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The built argv must not embed any consumer-specific package name.

        Asserts at runtime on the args passed to ``pytest.main`` (not on the
        source/docstring, which references the avoided flag in prose).
        """
        captured: dict[str, Any] = {}

        def _fake_pytest_main(args: list[str]) -> int:
            captured["args"] = list(args)
            return 0

        import pytest as _real_pytest

        monkeypatch.setattr(_real_pytest, "main", _fake_pytest_main)
        monkeypatch.setattr("sys.argv", ["test-checked"])

        with pytest.raises(SystemExit):
            _test_checked_main()
        joined = " ".join(captured["args"])
        assert "--typeguard-packages" not in joined
        assert "consultant" not in joined.lower()


# ── assert_precommit_config_valid — private-complex-unit ─────────


class TestAssertPrecommitConfigValid:
    """``assert_precommit_config_valid`` validates YAML + shape + validate-config."""

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(AssertionError, match="Missing pre-commit config"):
            assert_precommit_config_valid(tmp_path)

    def test_malformed_non_mapping_raises(self, tmp_path: Path) -> None:
        _write_precommit(tmp_path, repos_yaml="- just\n- a\n- list\n")
        with pytest.raises(AssertionError, match="YAML mapping"):
            assert_precommit_config_valid(tmp_path)

    def test_missing_repos_key_raises(self, tmp_path: Path) -> None:
        _write_precommit(tmp_path, repos_yaml="foo: bar\n")
        with pytest.raises(AssertionError, match="'repos' key"):
            assert_precommit_config_valid(tmp_path)

    def test_valid_yaml_shape_loaded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The YAML/shape check passes even before ``validate-config``; we
        # exercise the loader path by stubbing pre-commit to exit 0.
        _write_precommit(tmp_path, repos_yaml=_VALID_CONFIG)

        class _OK:
            returncode = 0
            stdout = ""
            stderr = ""

        def _fake_run(cmd: list[str], **_kwargs: object) -> _OK:
            assert cmd[:2] == ["pre-commit", "validate-config"]
            return _OK()

        monkeypatch.setattr("python_setup_lint.testing.subprocess.run", _fake_run)
        # Should not raise.
        assert_precommit_config_valid(tmp_path)

    def test_validate_config_failure_message_is_observable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Observability: a ``validate-config`` failure surfaces rc + captured output.

        A CI failure must reconstruct what ``pre-commit validate-config`` reported,
        so the assertion embeds the returncode and stdout/stderr (no sensitive
        leakage — these are local tool diagnostics).
        """
        _write_precommit(tmp_path, repos_yaml=_VALID_CONFIG)

        class _Fail:
            returncode = 2
            stdout = "stdout-diagnostic"
            stderr = "stderr-diagnostic"

        def _fake_run(cmd: list[str], **_kwargs: object) -> _Fail:
            return _Fail()

        monkeypatch.setattr("python_setup_lint.testing.subprocess.run", _fake_run)
        with pytest.raises(AssertionError) as exc:
            assert_precommit_config_valid(tmp_path)
        msg = str(exc.value)
        assert "exit 2" in msg
        assert "stdout-diagnostic" in msg
        assert "stderr-diagnostic" in msg


# ── assert_precommit_hooks_shape — private-complex-unit ───────────


class TestAssertPrecommitHooksShape:
    """``assert_precommit_hooks_shape`` enforces the shared-template contract."""

    def test_valid_config_passes(self, tmp_path: Path) -> None:
        _write_precommit(tmp_path, repos_yaml=_VALID_CONFIG)
        # Should not raise.
        assert_precommit_hooks_shape(tmp_path)

    def test_missing_lint_hook_raises(self, tmp_path: Path) -> None:
        _write_precommit(
            tmp_path,
            repos_yaml="""\
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.10
    hooks:
      - id: ruff-format
        stages: [pre-commit]
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
        stages: [pre-commit]
""",
        )
        with pytest.raises(AssertionError, match="'lint' local hook"):
            assert_precommit_hooks_shape(tmp_path)

    def test_lint_not_system_language_raises(self, tmp_path: Path) -> None:
        _write_precommit(
            tmp_path,
            repos_yaml="""\
repos:
  - repo: local
    hooks:
      - id: lint
        name: lint
        entry: python-setup lint --fix --baseline lint.baseline
        language: python
        pass_filenames: false
""",
        )
        with pytest.raises(AssertionError, match="language: system"):
            assert_precommit_hooks_shape(tmp_path)


    def test_wrong_baseline_filename_raises(self, tmp_path: Path) -> None:
        _write_precommit(
            tmp_path,
            repos_yaml="""\
repos:
  - repo: local
    hooks:
      - id: lint
        name: lint
        entry: python-setup lint --fix --baseline .lint.baseline
        language: system
        pass_filenames: false
""",
        )
        # Default baseline_filename='lint.baseline' must reject the
        # '.lint.baseline' drift, surfacing the filename in the message.
        with pytest.raises(AssertionError, match=r"--baseline lint\.baseline"):
            assert_precommit_hooks_shape(tmp_path)

    def test_explicit_baseline_filename_matches(self, tmp_path: Path) -> None:
        _write_precommit(
            tmp_path,
            repos_yaml="""\
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.10
    hooks:
      - id: ruff-format
        stages: [pre-commit]
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
        stages: [pre-commit]
  - repo: local
    hooks:
      - id: lint
        name: lint
        entry: python-setup lint --fix --baseline .lint.baseline
        language: system
        pass_filenames: false
""",
        )
        # Consumer opts into the legacy name; should not raise.
        assert_precommit_hooks_shape(tmp_path, baseline_filename=".lint.baseline")

    def test_ruff_hook_without_fix_raises(self, tmp_path: Path) -> None:
        _write_precommit(
            tmp_path,
            repos_yaml="""\
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.10
    hooks:
      - id: ruff
        args: [--exit-non-zero-on-fix]
        stages: [pre-commit]
  - repo: local
    hooks:
      - id: lint
        name: lint
        entry: python-setup lint --fix --baseline lint.baseline
        language: system
        pass_filenames: false
""",
        )
        with pytest.raises(AssertionError, match="--fix"):
            assert_precommit_hooks_shape(tmp_path)

    def test_fast_hook_off_pre_commit_stage_raises(self, tmp_path: Path) -> None:
        _write_precommit(
            tmp_path,
            repos_yaml="""\
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.10
    hooks:
      - id: ruff-format
        stages: [pre-push]
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
        stages: [pre-commit]
  - repo: local
    hooks:
      - id: lint
        name: lint
        entry: python-setup lint --fix --baseline lint.baseline
        language: system
        pass_filenames: false
""",
        )
        with pytest.raises(AssertionError, match="pre-commit stage"):
            assert_precommit_hooks_shape(tmp_path)

    def test_empty_stages_accepted_for_fast_hook(self, tmp_path: Path) -> None:
        # A fast hook with no explicit ``stages`` (runs on the default
        # pre-commit stage) must be accepted, matching the G0 contract.
        _write_precommit(
            tmp_path,
            repos_yaml="""\
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.10
    hooks:
      - id: ruff-format
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
  - repo: local
    hooks:
      - id: lint
        name: lint
        entry: python-setup lint --fix --baseline lint.baseline
        language: system
        pass_filenames: false
""",
        )
        assert_precommit_hooks_shape(tmp_path)


# ── Downstream integration against the installed template ─────────


@pytest.mark.slow
class TestHealthChecksAgainstInstalledTemplate:
    """Generic validators accept the template-generated config (real pre-commit).

    Downstream-integration: ``configured_project`` runs ``install`` to
    materialise the shared ``.pre-commit-config.yaml`` template, then the
    generic validators run against it — ``assert_precommit_config_valid``
    invokes the real ``pre-commit validate-config`` subprocess.
    """

    def test_validators_accept_installed_config(self, configured_project: Path) -> None:
        assert (configured_project / ".pre-commit-config.yaml").exists()
        # Should not raise: real validate-config subprocess + shape checks.
        assert_precommit_config_valid(configured_project)
        assert_precommit_hooks_shape(configured_project)
