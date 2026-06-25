"""Idempotent setup CLI for python-setup consumers.

Provides ``python-setup install`` and ``python-setup update`` commands.
Every install step checks current state before writing — running twice
is a no-op.
"""

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

# ── Constants ───────────────────────────────────────────────────────

_PACKAGE_NAME: str
_GIT_URL: str
_STATE_FILE: str
_BUNDLED_CONFIGS: tuple[str, ...]

# ── Data structures ─────────────────────────────────────────────────

@dataclass
class SetupState:
    """Tracks what was done for idempotency reporting."""

    dep_added: bool
    dep_skipped: bool
    pylint_plugins_added: bool
    pylint_plugins_skipped: bool
    precommit_written: bool
    precommit_skipped: bool
    coding_rules_copied: bool
    coding_rules_skipped: bool
    agents_appended: bool
    agents_skipped: bool
    errors: list[str]

    @property
    def all_ok(self) -> bool: ...

# ── Helpers ─────────────────────────────────────────────────────────

def _compute_checksums(config_dir: Path, files: Sequence[str]) -> dict[str, str]: ...
def _discover_checkers() -> list[str]: ...
def _read_pyproject_toml(project_dir: Path) -> dict[str, object] | None: ...
def _write_pyproject_toml(project_dir: Path, data: dict[str, object]) -> None: ...
def _get_pylint_load_plugins(data: dict[str, object]) -> list[str]: ...
def _set_pylint_load_plugins(data: dict[str, object], plugins: list[str]) -> None: ...
def _get_dev_deps(data: dict[str, object]) -> list[str]: ...
def _has_python_setup_dep(dev_deps: list[str]) -> bool: ...
def _run_uv(args: list[str], *, cwd: Path) -> tuple[int, str, str]: ...
def _get_package_dir() -> Path: ...
def _step_add_dep(
    state: SetupState, project_dir: Path, *, dev_path: str | None = None
) -> None: ...
def _step_pylint_plugins(state: SetupState, project_dir: Path) -> None: ...
def _step_coding_rules(state: SetupState, project_dir: Path) -> None: ...
def _save_state(project_dir: Path) -> None: ...
def _build_parser() -> argparse.ArgumentParser: ...

# ── Public API ──────────────────────────────────────────────────────

def install(
    project_dir: Path,
    *,
    dev_path: str | None = None,
) -> int:
    """Idempotently install python-setup tooling into *project_dir*.

    Returns exit code (0 = success, 1 = errors).
    """

def update(project_dir: Path) -> int:
    """Update python-setup in *project_dir* and report config drift.

    Returns exit code (0 = success, 1 = errors).
    """

def main(argv: list[str] | None = None) -> int:
    """CLI entry point for ``python-setup install`` / ``python-setup update``."""
