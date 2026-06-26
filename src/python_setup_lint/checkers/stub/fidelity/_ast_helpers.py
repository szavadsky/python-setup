"""Shared state types for the stub-fidelity package (Invariant 3).

Holds the dataclasses and the per-call state that flows between the
cohesive sub-modules (`signature.py`, `annotation.py`, `kind.py`).

Definitions:

- ``_FidelityState``  — aggregated stub/impl node maps keyed by module.
- ``ParamDescriptor``  — canonical form of a single callable parameter.
- ``ClassComparisonCtx``  — context bundle for one class stub-vs-impl pair.
- ``CallableComparisonCtx``  — context bundle for one callable stub-vs-impl pair.

These types are re-exported by ``stub_fidelity/__init__.py`` so external
test imports (`from python_setup_lint.checkers.stub_fidity import
ParamDescriptor, ClassComparisonCtx, ...`) and intra-package imports
resolve unchanged after the T10 split.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import inspect

    from astroid import nodes

    from python_setup_lint.checkers.stub.checker import StubChecker

__all__ = [
    "CallableComparisonCtx",
    "ClassComparisonCtx",
    "ParamDescriptor",
    "_FidelityState",
]

@dataclass
class _FidelityState:
    """Phase 3 state aggregated for StubChecker.

    Stores stub and implementation AST node references for variable,
    callable, and class comparison.
    """

    stub_variable_nodes: dict[str, dict[str, nodes.AnnAssign]] = field(
        default_factory=dict
    )
    impl_annotations: dict[
        str,
        dict[str, tuple[nodes.NodeNG | None, nodes.AnnAssign | nodes.Assign | None]],
    ] = field(default_factory=dict)
    stub_callable_nodes: dict[
        str, dict[str, nodes.FunctionDef | nodes.AsyncFunctionDef]
    ] = field(default_factory=dict)
    impl_callable_nodes: dict[
        str, dict[str, nodes.FunctionDef | nodes.AsyncFunctionDef]
    ] = field(default_factory=dict)
    stub_class_nodes: dict[str, dict[str, nodes.ClassDef]] = field(default_factory=dict)
    impl_class_nodes: dict[str, dict[str, nodes.ClassDef]] = field(default_factory=dict)
    impl_all_names: dict[str, set[str]] = field(default_factory=dict)

@dataclass
class ParamDescriptor:
    """Canonical form of a single function parameter for comparison.

    *name* — parameter name.
    *kind* — ``inspect.Parameter`` kind constant.
    *has_default* — whether a default value is present.
    *annotation_normalized* — normalized annotation string, or None if absent.
    """

    name: str
    kind: inspect.Parameter.Kind  # type: ignore[name-defined]
    has_default: bool
    annotation_normalized: str | None

@dataclass
class ClassComparisonCtx:
    """Context bundle for comparing a single class stub-vs-impl pair.

    Collapses 6 positional arguments into a single dataclass (R0913 fix).
    """

    checker: StubChecker
    module_name: str
    class_name: str
    msg_node: nodes.NodeNG
    stub_class: nodes.ClassDef
    impl_class: nodes.ClassDef

@dataclass
class CallableComparisonCtx:
    """Context bundle for comparing a single callable stub-vs-impl pair.

    Collapses 6 positional arguments into a single dataclass (R0913 fix).
    """

    checker: StubChecker
    module_name: str
    func_name: str
    msg_node: nodes.NodeNG
    stub_func: nodes.FunctionDef | nodes.AsyncFunctionDef
    impl_func: nodes.FunctionDef | nodes.AsyncFunctionDef | None
