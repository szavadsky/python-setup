"""Symbol-presence + kind-mismatch dispatch (Invariant 3 — the E97B1/E97B2 family).

Walks stub symbols for each module and emits:

- E97B1 (``stub-symbol-missing``) when a stub-declared symbol is absent from the
  implementation.
- E97B2 (``symbol-kind-mismatch``) when stub and impl disagree on the symbol
  kind (variable / callable / class).

For each matched class also delegates class-base / class-method /
class-attribute comparison into :mod:`._ast_helpers` consumers
(:mod:`.annotation`).

Functions:

- :func:`_emit_stub_symbol_check` — emits E97B1/E97B2 and dispatches class comparison.

Topologically the upstream-most dispatcher: depends on ``_ast_helpers``
(``ClassComparisonCtx``) and ``annotation`` (the class compare helpers).
"""

from __future__ import annotations

import structlog
from collections.abc import Mapping
from typing import TYPE_CHECKING

from ._ast_helpers import ClassComparisonCtx, _FidelityState

from .annotation import (
    _compare_class_attrs,
    _compare_class_bases,
    _compare_class_methods,
)

if TYPE_CHECKING:
    from astroid import nodes
    from python_setup_lint.checkers.stub.checker import StubChecker

log = structlog.get_logger(__name__)

__all__ = ["_emit_stub_symbol_check"]


def _build_stub_kinds(
    stub_vars: Mapping[str, object],
    stub_callables: Mapping[str, object],
    stub_classes: Mapping[str, object],
) -> dict[str, str]:
    stub_kinds: dict[str, str] = {}
    for vname in stub_vars:
        stub_kinds[vname] = "variable"
    for fname in stub_callables:
        stub_kinds[fname] = "callable"
    for cname in stub_classes:
        stub_kinds[cname] = "class"
    return stub_kinds


def _build_impl_kinds(
    f: _FidelityState,
    module_name: str,
    impl_all: set[str],
) -> dict[str, str]:
    impl_kinds: dict[str, str] = {}
    for iname in impl_all:
        if iname in f.impl_callable_nodes.get(module_name, {}):
            impl_kinds[iname] = "callable"
        elif iname in f.impl_class_nodes.get(module_name, {}):
            impl_kinds[iname] = "class"
        elif iname in f.impl_annotations.get(module_name, {}):
            impl_kinds[iname] = "variable"
        else:
            impl_kinds[iname] = "unknown"
    return impl_kinds


def _check_missing_symbols(
    stub_kinds: dict[str, str],
    impl_kinds: dict[str, str],
    impl_all: set[str],
    checker: StubChecker,
    module_name: str,
) -> None:
    impl_node = checker._coverage.module_index.get(module_name, (None, None))[1]
    for sym_name, stub_kind in stub_kinds.items():
        if sym_name not in impl_all:
            log.debug(
                "Stub symbol has no implementation", symbol=sym_name, module=module_name
            )
            checker.add_message(
                "stub-symbol-missing",
                node=impl_node,
                args=(sym_name, module_name),
            )
        else:
            impl_kind = impl_kinds.get(sym_name, "unknown")
            if stub_kind != impl_kind:
                log.debug(
                    "Kind mismatch",
                    symbol=sym_name,
                    module=module_name,
                    stub_kind=stub_kind,
                    impl_kind=impl_kind,
                )
                checker.add_message(
                    "symbol-kind-mismatch",
                    node=impl_node,
                    args=(sym_name, module_name, stub_kind, impl_kind),
                )


def _compare_matched_classes(
    stub_classes: Mapping[str, nodes.ClassDef],
    f: _FidelityState,
    checker: StubChecker,
    module_name: str,
) -> None:
    impl_node = checker._coverage.module_index.get(module_name, (None, None))[1]
    if impl_node is None:
        return
    for cname, stub_class in stub_classes.items():
        impl_class = f.impl_class_nodes.get(module_name, {}).get(cname)
        if impl_class is None:
            continue
        ctx = ClassComparisonCtx(
            checker=checker,
            module_name=module_name,
            class_name=cname,
            msg_node=impl_node,
            stub_class=stub_class,
            impl_class=impl_class,
        )
        _compare_class_bases(ctx)
        _compare_class_methods(ctx)
        _compare_class_attrs(ctx)


def _emit_stub_symbol_check(checker: StubChecker, module_name: str) -> None:
    f = checker._fidelity
    impl_all = f.impl_all_names.get(module_name, set())
    stub_vars = f.stub_variable_nodes.get(module_name, {})
    stub_callables = f.stub_callable_nodes.get(module_name, {})
    stub_classes = f.stub_class_nodes.get(module_name, {})

    impl_node = checker._coverage.module_index.get(module_name, (None, None))[1]
    if impl_node is None:
        return

    stub_kinds = _build_stub_kinds(stub_vars, stub_callables, stub_classes)
    impl_kinds = _build_impl_kinds(f, module_name, impl_all)
    _check_missing_symbols(stub_kinds, impl_kinds, impl_all, checker, module_name)
    _compare_matched_classes(stub_classes, f, checker, module_name)
