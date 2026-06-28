"""Phase 3 orchestrator — top-level dispatcher for stub-impl fidelity — stub.

See ``orchestrator.py`` for full docstrings.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from python_setup_lint.checkers.stub.checker import StubChecker

def emit_fidelity_violations(checker: StubChecker) -> None:
    """Emit all Phase 3 violations for every module in *stub_index*.

    Calls ``_emit_stub_symbol_check``, ``_emit_variable_fidelity``,
    and ``_emit_callable_fidelity`` for each module.
    """
