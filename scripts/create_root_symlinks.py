"""Create root-level relative symlinks for standalone-tool parity.

python-setup itself has configs only in ``config/``, so tools like
``uv run rumdl fmt`` / ``uv run pylint`` / ``uv run ruff`` cannot
auto-discover them (they search CWD + parents, not ``config/``).

This script creates root-level relative symlinks so that every tool
finds its config at the project root, mirroring what ``python-setup install``
does for consumer projects.

Usage::

    uv run python scripts/create_root_symlinks.py

Or from the project root::

    python scripts/create_root_symlinks.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Config files to symlink (must exist under config/)
_CONFIG_FILES: tuple[str, ...] = (
    "ruff.toml",
    ".pylintrc",
    "mypy.ini",
    "pyrightconfig.json",
    "rumdl.toml",
    "ty.toml",
    ".yamllint",
    ".pylintrc-pyi",
    ".pylintrc-tests",
)


def main() -> int:
    project_dir = Path.cwd().resolve()
    config_dir = project_dir / "config"

    if not config_dir.is_dir():
        print(f"Error: config/ directory not found at {config_dir}", file=sys.stderr)
        return 1

    created = 0
    skipped = 0
    errors: list[str] = []

    for fname in _CONFIG_FILES:
        source = config_dir / fname
        target = project_dir / fname

        if not source.exists():
            errors.append(f"Source config not found: {source}")
            continue

        # Compute relative symlink target: config/ruff.toml
        rel_target = os.path.relpath(str(source), start=str(target.parent))

        if target.is_symlink():
            existing = os.readlink(target)
            if existing == rel_target:
                skipped += 1
                continue
            # Mismatched symlink — remove and recreate
            target.unlink()
        elif target.exists():
            # Regular file exists — check content match
            try:
                if target.read_bytes() == source.read_bytes():
                    skipped += 1
                    continue
            except OSError:
                pass
            # Content differs or unreadable — remove and recreate
            target.unlink()

        try:
            os.symlink(rel_target, str(target))
            created += 1
            print(f"  ✓ {fname} → {rel_target}")
        except OSError as exc:
            errors.append(f"Failed to create symlink for {fname}: {exc}")

    print()
    print(f"Created {created} symlinks, skipped {skipped}")
    if errors:
        for err in errors:
            print(f"  ✗ {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
