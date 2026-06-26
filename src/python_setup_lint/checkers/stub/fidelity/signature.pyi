"""Callable fidelity comparison (Invariant 3 — the E97B3 family) — stub.

See ``signature.py`` for full docstrings.

Functions in this module extract :class:`ParamDescriptor` lists, compare
parameter and return annotations, and emit E97B3/E97B4/I97B6 via the
``StubChecker``.
"""

from typing import TYPE_CHECKING

from astroid import nodes

from ._ast_helpers import CallableComparisonCtx, ParamDescriptor

if TYPE_CHECKING:
    from python_setup_lint.checkers.stub.checker import StubChecker

    args: nodes.Arguments,
    *,
    strip_self: bool = ...,
) -> list[ParamDescriptor]:
    """Build a list of ``ParamDescriptor`` from an Astroid ``Arguments`` node.

    If *strip_self* is True and the first parameter is named ``self`` or
    ``cls``, it is excluded from the result.
    """

    stub_params: list[ParamDescriptor],
    impl_params: list[ParamDescriptor],
) -> str | None:
    """Compare two parameter descriptor lists, returning a detail string on
    mismatch or None if they match.

    Checks: count, name, kind, default-presence.
    """

    stub_params: list[ParamDescriptor],
    impl_params: list[ParamDescriptor],
) -> list[tuple[str, str, str]]:
    """Compare parameter annotations between stub and impl descriptors.

    Returns a list of ``(param_name, stub_normalized, impl_normalized)``
    tuples for mismatches. Only reports mismatches when both sides have
    an annotation.
    """

    stub_returns: nodes.NodeNG | None,
    impl_returns: nodes.NodeNG | None,
) -> tuple[str | None, str | None]:
    """Compare return annotations.

    Returns ``(stub_normalized, impl_normalized)`` where either may be
    None if the annotation is absent or unverifiable. Both are None when
    there is nothing to compare.
    """

    """Emit E97B3/E97B4/I97B6 for a single callable pair.

    If *impl_func* is None, the function exists only in the stub — no
    comparison can be done (handled separately by coverage logic).
    """

    """Compare callable signatures between stub and impl for *module_name*.

    Dispatches to ``_emit_callable_fidelity_issues`` for each stub callable.
    """
