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

from beartype import beartype

if TYPE_CHECKING:
    from collections.abc import Sequence


# ── Constants ───────────────────────────────────────────────────────

_PACKAGE_NAME: str = "python-setup"
_GIT_URL: str = "git+https://github.com/szavadsky/python-setup"
_STATE_FILE: str = ".python-setup-state.json"

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
    @beartype
    def all_ok(self) -> bool:
        return len(self.errors) == 0

# ── Helpers ─────────────────────────────────────────────────────────

def _compute_checksums(config_dir: Path, files: Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for fname in files:
        fpath = config_dir / fname
        if fpath.is_file():
            result[fname] = hashlib.sha256(fpath.read_bytes()).hexdigest()
    return result

def _discover_checkers() -> list[str]:
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
    toml_path = project_dir / "pyproject.toml"
    if not toml_path.is_file():
        return None
    with open(toml_path, "rb") as f:
        return tomllib.load(f)

def _write_pyproject_toml(project_dir: Path, data: dict[str, object]) -> None:
    import tomli_w

    toml_path = project_dir / "pyproject.toml"
    _atomic_write(toml_path, tomli_w.dumps(data))

def _pylint_main_section(data: dict[str, object]) -> dict | None:
    tool = data.get("tool", {})
    if not isinstance(tool, dict):
        return None
    pylint = tool.get("pylint", {})
    if not isinstance(pylint, dict):
        return None
    main = pylint.get("main", {})
    if not isinstance(main, dict):
        return None
    return main


def _get_pylint_load_plugins(data: dict[str, object]) -> list[str]:
    main = _pylint_main_section(data)
    if main is None:
        return []
    plugins = main.get("load-plugins", [])
    if isinstance(plugins, list):
        return [str(p) for p in plugins]
    return []


def _ensure_pylint_main_section(data: dict[str, object]) -> dict | None:
    tool = data.setdefault("tool", {})
    if not isinstance(tool, dict):
        return None
    pylint = tool.setdefault("pylint", {})
    if not isinstance(pylint, dict):
        return None
    main = pylint.setdefault("main", {})
    if not isinstance(main, dict):
        return None
    return main


def _set_pylint_load_plugins(data: dict[str, object], plugins: list[str]) -> None:
    main = _ensure_pylint_main_section(data)
    if main is not None:
        main["load-plugins"] = plugins

def _get_dev_deps(data: dict[str, object]) -> list[str]:
    dg = data.get("dependency-groups", {})
    if not isinstance(dg, dict):
        return []
    dev = dg.get("dev", [])
    if isinstance(dev, list):
        return [str(d) for d in dev]
    return []

def _has_python_setup_dep(dev_deps: list[str]) -> bool:
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
    args = (
        ["add", "--dev", dev_path]
        if dev_path
        else ["add", "--dev", f"python-setup @ {_GIT_URL}"]
    )

    rc, stdout, stderr = _run_uv(args, cwd=project_dir)
    if rc != 0:
        state.errors.append(f"uv add python-setup failed: {stderr.strip()}")
        return

    state.dep_added = True
    print("  [dependency] Added python-setup to dev dependencies")

def _step_pylint_plugins(state: SetupState, project_dir: Path) -> None:
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

def _format_install_summary(state: SetupState) -> list[str]:
    actions: list[str] = []
    _SUMMARY_ITEMS: tuple[tuple[str, str], ...] = (
        ("dep_added", "added python-setup dependency"),
        ("dep_skipped", "dependency already present"),
        ("pylint_plugins_added", "added pylint load-plugins"),
        ("pylint_plugins_skipped", "pylint plugins already configured"),
        ("precommit_written", "wrote .pre-commit-config.yaml"),
        ("precommit_skipped", "pre-commit config already exists"),
        ("coding_rules_copied", "copied CodingRules.md"),
        ("coding_rules_skipped", "CodingRules.md already exists"),
        ("agents_appended", "appended AGENTS.md snippet"),
        ("agents_skipped", "AGENTS.md snippet skipped"),
    )
    for attr, msg in _SUMMARY_ITEMS:
        if getattr(state, attr):
            actions.append(msg)
    return actions


def _check_config_drift(project_dir: Path) -> list[str]:
    state_path = project_dir / _STATE_FILE
    if not state_path.exists():
        print("  [config] No .python-setup-state.json — skipping drift check")
        return []

    try:
        saved = json.loads(state_path.read_text(encoding="utf-8"))
        saved_checksums: dict[str, str] = saved.get("config_checksums", {})
    except (json.JSONDecodeError, KeyError):
        print(
            "  [config] .python-setup-state.json unreadable — skipping drift check"
        )
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
        print("  [config] ⚠ Config drift detected:")
        for d in drifted:
            print(f"    • {d}")
    else:
        print("  [config] All config checksums match — no drift")

    return drifted

def _run_update_steps(project_dir: Path) -> list[str]:
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

    return errors

# ── Install command ──────────────────────────────────────────────────

@beartype
def install(
    project_dir: Path,
    *,
    dev_path: str | None = None,
) -> int:
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

    actions = _format_install_summary(state)

    if not actions:
        print("Already fully configured — nothing to do.")
    else:
        print("Summary:")
        for a in actions:
            print(f"  ✓ {a}")

    return 0

# ── Update command ───────────────────────────────────────────────────

@beartype
def update(project_dir: Path) -> int:
    print(f"python-setup update → {project_dir}")

    errors = _run_update_steps(project_dir)

    _check_config_drift(project_dir)

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
    parser = argparse.ArgumentParser(
        prog="python-setup",
        description="Set up python-setup tooling in a Python project",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # install
    install_p = sub.add_parser(
        "install", help="Idempotently install python-setup tooling"
    )
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
    update_p = sub.add_parser(
        "update", help="Update python-setup and check config drift"
    )
    update_p.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Target project directory (default: current directory)",
    )

    return parser

@beartype
def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "install":
        return install(args.path.resolve(), dev_path=args.dev_path)
    if args.command == "update":
        return update(args.path.resolve())

    print(f"Unknown command: {args.command}", file=sys.stderr)
    return 1
