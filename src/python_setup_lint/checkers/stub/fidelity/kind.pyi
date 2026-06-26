"""Symbol-presence + kind-mismatch dispatch (Invariant 3 — the E97B1/E97B2 family) — stub.

See ``kind.py`` for full docstrings.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from python_setup_lint.checkers.stub.checker import StubChecker

    stub_vars: dict[str, object],
    stub_callables: dict[str, object],
    stub_classes: dict[str, object],
) -> dict[str, str]:
    """Build a symbol-name to kind mapping from stub declarations."""

    f: object,
    module_name: str,
    impl_all: set[str],
) -> dict[str, str]:
    """Build a symbol-name to kind mapping from implementation declarations."""

    stub_kinds: dict[str, str],
    impl_kinds: dict[str, str],
    impl_all: set[str],
    checker: StubChecker,
    module_name: str,
) -> None:
    """Emit violations for symbols present in stub but missing from impl."""

    stub_classes: dict[str, object],
    f: object,
    checker: StubChecker,
    module_name: str,
) -> None:
    """Compare matched class definitions between stub and impl."""

    """Emit E97B1/E97B2 and class comparison for all stub symbols.

    E97B1: symbol declared in stub but absent from implementation.
    E97B2: symbol exists in both but with different kind (class vs function vs var).
    """
