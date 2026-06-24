"""Symbol-presence + kind-mismatch dispatch (Invariant 3 — the E97B1/E97B2 family) — stub.

See ``kind.py`` for full docstrings.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from python_setup_lint.checkers.stub_checker import StubChecker

def _emit_stub_symbol_check(checker: StubChecker, module_name: str) -> None:
    """Emit E97B1/E97B2 and class comparison for all stub symbols.

    E97B1: symbol declared in stub but absent from implementation.
    E97B2: symbol exists in both but with different kind (class vs function vs var).
    """
