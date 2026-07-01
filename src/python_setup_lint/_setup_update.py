# Extracted from setup.py to keep this module under 500 lines.
from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def _check_config_drift(project_dir: Path, /) -> list[str]:
    from .setup import (
        _BUNDLED_CONFIGS,
        _STATE_FILE,
        _compute_checksums,
        _get_package_dir,
    )

    state_path = project_dir / _STATE_FILE
    if not state_path.exists():
        print("  [config] No .python-setup-state.json — skipping drift check")
        return []

    try:
        saved = json.loads(state_path.read_text(encoding="utf-8"))
        saved_checksums: dict[str, str] = saved.get("config_checksums", {})
    except (json.JSONDecodeError, KeyError):  # pylint: disable=W9740  # best-effort state file parse fallback; logging would noise unavoidable parse/IO degrade
        print("  [config] .python-setup-state.json unreadable — skipping drift check")
        return []

    pkg_dir = _get_package_dir()
    config_dir = pkg_dir / "config"
    current = _compute_checksums(config_dir, _BUNDLED_CONFIGS)

    drifted: list[str] = []
    for fname in sorted(set(saved_checksums) | set(current)):
        old = saved_checksums.get(fname, "(missing)")
        new = current.get(fname, "(missing)")
        if old != new:
            drifted.append(f"{fname}: saved={old[:8]}… current={new[:8]}…")

    if drifted:
        print("  [config] Config drift detected:")
        for d in drifted:
            print(f"    \u2022 {d}")
    else:
        print("  [config] All config checksums match — no drift")

    return drifted


def _run_update_steps(project_dir: Path) -> list[str]:
    from .setup import _run_uv

    errors: list[str] = []

    # Step 1: uv sync
    rc, stdout, stderr = _run_uv(["sync"], cwd=project_dir)
    if rc != 0:
        errors.append(f"uv sync failed: {stderr.strip()}")
    else:
        print("  [sync] uv sync completed")

    # Step 2: uv add python-setup --refresh-package python-setup
    rc, stdout, stderr = _run_uv(
        ["add", "python-setup", "--refresh-package", "python-setup"],
        cwd=project_dir,
    )
    if rc != 0:
        errors.append(f"uv add --refresh-package failed: {stderr.strip()}")
    else:
        print("  [refresh] python-setup version pins refreshed")

    return errors


def update(  # pylint: disable=missing-beartype,docstring-in-impl  # CLI entry point, signature fixed by setup API; @beartype cannot resolve Path forward ref
    project_dir: Path,
) -> int:
    """Update an existing python-setup installation, checking for config drift.

    Returns:
        Exit code: 0 on success, 1 on error.
    """
    print(f"python-setup update \u2192 {project_dir}")

    errors = _run_update_steps(project_dir)

    _check_config_drift(project_dir)

    if errors:
        print()
        print("Errors:")
        for e in errors:
            print(f"  \u2717 {e}")
        return 1

    print()
    print("Update complete.")
    return 0
