"""Idempotent setup CLI for python-setup consumers.

Provides ``python-setup install`` and ``python-setup update`` commands.
Every install step checks current state before writing — running twice
is a no-op.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


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
