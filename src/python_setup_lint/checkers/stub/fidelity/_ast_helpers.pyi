"""Shared state types for the stub-fidelity package (Invariant 3) — stub.

Holds the dataclasses and per-call state flowing between the cohesive
sub-modules.  See ``_ast_helpers.py`` for full docstrings.
"""

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING

from astroid import nodes

if TYPE_CHECKING:
    from python_setup_lint.checkers.stub.checker import StubChecker


@dataclass
class ParamDescriptor:
    """Canonical parameter form for stub-vs-impl comparison."""

    name: str
    kind: inspect._ParameterKind
    has_default: bool
    annotation_normalized: str | None

@dataclass
class ClassComparisonCtx:
    """Context bundle for comparing a single class stub-vs-impl pair."""

    checker: StubChecker
    module_name: str
    class_name: str
    msg_node: nodes.NodeNG
    stub_class: nodes.ClassDef
    impl_class: nodes.ClassDef

@dataclass
class CallableComparisonCtx:
    """Context bundle for comparing a single callable stub-vs-impl pair."""

    checker: StubChecker
    module_name: str
    func_name: str
    msg_node: nodes.NodeNG
    stub_func: nodes.FunctionDef | nodes.AsyncFunctionDef
    impl_func: nodes.FunctionDef | nodes.AsyncFunctionDef | None
@dataclass
class _FidelityState:
    """Per-module state for stub-fidelity comparison."""

    stub_variable_nodes: dict[str, dict[str, nodes.AnnAssign]] = ...
    impl_annotations: dict[str, dict[str, tuple[nodes.NodeNG | None, nodes.AnnAssign | nodes.Assign | None]]] = ...
    stub_callable_nodes: dict[str, dict[str, nodes.FunctionDef | nodes.AsyncFunctionDef]] = ...
    impl_callable_nodes: dict[str, dict[str, nodes.FunctionDef | nodes.AsyncFunctionDef]] = ...
    stub_class_nodes: dict[str, dict[str, nodes.ClassDef]] = ...
    impl_class_nodes: dict[str, dict[str, nodes.ClassDef]] = ...
    impl_all_names: dict[str, set[str]] = ...
