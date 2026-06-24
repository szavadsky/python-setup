"""Phase 3 orchestrator — top-level dispatcher for stub-impl fidelity.

Public entrypoint :func:`emit_fidelity_violations` walks every module
in the checker's ``stub_index`` and delegates per-module dispatchers
in the documented order:

1. :func:`._kind._emit_stub_symbol_check` — E97B1 / E97B2 + class dispatch.
2. :func:`._annotation._emit_variable_fidelity` — module variable fidelity.
3. :func:`._signature._emit_callable_fidelity` — callable signature fidelity.

Kept in its own module so the public entry point has a ``.pyi`` companion
and the package ``__init__.py`` stays a pure re-export hub (CodingRules
exemption: an ``__init__.py`` with logic requires a ``.pyi``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .annotation import _emit_variable_fidelity
from .kind import _emit_stub_symbol_check
from .signature import _emit_callable_fidelity

if TYPE_CHECKING:
    from python_setup_lint.checkers.stub_checker import StubChecker

__all__ = ["emit_fidelity_violations"]


def emit_fidelity_violations(checker: StubChecker) -> None:
    for module_name in checker._coverage.stub_index:
        _emit_stub_symbol_check(checker, module_name)
        _emit_variable_fidelity(checker, module_name)
        _emit_callable_fidelity(checker, module_name)
