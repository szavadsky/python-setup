"""Phase 2 enforcement — import contract (Invariant 2).

DocStrings in pyi are required for non-trivial helpers:
- ``_in_type_checking_block`` walks parents to detect ``if TYPE_CHECKING:``.
- ``_is_type_checking_guard`` handles both Name and Attribute forms of TYPE_CHECKING.
- ``_resolve_relative`` implements level-arithmetic for dotted relative imports,
  handling package vs non-package modules and level > depth edge cases.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from astroid import nodes

if TYPE_CHECKING:
    from python_setup_lint.checkers.stub.checker import StubChecker

@dataclass
class ImportUsage:
    """A single import statement fact recorded during traversal."""

    importer_module: str
    lineno: int
    target_module: str
    symbol_name: str | None
    alias: str | None
    is_star: bool

    """Walk parent chain to detect ``if TYPE_CHECKING:`` guard.

    True if any ancestor ``If`` node has a ``TYPE_CHECKING`` test.
    """

    """Check if *test* is a ``TYPE_CHECKING`` name (Name or Attribute form)."""

    current_module: str,
    level: int,
    modname: str | None,
    *,
    is_package: bool = False,
) -> str:
    """Resolve relative import to absolute module name via level arithmetic.

    Package modules (``__init__.py``) use full name as package root;
    non-package modules strip leaf component. Trims ``level - 1`` parts
    for dotted relative imports (``..``, ``...``), capped at package depth.
    """

def emit_import_contract_violations(checker: StubChecker) -> None:
    """Emit E97A1/E97A2/E97A3 for every import usage that violates the contract."""
