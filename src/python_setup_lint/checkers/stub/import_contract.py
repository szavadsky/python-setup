"""Phase 2 enforcement — import contract (Invariant 2).

Every project-local import in non-test code refers to a symbol/module
declared in the target's .pyi.

Extracted from stub_checker.py. No logic change.
"""

from __future__ import annotations

import structlog
from dataclasses import dataclass
from typing import TYPE_CHECKING

from astroid import nodes

if TYPE_CHECKING:
    from python_setup_lint.checkers.stub.checker import StubChecker

log = structlog.get_logger(__name__)

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
    parent = node.parent
    while parent is not None:
        if isinstance(parent, nodes.If):
            if _is_type_checking_guard(parent.test):
                return True
        parent = parent.parent
    return False


def _is_type_checking_guard(test: nodes.NodeNG) -> bool:
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


def emit_import_contract_violations(checker: StubChecker) -> None:  # pylint: disable=missing-beartype  # StubChecker is TYPE_CHECKING-only; beartype can't resolve at runtime
    c = checker._coverage
    for usage in c.import_usages:
        target = usage.target_module

        # Only enforce project-local imports
        if target not in c.module_index:
            continue

        entry = c.module_index.get(usage.importer_module)
        importer_node: nodes.Module | None = entry[1] if entry is not None else None

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
