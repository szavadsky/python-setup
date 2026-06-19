"""Pre-commit hook template and AGENTS.md snippet for python-setup install.

Extracted from setup.py for module-size compliance (G5 §2).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .setup import SetupState

_AGENTS_SENTINEL: str
_AGENTS_SENTINEL_END: str
_PRECOMMIT_TEMPLATE: str
_AGENTS_SNIPPET: str


def _atomic_write(path: Path, content: str) -> None: ...


def _step_precommit(state: SetupState, project_dir: Path) -> None: ...


def _step_agents_snippet(state: SetupState, project_dir: Path) -> None: ...
