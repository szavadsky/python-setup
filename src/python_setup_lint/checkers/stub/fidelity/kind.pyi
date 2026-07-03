"""Symbol-presence + kind-mismatch dispatch (Invariant 3 — the E97B1/E97B2 family) — stub.

See ``kind.py`` for full docstrings.
"""

from collections.abc import Mapping
from typing import TYPE_CHECKING

from astroid import nodes

from ._ast_helpers import (  # type: ignore[attr-defined]  # private symbol removed from .pyi per M3(b); runtime import still works
    _FidelityState,
)

if TYPE_CHECKING:
    from python_setup_lint.checkers.stub.checker import StubChecker

def _build_stub_kinds(
    stub_vars: Mapping[str, object],
    stub_callables: Mapping[str, object],
    stub_classes: Mapping[str, object],
) -> dict[str, str]:
    """Build a symbol-name to kind mapping from stub declarations."""

def _build_impl_kinds(
    f: _FidelityState,
    module_name: str,
    impl_all: set[str],
) -> dict[str, str]:
    """Build a symbol-name to kind mapping from implementation declarations."""

def _check_missing_symbols(
    stub_kinds: dict[str, str],
    impl_kinds: dict[str, str],
    impl_all: set[str],
    checker: StubChecker,
    module_name: str,
) -> None:
    """Emit violations for symbols present in stub but missing from impl."""

def _compare_matched_classes(
    stub_classes: Mapping[str, nodes.ClassDef],
    f: _FidelityState,
    checker: StubChecker,
    module_name: str,
) -> None:
    """Compare matched class definitions between stub and impl."""

def _emit_stub_symbol_check(checker: StubChecker, module_name: str) -> None:
    """Emit E97B1/E97B2 and class comparison for all stub symbols.

    E97B1: symbol declared in stub but absent from implementation.
    E97B2: symbol exists in both but with different kind (class vs function vs var).
    """
