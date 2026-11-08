"""Single-source helpers for building and inspecting test projects.

Shared by the integration pipeline tests, the autofix conflict tests, and the
self-lint guards.  This module may import stdlib, ``python_setup_lint`` and
``tests._golden`` only — never ``tests.conftest`` or ``tests.integration`` — to
keep the test import graph acyclic.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from python_setup_lint.runner import RunnerConfig
from python_setup_lint.runner._config import _SHIPPED_CONFIG_FILES
from python_setup_lint.setup import install
from tests._golden import Finding, collect_findings

SAMPLE_PROJECT = Path("tests/data/minimal_sample_project")


def copy_sample_project(dest_parent: Path) -> Path:
    """Copy the minimal sample project to ``dest_parent/project`` and return it."""
    dest_parent.mkdir(parents=True, exist_ok=True)
    dest = dest_parent / "project"
    shutil.copytree(SAMPLE_PROJECT, dest)
    return dest


def git_init_and_stage(project: Path) -> None:
    """Initialise a git repo in *project* and stage every file (detect-secrets needs it)."""
    subprocess.run(["git", "init"], cwd=project, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test"],
        cwd=project,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=project,
        capture_output=True,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=project, capture_output=True, check=True)


def shipped_config_paths() -> dict[str, Path]:
    """Build config_paths dict from the python-setup project root config/ dir."""
    config_root = Path("config")
    paths: dict[str, Path] = {}
    for tool_label, filename in _SHIPPED_CONFIG_FILES.items():
        candidate = config_root / filename
        if candidate.is_file():
            paths[tool_label] = candidate.resolve()
    return paths


def make_runner_config(project: Path) -> RunnerConfig:
    """Build a ``RunnerConfig`` for the sample project with shipped config paths.

    The shipped rumdl config excludes ``tests/data/``, which is where the
    sample project lives when copied to a temp dir.  Create a project-local
    override that removes that exclusion so rumdl checks the sample's
    AGENTS.md (which has planted MD022/MD009/MD012/MD071 violations).  The
    override is skipped when the shipped rumdl config is missing.
    """
    config_paths = shipped_config_paths()
    shipped_rumdl = Path("config/rumdl.toml")
    if shipped_rumdl.is_file():
        local_rumdl = project / "rumdl.toml"
        content = shipped_rumdl.read_text()
        # Remove the ``tests/data`` entry from the exclude list.
        content = content.replace('"tests/data", ', "")
        local_rumdl.write_text(content)
        config_paths["rumdl check"] = local_rumdl
    return RunnerConfig(
        cwd=project,
        package_name="minimal_sample",
        config_paths=config_paths,
    )


def collect_sample_findings(dest_parent: Path) -> list[Finding]:
    """Copy a fresh sample project under *dest_parent* and collect its golden findings."""
    project = copy_sample_project(dest_parent)
    git_init_and_stage(project)
    return collect_findings(project, make_runner_config(project))


def git_init_bare(cwd: Path) -> None:
    """Initialise a git repo in *cwd* without staging anything."""
    subprocess.run(["git", "init", "-q"], cwd=cwd, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=cwd,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def write_project_file(cwd: Path, rel: str, content: str) -> Path:
    """Write *content* to ``cwd/rel``, creating parent dirs, and return the path."""
    p = cwd / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def stage_file(cwd: Path, rel: str) -> None:
    """Stage a single file in *cwd*'s git index."""
    subprocess.run(["git", "add", rel], cwd=cwd, check=True, capture_output=True)


def commit_all(cwd: Path, msg: str = "init") -> None:
    """Stage everything in *cwd* and commit it with *msg*."""
    subprocess.run(["git", "add", "."], cwd=cwd, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", msg],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


_CONSUMER_PYPROJECT = textwrap.dedent("""\
    [project]
    name = "consumer"
    version = "0.1.0"
    requires-python = ">=3.14"
    [dependency-groups]
    dev = ["ruff>=0.5", "python-setup"]
""")

_SECRETS_BASELINE = '{"version":"1.0","plugins_used":[],"filters_used":[],"results":{},"generated_at":"2025-01-01T00:00:00Z"}\n'


def make_clean_consumer_project(project: Path) -> Path:
    """Create a minimal clean consumer project with a git repo at *project*."""
    project.mkdir()
    write_project_file(project, "src/consumer/__init__.py", "# c\n")
    write_project_file(project, "tests/__init__.py", "# t\n")
    write_project_file(project, "pyproject.toml", _CONSUMER_PYPROJECT)
    write_project_file(project, "AGENTS.md", "# C\n")
    git_init_and_stage(project)
    write_project_file(project, ".secrets.baseline", _SECRETS_BASELINE)
    write_project_file(project, "tach.toml", '[[modules]]\npath = "src/consumer"\ndepends_on = []\n')
    return project


def build_pylint_overlay_config(project: Path, disable_rule: str) -> Path:
    """Create a project-local ``.pylintrc`` disabling *disable_rule*; return its path.

    The rule is added to the shipped config's ``disable=`` list and removed
    from its ``enable=`` whitelist so the disable actually takes effect.
    """
    shipped_pylintrc = Path("config") / ".pylintrc"
    assert shipped_pylintrc.is_file(), "Shipped pylintrc not found"
    pylintrc_content = shipped_pylintrc.read_text()

    pylintrc_content = pylintrc_content.replace("disable=", f"disable={disable_rule},")
    enable_match = re.search(r"^enable=(.+)", pylintrc_content, re.MULTILINE)
    assert enable_match, "Could not find enable= line in pylintrc"
    enable_items = enable_match.group(1).split(",")
    new_enable = "enable=" + ",".join(item for item in enable_items if item != disable_rule)
    pylintrc_content = pylintrc_content[: enable_match.start()] + new_enable + pylintrc_content[enable_match.end() :]

    local_pylintrc = project / ".pylintrc"
    local_pylintrc.write_text(pylintrc_content)
    return local_pylintrc


def ensure_precommit_or_skip() -> None:
    """Skip the current test when the ``pre-commit`` binary is unavailable."""
    try:
        subprocess.run(["pre-commit", "--version"], capture_output=True, check=True)
    except FileNotFoundError, subprocess.CalledProcessError:
        logging.warning("pre-commit not available, skipping test")
        pytest.skip("pre-commit not available")


def install_twice_assert_idempotent(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run ``install`` twice with ``uv`` mocked; assert both runs succeed."""

    def fake_run_uv(args: list[str], *, cwd: str | Path) -> tuple[int, str, str]:
        return 0, "", ""

    monkeypatch.setattr("python_setup_lint.setup._run_uv", fake_run_uv)
    rc1 = install(project)
    assert rc1 == 0, f"First install failed with exit code {rc1}"
    rc2 = install(project)
    assert rc2 == 0, f"Second install failed with exit code {rc2} (should be idempotent)"
