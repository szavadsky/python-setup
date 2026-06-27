"""Variable + class annotation fidelity (Invariant 3 — the E97B4/W97B5/I97B6 family).

Compares module-level variable annotations between stub and impl,
compares class base lists / public methods / class-level attributes,
and emits the corresponding message ids.

Functions:
- :func:`_normalize_bases` — normalise base-class AST nodes to a sorted, comparable list.
- :func:`_is_public_method` — public-method predicate used by ``_compare_class_methods``.
- :func:`_is_classvar` — detects ``ClassVar[...]`` AST pattern.
- :func:`_compare_class_bases` — emits E97B4 when normalised base lists differ.
- :func:`_compare_class_methods` — delegates public methods to ``signature._emit_callable_fidelity_issues``.
- :func:`_compare_class_attrs` — emits W97B5/E97B4/I97B6 per class-level attribute.
- :func:`_emit_variable_fidelity` — dispatches variable annotation comparison per module.

Topologically downstream of ``_ast_helpers`` and ``signature``
(``_compare_class_methods`` delegates callable compare into
``signature._emit_callable_fidelity_issues``).
"""

from __future__ import annotations

import structlog
from typing import TYPE_CHECKING

from astroid import nodes

from python_setup_lint.checkers.stub.normalizer import AnnotationNormalizer

from ._ast_helpers import CallableComparisonCtx, ClassComparisonCtx
from .signature import _emit_callable_fidelity_issues

if TYPE_CHECKING:
    from python_setup_lint.checkers.stub.checker import StubChecker

log = structlog.get_logger(__name__)

__all__ = [
    "_compare_class_attrs",
    "_compare_class_bases",
    "_compare_class_methods",
    "_emit_variable_fidelity",
    "_is_classvar",
    "_is_public_method",
    "_normalize_bases",
]


def _normalize_bases(bases: list[nodes.NodeNG]) -> list[str]:
    normalized: list[str] = []
    for base in bases:
        if isinstance(base, nodes.Subscript):
            name = _normalize_bases([base.value])[0] if base.value else "?"
            normalized.append(name)
        elif isinstance(base, nodes.Name):
            name = base.name
            if name == "object":
                name = "builtins.object"
            normalized.append(name)
        elif isinstance(base, nodes.Attribute):
            normalized.append(base.attrname)
    normalized.sort()
    return normalized


def _is_public_method(member_name: str) -> bool:
    if member_name in ("__init__", "__new__"):
        return True
    return not member_name.startswith("_")


def _is_classvar(ann_node: nodes.NodeNG) -> bool:
    return (
        isinstance(ann_node, nodes.Subscript)
        and isinstance(ann_node.value, nodes.Name)
        and ann_node.value.name == "ClassVar"
    )


def _compare_class_bases(ctx: ClassComparisonCtx) -> None:
    stub_bases = _normalize_bases(ctx.stub_class.bases)
    impl_bases = _normalize_bases(ctx.impl_class.bases)
    if stub_bases != impl_bases:
        stub_str = ", ".join(stub_bases) if stub_bases else "(none)"
        impl_str = ", ".join(impl_bases) if impl_bases else "(none)"
        log.debug(
            "Base class mismatch",
            class_name=ctx.class_name,
            module=ctx.module_name,
            stub=stub_str,
            impl=impl_str,
        )
        ctx.checker.add_message(
            "annotation-mismatch",
            node=ctx.msg_node,
            args=(ctx.class_name, ctx.module_name, stub_str, impl_str),
        )


def _compare_one_method(
    ctx: ClassComparisonCtx,
    name: str,
    stub_method: nodes.FunctionDef | nodes.AsyncFunctionDef,
    impl_method: nodes.FunctionDef | nodes.AsyncFunctionDef | None,
) -> None:
    _emit_callable_fidelity_issues(
        CallableComparisonCtx(
            checker=ctx.checker,
            module_name=ctx.module_name,
            func_name=f"{ctx.class_name}.{name}",
            msg_node=ctx.msg_node,
            stub_func=stub_method,
            impl_func=impl_method,
        )
    )


def _compare_class_methods(ctx: ClassComparisonCtx) -> None:
    stub_methods: dict[str, nodes.FunctionDef | nodes.AsyncFunctionDef] = {}
    impl_methods: dict[str, nodes.FunctionDef | nodes.AsyncFunctionDef] = {}
    for child in ctx.stub_class.body:
        if isinstance(
            child, (nodes.FunctionDef, nodes.AsyncFunctionDef)
        ) and _is_public_method(child.name):
            stub_methods[child.name] = child
    for child in ctx.impl_class.body:
        if isinstance(
            child, (nodes.FunctionDef, nodes.AsyncFunctionDef)
        ) and _is_public_method(child.name):
            impl_methods[child.name] = child

    for mname, stub_method in stub_methods.items():
        _compare_one_method(ctx, mname, stub_method, impl_methods.get(mname))


def _compare_one_attr(
    ctx: ClassComparisonCtx,
    attr_name: str,
    stub_annotation: nodes.NodeNG | None,
    impl_annotation: nodes.NodeNG | None,
    attr_msg_node: nodes.NodeNG,
) -> None:
    if stub_annotation is not None and impl_annotation is None:
        if ctx.checker._coverage.impl_missing_policy in ("error", "warn"):
            log.debug(
                "Impl missing annotation for class attr",
                class_name=ctx.class_name,
                attr=attr_name,
                module=ctx.module_name,
            )
            ctx.checker.add_message(
                "impl-missing-annotation",
                node=attr_msg_node,
                args=(f"{ctx.class_name}.{attr_name}", ctx.module_name),
            )
    elif stub_annotation is not None and impl_annotation is not None:
        stub_norm = AnnotationNormalizer.normalize(stub_annotation)
        impl_norm = AnnotationNormalizer.normalize(impl_annotation)
        if stub_norm is None or impl_norm is None:
            log.debug(
                "Normalization failed for class attr",
                class_name=ctx.class_name,
                attr=attr_name,
                module=ctx.module_name,
            )
            ctx.checker.add_message(
                "annotation-unverifiable",
                node=attr_msg_node,
                args=(f"{ctx.class_name}.{attr_name}", ctx.module_name),
            )
        elif stub_norm != impl_norm:
            log.debug(
                "Annotation mismatch for class attr",
                class_name=ctx.class_name,
                attr=attr_name,
                module=ctx.module_name,
                stub=stub_norm,
                impl=impl_norm,
            )
            ctx.checker.add_message(
                "annotation-mismatch",
                node=attr_msg_node,
                args=(
                    f"{ctx.class_name}.{attr_name}",
                    ctx.module_name,
                    stub_norm,
                    impl_norm,
                ),
            )
        else:
            log.debug(
                "Annotations match for class attr",
                class_name=ctx.class_name,
                attr=attr_name,
                module=ctx.module_name,
                annotation=stub_norm,
            )


def _build_attr_index(
    ctx: ClassComparisonCtx,
) -> tuple[
    dict[str, nodes.AnnAssign],
    dict[str, tuple[nodes.NodeNG | None, nodes.AnnAssign | nodes.Assign | None]],
]:
    # no docstring — moved to .pyi stub
    stub_attrs: dict[str, nodes.AnnAssign] = {}
    impl_attrs: dict[
        str, tuple[nodes.NodeNG | None, nodes.AnnAssign | nodes.Assign | None]
    ] = {}
    for child in ctx.stub_class.body:
        if isinstance(child, nodes.AnnAssign) and isinstance(
            child.target, nodes.AssignName
        ):
            if child.annotation is not None and _is_classvar(child.annotation):
                log.debug(
                    "Skipping ClassVar",
                    name=child.target.name,
                    class_name=ctx.class_name,
                    module=ctx.module_name,
                )
                continue
            stub_attrs[child.target.name] = child
    for child in ctx.impl_class.body:
        if isinstance(child, nodes.AnnAssign) and isinstance(
            child.target, nodes.AssignName
        ):
            impl_attrs[child.target.name] = (child.annotation, child)
        elif isinstance(child, nodes.Assign):
            for t in child.targets:
                if isinstance(t, nodes.AssignName):
                    impl_attrs[t.name] = (None, child)
    return stub_attrs, impl_attrs


def _compare_class_attrs(ctx: ClassComparisonCtx) -> None:
    stub_attrs, impl_attrs = _build_attr_index(ctx)
    for attr_name, stub_attr_node in stub_attrs.items():
        stub_annotation = stub_attr_node.annotation
        impl_data = impl_attrs.get(attr_name, (None, None))
        impl_annotation, impl_source_node = impl_data
        attr_msg_node = (
            impl_source_node if impl_source_node is not None else ctx.msg_node
        )
        _compare_one_attr(
            ctx, attr_name, stub_annotation, impl_annotation, attr_msg_node
        )


def _check_one_variable(
    checker: StubChecker,
    module_name: str,
    var_name: str,
    stub_ann_node: nodes.AnnAssign,
    *,
    impl_vars: dict[str, tuple[nodes.NodeNG | None, nodes.NodeNG | None]],
    impl_node: nodes.Module,
    impl_missing_policy: str,
) -> None:
    # no docstring — moved to .pyi stub
    stub_annotation = stub_ann_node.annotation
    if stub_annotation is not None and _is_classvar(stub_annotation):
        return

    impl_annotation, impl_source_node = impl_vars.get(var_name, (None, None))
    msg_node = impl_source_node if impl_source_node is not None else impl_node

    if stub_annotation is not None and impl_annotation is None:
        if impl_missing_policy in ("error", "warn"):
            checker.add_message(
                "impl-missing-annotation",
                node=msg_node,
                args=(var_name, module_name),
            )
    elif stub_annotation is not None and impl_annotation is not None:
        stub_normalized = AnnotationNormalizer.normalize(stub_annotation)
        impl_normalized = AnnotationNormalizer.normalize(impl_annotation)

        if stub_normalized is None or impl_normalized is None:
            checker.add_message(
                "annotation-unverifiable",
                node=msg_node,
                args=(var_name, module_name),
            )
        elif stub_normalized != impl_normalized:
            checker.add_message(
                "annotation-mismatch",
                node=msg_node,
                args=(var_name, module_name, stub_normalized, impl_normalized),
            )


def _emit_variable_fidelity(checker: StubChecker, module_name: str) -> None:
    f = checker._fidelity
    c = checker._coverage
    stub_vars = f.stub_variable_nodes.get(module_name, {})
    impl_vars = f.impl_annotations.get(module_name, {})
    impl_all = f.impl_all_names.get(module_name, set())

    if not stub_vars:
        return

    impl_node = c.module_index.get(module_name, (None, None))[1]
    if impl_node is None:
        return

    for var_name, stub_ann_node in stub_vars.items():
        if var_name not in impl_all:
            continue
        _check_one_variable(
            checker,
            module_name,
            var_name,
            stub_ann_node,
            impl_vars=impl_vars,
            impl_node=impl_node,
            impl_missing_policy=c.impl_missing_policy,
        )
