"""Stub for :mod:`python_setup_lint._setup_update`.

Update workflow: config drift check + uv sync/refresh.
"""

from pathlib import Path

def _check_config_drift(project_dir: Path, /) -> list[str]:
    """Compare saved config checksums against current bundled configs.

    Returns:
        List of drift descriptions (empty if none).
    """


def _run_update_steps(project_dir: Path) -> list[str]:
    """Run uv sync and uv add --refresh-package python-setup.

    Returns:
        List of error messages (empty on success).
    """


def update(project_dir: Path) -> int:
    """Update an existing python-setup installation.

    Returns:
        Exit code: 0 on success, 1 on error.
    """
