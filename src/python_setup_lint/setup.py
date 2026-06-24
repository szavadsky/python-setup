"""Idempotent setup CLI for python-setup consumers.

Provides ``python-setup install`` and ``python-setup update`` commands.
Every install step checks current state before writing — running twice
is a no-op.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pkgutil
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ._setup_precommit import (
    _atomic_write,
    _step_agents_snippet,
    _step_precommit,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

# ── Constants ───────────────────────────────────────────────────────

_PACKAGE_NAME = "python-setup"
_GIT_URL = "git+https://github.com/szavadsky/python-setup"
_STATE_FILE = ".python-setup-state.json"

# Bundled config files to copy / checksum-track (relative to config/ dir)
_BUNDLED_CONFIGS: tuple[str, ...] = (
    "ruff.toml",
    ".pylintrc",
    "mypy.ini",
    "pyrightconfig.json",
    "rumdl.toml",
    "ty.toml",
)


# ── Data structures ─────────────────────────────────────────────────

@dataclass
class SetupState:
    """Tracks what was done for idempotency reporting."""

    dep_added: bool = False
    dep_skipped: bool = False
    pylint_plugins_added: bool = False
    pylint_plugins_skipped: bool = False
    precommit_written: bool = False
    precommit_skipped: bool = False
    coding_rules_copied: bool = False
    coding_rules_skipped: bool = False
    agents_appended: bool = False
    agents_skipped: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return len(self.errors) == 0


# ── Helpers ─────────────────────────────────────────────────────────

def _compute_checksums(config_dir: Path, files: Sequence[str]) -> dict[str, str]:
    """Compute SHA-256 checksums for *files* relative to *config_dir*."""
    result: dict[str, str] = {}
    for fname in files:
        fpath = config_dir / fname
        if fpath.is_file():
            result[fname] = hashlib.sha256(fpath.read_bytes()).hexdigest()
    return result


def _discover_checkers() -> list[str]:
    """Introspect ``python_setup_lint.checkers`` for pylint plugin modules.

    Returns fully-qualified module names for modules that define a
    ``register`` function (pylint plugin contract).
    """
    import python_setup_lint.checkers as checkers_pkg

    result: list[str] = []
    prefix = checkers_pkg.__name__ + "."
    for m in pkgutil.iter_modules(checkers_pkg.__path__, prefix):
        # Filter: only modules with a register function
        try:
            mod = __import__(m.name, fromlist=["register"])
            if hasattr(mod, "register"):
                result.append(m.name)
        except ImportError as e:
            import warnings
            warnings.warn(
                f"Failed to import checker module {m.name}: {e}",
                ImportWarning,
                stacklevel=2,
            )
    return sorted(result)


def _read_pyproject_toml(project_dir: Path) -> dict[str, object] | None:
    """Read pyproject.toml from *project_dir*, returning parsed dict or None."""
    toml_path = project_dir / "pyproject.toml"
    if not toml_path.is_file():
        return None
    with open(toml_path, "rb") as f:
        return tomllib.load(f)


def _write_pyproject_toml(project_dir: Path, data: dict[str, object]) -> None:
    """Write *data* back to pyproject.toml using tomli-w."""
    import tomli_w

    toml_path = project_dir / "pyproject.toml"
    _atomic_write(toml_path, tomli_w.dumps(data))


def _get_pylint_load_plugins(data: dict[str, object]) -> list[str]:
    """Extract current ``[tool.pylint.main].load-plugins`` list from TOML data."""
    tool = data.get("tool", {})
    if not isinstance(tool, dict):
        return []
    pylint = tool.get("pylint", {})
    if not isinstance(pylint, dict):
        return []
    main = pylint.get("main", {})
    if not isinstance(main, dict):
        return []
    plugins = main.get("load-plugins", [])
    if isinstance(plugins, list):
        return [str(p) for p in plugins]
    return []


def _set_pylint_load_plugins(data: dict[str, object], plugins: list[str]) -> None:
    """Set ``[tool.pylint.main].load-plugins`` in TOML data, creating sections as needed."""
    tool = data.setdefault("tool", {})
    if not isinstance(tool, dict):
        return
    pylint = tool.setdefault("pylint", {})
    if not isinstance(pylint, dict):
        return
    main = pylint.setdefault("main", {})
    if not isinstance(main, dict):
        return
    main["load-plugins"] = plugins


def _get_dev_deps(data: dict[str, object]) -> list[str]:
    """Extract current ``[dependency-groups].dev`` list from TOML data."""
    dg = data.get("dependency-groups", {})
    if not isinstance(dg, dict):
        return []
    dev = dg.get("dev", [])
    if isinstance(dev, list):
        return [str(d) for d in dev]
    return []


def _has_python_setup_dep(dev_deps: list[str]) -> bool:
    """Check if python-setup is already in dev dependencies."""
    for dep in dev_deps:
        # PEP 508: package name is everything before first [ < > = ! ~ @
        # Strip extras [...], then version/URL specifiers
        name = dep.split("[")[0]
        for sep in (">=", "<=", "!=", "==", "~=", "@", ">"):
            if sep in name:
                name = name.split(sep)[0]
        name = name.strip()
        if name == _PACKAGE_NAME:
            return True
    return False


def _run_uv(args: list[str], *, cwd: Path) -> tuple[int, str, str]:
    """Run a uv command, returning (exit_code, stdout, stderr)."""
    try:
        proc = subprocess.run(
            ["uv"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError:
        return 1, "", "uv not found — is it installed?"
    except subprocess.TimeoutExpired:
        return 1, "", "uv command timed out"


def _get_package_dir() -> Path:
    """Return the directory containing config/ and CodingRules.md.

    With ``force-include`` these ship inside the package directory.
    For editable installs they live at the project root.
    """
    import python_setup_lint

    pkg_dir = Path(python_setup_lint.__path__[0])
    if (pkg_dir / "config").is_dir():
        return pkg_dir
    return pkg_dir.parent.parent


# ── Install steps ────────────────────────────────────────────────────

def _step_add_dep(
    state: SetupState,
    project_dir: Path,
    *,
    dev_path: str | None = None,
) -> None:
    """Step 1: Add python-setup git dependency to dev group."""
    data = _read_pyproject_toml(project_dir)
    if data is None:
        state.errors.append("pyproject.toml not found — not a Python project?")
        return

    dev_deps = _get_dev_deps(data)
    if _has_python_setup_dep(dev_deps):
        state.dep_skipped = True
        print("  [dependency] python-setup already in dev dependencies — skipping")
        return

    # Add the dependency — path is the package argument itself
    args = ["add", "--dev", dev_path] if dev_path else ["add", "--dev", f"python-setup @ {_GIT_URL}"]

    rc, stdout, stderr = _run_uv(args, cwd=project_dir)
    if rc != 0:
        state.errors.append(f"uv add python-setup failed: {stderr.strip()}")
        return

    state.dep_added = True
    print("  [dependency] Added python-setup to dev dependencies")


def _step_pylint_plugins(state: SetupState, project_dir: Path) -> None:
    """Step 2: Add pylint load-plugins entries for discovered checkers."""
    data = _read_pyproject_toml(project_dir)
    if data is None:
        state.errors.append("pyproject.toml not found — cannot add pylint plugins")
        return

    discovered = _discover_checkers()
    if not discovered:
        print("  [pylint] No checker plugins discovered — skipping")
        return

    existing = _get_pylint_load_plugins(data)
    missing = [p for p in discovered if p not in existing]

    if not missing:
        state.pylint_plugins_skipped = True
        print("  [pylint] All checker plugins already registered — skipping")
        return

    all_plugins = sorted(set(existing + discovered))
    _set_pylint_load_plugins(data, all_plugins)
    _write_pyproject_toml(project_dir, data)

    state.pylint_plugins_added = True
    print(f"  [pylint] Added load-plugins: {', '.join(missing)}")


def _step_coding_rules(state: SetupState, project_dir: Path) -> None:
    """Step 4: Copy CodingRules.md from python-setup's bundled copy."""
    target = project_dir / "CodingRules.md"
    if target.exists():
        state.coding_rules_skipped = True
        print("  [coding-rules] CodingRules.md already exists — skipping")
        return

    source = _get_package_dir() / "CodingRules.md"
    if not source.is_file():
        state.errors.append("Bundled CodingRules.md not found in python-setup package")
        return

    shutil.copy2(source, target)
    state.coding_rules_copied = True
    print("  [coding-rules] Copied CodingRules.md")


def _save_state(project_dir: Path) -> None:
    """Save install state to .python-setup-state.json for update drift detection."""
    pkg_dir = _get_package_dir()
    config_dir = pkg_dir / "config"
    checksums = _compute_checksums(config_dir, _BUNDLED_CONFIGS)

    state_data = {
        "version": 1,
        "config_checksums": checksums,
        "installed_at": None,  # Could add timestamp if needed
    }
    state_path = project_dir / _STATE_FILE
    _atomic_write(state_path, json.dumps(state_data, indent=2, sort_keys=True) + "\n")


# ── Install command ──────────────────────────────────────────────────

def install(
    project_dir: Path,
    *,
    dev_path: str | None = None,
) -> int:
    """Idempotently install python-setup tooling into *project_dir*.

    Returns exit code (0 = success, 1 = errors).
    """
    print(f"python-setup install → {project_dir}")
    state = SetupState()

    _step_add_dep(state, project_dir, dev_path=dev_path)
    _step_pylint_plugins(state, project_dir)
    _step_precommit(state, project_dir)
    _step_coding_rules(state, project_dir)
    _step_agents_snippet(state, project_dir)

    # Save state for update drift detection
    if state.all_ok:
        _save_state(project_dir)

    # Summary
    print()
    if state.errors:
        print("Errors:")
        for e in state.errors:
            print(f"  ✗ {e}")
        return 1

    actions = []
    if state.dep_added:
        actions.append("added python-setup dependency")
    if state.dep_skipped:
        actions.append("dependency already present")
    if state.pylint_plugins_added:
        actions.append("added pylint load-plugins")
    if state.pylint_plugins_skipped:
        actions.append("pylint plugins already configured")
    if state.precommit_written:
        actions.append("wrote .pre-commit-config.yaml")
    if state.precommit_skipped:
        actions.append("pre-commit config already exists")
    if state.coding_rules_copied:
        actions.append("copied CodingRules.md")
    if state.coding_rules_skipped:
        actions.append("CodingRules.md already exists")
    if state.agents_appended:
        actions.append("appended AGENTS.md snippet")
    if state.agents_skipped:
        actions.append("AGENTS.md snippet skipped")

    if not actions:
        print("Already fully configured — nothing to do.")
    else:
        print("Summary:")
        for a in actions:
            print(f"  ✓ {a}")

    return 0


# ── Update command ───────────────────────────────────────────────────

def update(project_dir: Path) -> int:
    """Update python-setup in *project_dir* and report config drift.

    Returns exit code (0 = success, 1 = errors).
    """
    print(f"python-setup update → {project_dir}")
    errors: list[str] = []

    # Step 1: uv sync
    rc, stdout, stderr = _run_uv(["sync"], cwd=project_dir)
    if rc != 0:
        errors.append(f"uv sync failed: {stderr.strip()}")
    else:
        print("  [sync] uv sync completed")

    # Step 2: uv add --refresh-package python-setup
    rc, stdout, stderr = _run_uv(
        ["add", "--refresh-package", "python-setup"],
        cwd=project_dir,
    )
    if rc != 0:
        errors.append(f"uv add --refresh-package failed: {stderr.strip()}")
    else:
        print("  [refresh] python-setup version pins refreshed")

    # Step 3: Compare config checksums
    state_path = project_dir / _STATE_FILE
    if not state_path.exists():
        print("  [config] No .python-setup-state.json — skipping drift check")
    else:
        try:
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            saved_checksums: dict[str, str] = saved.get("config_checksums", {})
        except (json.JSONDecodeError, KeyError):
            print("  [config] .python-setup-state.json unreadable — skipping drift check")
        else:
            pkg_dir = _get_package_dir()
            config_dir = pkg_dir / "config"
            current = _compute_checksums(config_dir, _BUNDLED_CONFIGS)

            drifted = []
            for fname in sorted(set(saved_checksums) | set(current)):
                old = saved_checksums.get(fname, "(missing)")
                new = current.get(fname, "(missing)")
                if old != new:
                    drifted.append(f"{fname}: saved={old[:8]}… current={new[:8]}…")

            if drifted:
                print("  [config] ⚠ Config drift detected:")
                for d in drifted:
                    print(f"    • {d}")
            else:
                print("  [config] All config checksums match — no drift")

    if errors:
        print()
        print("Errors:")
        for e in errors:
            print(f"  ✗ {e}")
        return 1

    print()
    print("Update complete.")
    return 0


# ── CLI entry point ──────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for ``python-setup install`` / ``update``."""
    parser = argparse.ArgumentParser(
        prog="python-setup",
        description="Set up python-setup tooling in a Python project",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # install
    install_p = sub.add_parser("install", help="Idempotently install python-setup tooling")
    install_p.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Target project directory (default: current directory)",
    )
    install_p.add_argument(
        "--dev-path",
        help="Local path to python-setup for development (uses git URL otherwise)",
    )

    # update
    update_p = sub.add_parser("update", help="Update python-setup and check config drift")
    update_p.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Target project directory (default: current directory)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for ``python-setup install`` / ``python-setup update``."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "install":
        return install(args.path.resolve(), dev_path=args.dev_path)
    if args.command == "update":
        return update(args.path.resolve())

    print(f"Unknown command: {args.command}", file=sys.stderr)
    return 1
