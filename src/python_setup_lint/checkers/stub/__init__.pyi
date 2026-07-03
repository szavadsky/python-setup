"""Phase 3 enforcement — stub-impl fidelity (Invariant 3).

Compares variable annotations, callable signatures, class structure,
and symbol presence/kind between .pyi stubs and .py implementations.

Public entrypoint: :func:`emit_fidelity_violations` (re-exported from
:mod:`.orchestrator`) — called from
:class:`~python_setup_lint.checkers.stub_checker.StubChecker.close` to
emit all Phase 3 violations for every module in the checker's
``stub_index``.
"""
