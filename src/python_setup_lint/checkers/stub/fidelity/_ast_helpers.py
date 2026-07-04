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
    stub_variable_nodes: dict[str, dict[str, nodes.AnnAssign]] = field(default_factory=dict)
    impl_annotations: dict[
        str,
        dict[str, tuple[nodes.NodeNG | None, nodes.AnnAssign | nodes.Assign | None]],
    ] = field(default_factory=dict)
    stub_callable_nodes: dict[str, dict[str, nodes.FunctionDef | nodes.AsyncFunctionDef]] = field(default_factory=dict)
    impl_callable_nodes: dict[str, dict[str, nodes.FunctionDef | nodes.AsyncFunctionDef]] = field(default_factory=dict)
    stub_class_nodes: dict[str, dict[str, nodes.ClassDef]] = field(default_factory=dict)
    impl_class_nodes: dict[str, dict[str, nodes.ClassDef]] = field(default_factory=dict)
    impl_all_names: dict[str, set[str]] = field(default_factory=dict)


@dataclass
class ParamDescriptor:
    name: str
    kind: inspect._ParameterKind
    has_default: bool
    annotation_normalized: str | None


@dataclass
class ClassComparisonCtx:
    checker: StubChecker
    module_name: str
    class_name: str
    msg_node: nodes.NodeNG
    stub_class: nodes.ClassDef
    impl_class: nodes.ClassDef


@dataclass
class CallableComparisonCtx:
    checker: StubChecker
    module_name: str
    func_name: str
    msg_node: nodes.NodeNG
    stub_func: nodes.FunctionDef | nodes.AsyncFunctionDef
    impl_func: nodes.FunctionDef | nodes.AsyncFunctionDef | None
