"""Phase 2 enforcement — import contract (Invariant 2).

Every project-local import in non-test code refers to a symbol/module
declared in the target's .pyi.

Extracted from stub_checker.py. No logic change.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from astroid import nodes

if TYPE_CHECKING:
    from python_setup_lint.checkers.stub_checker import StubChecker

log = logging.getLogger(__name__)


# ── Import usage record ────────────────────────────────────────────────────────


@dataclass
class ImportUsage:
    """A single import statement fact recorded during traversal."""

    importer_module: str
    lineno: int
    target_module: str
    symbol_name: str | None  # None for ``import X``, str for ``from X import Y``
    alias: str | None
    is_star: bool


# ── TYPE_CHECKING guard detection ─────────────────────────────────────────────


def _in_type_checking_block(node: nodes.Import | nodes.ImportFrom) -> bool:
    """Check if *node* is inside a ``if TYPE_CHECKING:`` block."""
    parent = node.parent
    while parent is not None:
        if isinstance(parent, nodes.If):
            if _is_type_checking_guard(parent.test):
                return True
        parent = parent.parent
    return False


def _is_type_checking_guard(test: nodes.NodeNG) -> bool:
    """Check if *test* is a ``TYPE_CHECKING`` name reference."""
    if isinstance(test, nodes.Name) and test.name == "TYPE_CHECKING":
        return True
    return isinstance(test, nodes.Attribute) and test.attrname == "TYPE_CHECKING"


# ── Import resolution helpers ─────────────────────────────────────────────────


def _resolve_relative(
    current_module: str,
    level: int,
    modname: str | None,
    *,
    is_package: bool = False,
) -> str:
    """Resolve a relative import target to an absolute module name.

    Args:
        current_module: Fully qualified name of the importing module.
        level: Relative import level (0 for absolute, 1 for ``.``, etc.).
        modname: The "from" part (e.g. ``"server"`` in ``from .server import``).
        is_package: True if the importing module is a package (``__init__.py``).
                    Package modules use their full name as the package; non-package
                    modules derive the package by stripping the last component.
    """
    if level == 0:
        return modname or ""

    # Determine the package context
    parts = current_module.split(".")
    if not is_package:
        # Non-package: strip leaf module name to get package
        parts = parts[:-1]
    # level counts dots: "." → 1 dot = stay in same package (no trim),
    # ".." → 2 dots = one level up (trim 1), etc.
    # We trim (level - 1) components from the end.
    if level > 1 and parts:
        trim = min(level - 1, len(parts))
        parts = parts[:-trim]
    if modname:
        parts.append(modname)
    return ".".join(parts)


# ── Public API ─────────────────────────────────────────────────────────────────


def emit_import_contract_violations(checker: StubChecker) -> None:
    """Emit E97A1/E97A2/E97A3 for every import usage that violates the contract."""
    c = checker._coverage
    for usage in c.import_usages:
        target = usage.target_module

        # Only enforce project-local imports
        if target not in c.module_index:
            continue

        importer_node = c.module_index.get(usage.importer_module, (None, (None, None)))[1]

        # Check if target has a stub
        if target not in c.stub_index:
            checker.add_message(
                "missing-module-stub-for-import",
                node=importer_node,
                args=(target, usage.importer_module),
            )
            continue

        # Check star import policy
        if usage.is_star:
            if c.star_import_policy in ("error", "warn"):
                checker.add_message(
                    "star-import-unresolvable",
                    node=importer_node,
                    args=(target, usage.importer_module),
                )
            continue

        # Check symbol declaration
        if usage.symbol_name is not None:
            declarations = c.declaration_index.get(target, set())
            if usage.symbol_name not in declarations:
                checker.add_message(
                    "missing-import-declaration",
                    node=importer_node,
                    args=(usage.symbol_name, usage.importer_module, target),
                )