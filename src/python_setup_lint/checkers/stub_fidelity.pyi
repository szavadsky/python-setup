"""Phase 3 enforcement — stub-impl fidelity (Invariant 3).

Compares variable annotations, callable signatures, class structure,
and symbol presence/kind between .pyi stubs and .py implementations.

DocStrings:
- ``_extract_param_descriptors`` builds ``ParamDescriptor`` list from an Astroid Arguments node,
  supporting all 5 parameter kinds (POSITIONAL_ONLY, POSITIONAL_OR_KEYWORD, VAR_POSITIONAL,
  KEYWORD_ONLY, VAR_KEYWORD) and optional self/cls stripping.
- ``_compare_callable_descriptors`` compares count, name, kind, default-presence — returns
  detail string on mismatch, None on match.
- ``_compare_callable_annotations`` returns list of (param, stub, impl) triples where annotations
  differ (both sides annotated).
- ``_compare_return_annotations`` normalizes both sides — returns (stub_norm, impl_norm).
- ``_emit_callable_fidelity_issues`` dispatches E97B3/E97B4/I97B6 for one callable pair.
- ``_normalize_bases`` strips module prefixes, normalizes ``object`` → ``builtins.object``,
  extracts base from subscript nodes, sorts.
- ``_is_public_method`` — ``__init__``/``__new__`` or no leading ``_``.
- ``_is_classvar`` detects ``ClassVar[...]`` via Subscript+Name AST pattern.
- ``_compare_class_bases`` emits E97B4 when normalized base lists differ.
- ``_compare_class_methods`` delegates public methods to ``_emit_callable_fidelity_issues``.
- ``_compare_class_attrs`` emits W97B5/E97B4/I97B6 for class-level annotations.
- ``_emit_variable_fidelity`` compares module-level variable annotations between stub and impl.
- ``_emit_callable_fidelity`` dispatches all stub callables to ``_emit_callable_fidelity_issues``.
- ``_emit_stub_symbol_check`` emits E97B1/E97B2 and dispatches class comparison.
- ``ClassComparisonCtx`` bundles (checker, module_name, class_name, msg_node, stub_class, impl_class).
- ``CallableComparisonCtx`` bundles (checker, module_name, func_name, msg_node, stub_func, impl_func).
"""

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING

from astroid import nodes

if TYPE_CHECKING:
    from python_setup_lint.checkers.stub_checker import StubChecker

@dataclass
class _FidelityState:
    """Phase 3 state aggregated for StubChecker."""

    stub_variable_nodes: dict[str, dict[str, nodes.AnnAssign]] = ...
    impl_annotations: dict[str, dict[str, tuple[nodes.NodeNG | None, nodes.AnnAssign | None]]] = ...
    stub_callable_nodes: dict[str, dict[str, nodes.FunctionDef | nodes.AsyncFunctionDef]] = ...
    impl_callable_nodes: dict[str, dict[str, nodes.FunctionDef | nodes.AsyncFunctionDef]] = ...
    stub_class_nodes: dict[str, dict[str, nodes.ClassDef]] = ...
    impl_class_nodes: dict[str, dict[str, nodes.ClassDef]] = ...
    impl_all_names: dict[str, set[str]] = ...

@dataclass
class ParamDescriptor:
    """Canonical parameter form for stub-vs-impl comparison."""

    name: str
    kind: inspect.Parameter.Kind  # type: ignore[name-defined]
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

def emit_fidelity_violations(checker: StubChecker) -> None: ...
def _extract_param_descriptors(
    args: nodes.Arguments,
    *,
    strip_self: bool = False,
) -> list[ParamDescriptor]: ...
def _compare_callable_descriptors(
    stub_params: list[ParamDescriptor],
    impl_params: list[ParamDescriptor],
) -> str | None: ...
def _compare_callable_annotations(
    stub_params: list[ParamDescriptor],
    impl_params: list[ParamDescriptor],
) -> list[tuple[str, str, str]]: ...
def _compare_return_annotations(
    stub_returns: nodes.NodeNG | None,
    impl_returns: nodes.NodeNG | None,
) -> tuple[str | None, str | None]: ...
def _emit_callable_fidelity_issues(ctx: CallableComparisonCtx) -> None: ...