"""Phase 3 enforcement — stub-impl fidelity (Invariant 3).

Compares variable annotations, callable signatures, class structure,
and symbol presence/kind between .pyi stubs and .py implementations.

Extracted from stub_checker.py.  Mechanical cut-paste, decomposed for complexity.
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from astroid import nodes

if TYPE_CHECKING:
    from python_setup_lint.checkers.stub_checker import StubChecker

from python_setup_lint.checkers.stub_normalizer import AnnotationNormalizer

log = logging.getLogger(__name__)


@dataclass
class _FidelityState:
    """Phase 3 state aggregated for StubChecker.

    Stores stub and implementation AST node references for variable,
    callable, and class comparison.
    """

    stub_variable_nodes: dict[str, dict[str, nodes.AnnAssign]] = field(default_factory=dict)
    impl_annotations: dict[str, dict[str, tuple[nodes.NodeNG | None, nodes.AnnAssign | None]]] = field(default_factory=dict)
    stub_callable_nodes: dict[str, dict[str, nodes.FunctionDef | nodes.AsyncFunctionDef]] = field(default_factory=dict)
    impl_callable_nodes: dict[str, dict[str, nodes.FunctionDef | nodes.AsyncFunctionDef]] = field(default_factory=dict)
    stub_class_nodes: dict[str, dict[str, nodes.ClassDef]] = field(default_factory=dict)
    impl_class_nodes: dict[str, dict[str, nodes.ClassDef]] = field(default_factory=dict)
    impl_all_names: dict[str, set[str]] = field(default_factory=dict)


# ── Parameter descriptor ───────────────────────────────────────────────────────


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


# ── Parameter descriptor extraction ────────────────────────────────────────────


def _extract_param_descriptors(
    args: nodes.Arguments,
    *,
    strip_self: bool = False,
) -> list[ParamDescriptor]:
    """Build a list of ``ParamDescriptor`` from an Astroid ``Arguments`` node.

    If *strip_self* is True and the first parameter is named ``self`` or
    ``cls``, it is excluded from the result.
    """
    descriptors: list[ParamDescriptor] = []

    n_pos = len(args.posonlyargs)
    n_args = len(args.args)
    n_regular = n_pos + n_args
    n_defaults = len(args.defaults)

    def _has_default(idx: int) -> bool:
        """Check if parameter at index *idx* (across posonlyargs + args) has a default.

        Defaults are right-aligned in the ``defaults`` list.
        """
        return n_defaults > 0 and idx >= n_regular - n_defaults

    # Positional-only parameters
    for i, p in enumerate(args.posonlyargs):
        ann = (args.posonlyargs_annotations or [None] * n_pos)[i]
        descriptors.append(
            ParamDescriptor(
                name=p.name,
                kind=inspect.Parameter.POSITIONAL_ONLY,
                has_default=_has_default(i),
                annotation_normalized=(AnnotationNormalizer.normalize(ann) if ann is not None else None),
            )
        )

    # Positional-or-keyword parameters
    for i, p in enumerate(args.args):
        idx = n_pos + i
        ann = (args.annotations or [None] * n_args)[i]
        descriptors.append(
            ParamDescriptor(
                name=p.name,
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                has_default=_has_default(idx),
                annotation_normalized=(AnnotationNormalizer.normalize(ann) if ann is not None else None),
            )
        )

    # VAR_POSITIONAL (*args)
    if args.vararg_node is not None:
        descriptors.append(
            ParamDescriptor(
                name=args.vararg_node.name,
                kind=inspect.Parameter.VAR_POSITIONAL,
                has_default=False,
                annotation_normalized=(
                    AnnotationNormalizer.normalize(args.varargannotation) if args.varargannotation is not None else None
                ),
            )
        )

    # Keyword-only parameters
    n_kwonly = len(args.kwonlyargs)
    for i, p in enumerate(args.kwonlyargs):
        ann = (args.kwonlyargs_annotations or [None] * n_kwonly)[i]
        kwd = (args.kw_defaults or [None] * n_kwonly)[i]
        descriptors.append(
            ParamDescriptor(
                name=p.name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                has_default=kwd is not None,
                annotation_normalized=(AnnotationNormalizer.normalize(ann) if ann is not None else None),
            )
        )

    # VAR_KEYWORD (**kwargs)
    if args.kwarg_node is not None:
        descriptors.append(
            ParamDescriptor(
                name=args.kwarg_node.name,
                kind=inspect.Parameter.VAR_KEYWORD,
                has_default=False,
                annotation_normalized=(
                    AnnotationNormalizer.normalize(args.kwargannotation) if args.kwargannotation is not None else None
                ),
            )
        )

    # Strip self/cls if requested
    if strip_self and descriptors and descriptors[0].name in ("self", "cls"):
        descriptors = descriptors[1:]

    return descriptors


# ── Callable comparison (Invariant 3) ──────────────────────────────────────────


def _compare_callable_descriptors(
    stub_params: list[ParamDescriptor],
    impl_params: list[ParamDescriptor],
) -> str | None:
    """Compare two parameter descriptor lists, returning a detail string on
    mismatch or None if they match.

    Checks: count, name, kind, default-presence.
    """
    if len(stub_params) != len(impl_params):
        return f"param_count({len(stub_params)} vs {len(impl_params)})"

    for sp, ip in zip(stub_params, impl_params, strict=True):
        if sp.name != ip.name:
            return f"param_name({sp.name} vs {ip.name})"
        if sp.kind != ip.kind:
            return f"param_kind({sp.name}: {sp.kind.name} vs {ip.kind.name})"
        if sp.has_default != ip.has_default:
            return f"param_default({sp.name})"

    return None


def _compare_callable_annotations(
    stub_params: list[ParamDescriptor],
    impl_params: list[ParamDescriptor],
) -> list[tuple[str, str, str]]:
    """Compare parameter annotations between stub and impl descriptors.

    Returns a list of ``(param_name, stub_normalized, impl_normalized)``
    tuples for mismatches. Only reports mismatches when both sides have
    an annotation.
    """
    mismatches: list[tuple[str, str, str]] = []
    for sp, ip in zip(stub_params, impl_params, strict=True):
        if sp.annotation_normalized is not None and ip.annotation_normalized is not None:
            if sp.annotation_normalized != ip.annotation_normalized:
                mismatches.append((sp.name, sp.annotation_normalized, ip.annotation_normalized))
    return mismatches


def _compare_return_annotations(
    stub_returns: nodes.NodeNG | None,
    impl_returns: nodes.NodeNG | None,
) -> tuple[str | None, str | None]:
    """Compare return annotations.

    Returns ``(stub_normalized, impl_normalized)`` where either may be
    None if the annotation is absent or unverifiable. Both are None when
    there is nothing to compare.
    """
    if stub_returns is None or impl_returns is None:
        return (None, None)

    stub_norm = AnnotationNormalizer.normalize(stub_returns)
    impl_norm = AnnotationNormalizer.normalize(impl_returns)
    return (stub_norm, impl_norm)


def _emit_callable_fidelity_issues(ctx: CallableComparisonCtx) -> None:
    """Emit E97B3/E97B4/I97B6 for a single callable pair.

    If *impl_func* is None, the function exists only in the stub — no
    comparison can be done (handled separately by coverage logic).
    """
    if ctx.impl_func is None:
        return

    is_method = isinstance(ctx.impl_func.parent, nodes.ClassDef)
    stub_params = _extract_param_descriptors(
        ctx.stub_func.args,
        strip_self=is_method,
    )
    impl_params = _extract_param_descriptors(
        ctx.impl_func.args,
        strip_self=is_method,
    )

    # Compare param structure (count, names, kinds, defaults)
    sig_mismatch = _compare_callable_descriptors(stub_params, impl_params)
    if sig_mismatch is not None:
        log.debug(
            "Signature mismatch for '%s' in '%s': %s",
            ctx.func_name,
            ctx.module_name,
            sig_mismatch,
        )
        ctx.checker.add_message(
            "signature-mismatch",
            node=ctx.msg_node,
            args=(ctx.func_name, ctx.module_name, sig_mismatch),
        )
        return  # Don't emit annotation mismatches on structurally different signatures

    # Compare param annotations
    ann_mismatches = _compare_callable_annotations(stub_params, impl_params)
    for pname, stub_val, impl_val in ann_mismatches:
        log.debug(
            "Annotation mismatch for param '%s' in '%s.%s': stub=%s, impl=%s",
            pname,
            ctx.module_name,
            ctx.func_name,
            stub_val,
            impl_val,
        )
        ctx.checker.add_message(
            "annotation-mismatch",
            node=ctx.msg_node,
            args=(ctx.func_name, ctx.module_name, stub_val, impl_val),
        )

    # Compare return annotations
    stub_ret, impl_ret = _compare_return_annotations(
        ctx.stub_func.returns,
        ctx.impl_func.returns,
    )
    if stub_ret is not None and impl_ret is not None:
        if stub_ret == impl_ret:
            log.debug(
                "Return annotations match for '%s' in '%s': %s",
                ctx.func_name,
                ctx.module_name,
                stub_ret,
            )
        else:
            log.debug(
                "Return annotation mismatch for '%s' in '%s': stub=%s, impl=%s",
                ctx.func_name,
                ctx.module_name,
                stub_ret,
                impl_ret,
            )
            ctx.checker.add_message(
                "annotation-mismatch",
                node=ctx.msg_node,
                args=(ctx.func_name, ctx.module_name, stub_ret, impl_ret),
            )
    elif ctx.stub_func.returns is not None and ctx.impl_func.returns is not None:
        # Both have return annotations but one or both failed normalization
        log.debug(
            "Return annotation unverifiable for '%s' in '%s'",
            ctx.func_name,
            ctx.module_name,
        )
        ctx.checker.add_message(
            "annotation-unverifiable",
            node=ctx.msg_node,
            args=(ctx.func_name, ctx.module_name),
        )


# ── Class comparison helpers ───────────────────────────────────────────────────


def _normalize_bases(bases: list[nodes.NodeNG]) -> list[str]:
    """Normalize base class AST nodes to a comparable sorted list of names.

    Strips module prefix from ``Attribute`` nodes (e.g. ``pydantic.BaseModel``
    → ``BaseModel``). Treats ``builtins.object`` ≡ ``object``. For subscript
    nodes (e.g. ``Generic[T]``), extracts the base name (``Generic``).
    Sorts the result. Returns an empty list for empty bases.
    """
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
    """Check if *member_name* is a public method for class comparison.

    Includes:
    - Public methods (no leading underscore).
    - ``__init__`` and ``__new__`` (special methods with public semantics).
    Excludes:
    - Private methods (leading ``_`` but not ``__``).
    - Dunder methods other than ``__init__``/``__new__`` (e.g. ``__str__``, ``__repr__``).
    - Class-level attributes (handled separately via variable comparison).
    """
    if member_name in ("__init__", "__new__"):
        return True
    return not member_name.startswith("_")


def _is_classvar(ann_node: nodes.NodeNG) -> bool:
    """Check if *ann_node* has ``ClassVar`` as its base type.

    Detects ``ClassVar[...]`` via AST structure (Subscript with Name('ClassVar')).
    """
    return isinstance(ann_node, nodes.Subscript) and isinstance(ann_node.value, nodes.Name) and ann_node.value.name == "ClassVar"


def _compare_class_bases(ctx: ClassComparisonCtx) -> None:
    """Compare base classes between stub and impl classes.

    Emits E97B4 when normalized base lists differ.
    """
    stub_bases = _normalize_bases(ctx.stub_class.bases)
    impl_bases = _normalize_bases(ctx.impl_class.bases)
    if stub_bases != impl_bases:
        stub_str = ", ".join(stub_bases) if stub_bases else "(none)"
        impl_str = ", ".join(impl_bases) if impl_bases else "(none)"
        log.debug(
            "Base class mismatch for '%s' in '%s': stub=[%s], impl=[%s]",
            ctx.class_name,
            ctx.module_name,
            stub_str,
            impl_str,
        )
        ctx.checker.add_message(
            "annotation-mismatch",
            node=ctx.msg_node,
            args=(ctx.class_name, ctx.module_name, stub_str, impl_str),
        )


def _compare_class_methods(ctx: ClassComparisonCtx) -> None:
    """Compare public methods between stub and impl class bodies.

    Delegates to ``_emit_callable_fidelity_issues`` for each method pair.
    """
    stub_methods: dict[str, nodes.FunctionDef | nodes.AsyncFunctionDef] = {}
    impl_methods: dict[str, nodes.FunctionDef | nodes.AsyncFunctionDef] = {}
    for child in ctx.stub_class.body:
        if isinstance(child, (nodes.FunctionDef, nodes.AsyncFunctionDef)):
            if _is_public_method(child.name):
                stub_methods[child.name] = child
    for child in ctx.impl_class.body:
        if isinstance(child, (nodes.FunctionDef, nodes.AsyncFunctionDef)):
            if _is_public_method(child.name):
                impl_methods[child.name] = child

    for mname, stub_method in stub_methods.items():
        impl_method = impl_methods.get(mname)
        _emit_callable_fidelity_issues(
            CallableComparisonCtx(
                checker=ctx.checker,
                module_name=ctx.module_name,
                func_name=f"{ctx.class_name}.{mname}",
                msg_node=ctx.msg_node,
                stub_func=stub_method,
                impl_func=impl_method,
            )
        )


def _compare_class_attrs(ctx: ClassComparisonCtx) -> None:
    """Compare class-level annotated attributes between stub and impl.

    Emits W97B5, E97B4, or I97B6 for each attribute comparison.
    Skips ClassVar-annotated attributes.
    """
    stub_attrs: dict[str, nodes.AnnAssign] = {}
    impl_attrs: dict[str, tuple[nodes.NodeNG | None, nodes.AnnAssign | None]] = {}
    for child in ctx.stub_class.body:
        if isinstance(child, nodes.AnnAssign) and isinstance(child.target, nodes.AssignName):
            if child.annotation is not None and _is_classvar(child.annotation):
                log.debug(
                    "Skipping ClassVar '%s' in class '%s' in module '%s'",
                    child.target.name,
                    ctx.class_name,
                    ctx.module_name,
                )
                continue
            stub_attrs[child.target.name] = child
    for child in ctx.impl_class.body:
        if isinstance(child, nodes.AnnAssign) and isinstance(child.target, nodes.AssignName):
            impl_attrs[child.target.name] = (child.annotation, child)
        elif isinstance(child, nodes.Assign):
            for t in child.targets:
                if isinstance(t, nodes.AssignName):
                    impl_attrs[t.name] = (None, child)

    for attr_name, stub_attr_node in stub_attrs.items():
        stub_annotation = stub_attr_node.annotation
        impl_data = impl_attrs.get(attr_name, (None, None))
        impl_annotation, impl_source_node = impl_data
        attr_msg_node = impl_source_node if impl_source_node is not None else ctx.msg_node

        if stub_annotation is not None and impl_annotation is None:
            if ctx.checker._coverage.impl_missing_policy in ("error", "warn"):
                log.debug(
                    "Impl missing annotation for class attr '%s.%s' in '%s'",
                    ctx.class_name,
                    attr_name,
                    ctx.module_name,
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
                    "Normalization failed for class attr '%s.%s' in '%s'",
                    ctx.class_name,
                    attr_name,
                    ctx.module_name,
                )
                ctx.checker.add_message(
                    "annotation-unverifiable",
                    node=attr_msg_node,
                    args=(f"{ctx.class_name}.{attr_name}", ctx.module_name),
                )
            elif stub_norm != impl_norm:
                log.debug(
                    "Annotation mismatch for class attr '%s.%s' in '%s': stub=%s, impl=%s",
                    ctx.class_name,
                    attr_name,
                    ctx.module_name,
                    stub_norm,
                    impl_norm,
                )
                ctx.checker.add_message(
                    "annotation-mismatch",
                    node=attr_msg_node,
                    args=(f"{ctx.class_name}.{attr_name}", ctx.module_name, stub_norm, impl_norm),
                )
            else:
                log.debug(
                    "Annotations match for class attr '%s.%s' in '%s': %s",
                    ctx.class_name,
                    attr_name,
                    ctx.module_name,
                    stub_norm,
                )


# ── Variable fidelity dispatcher ───────────────────────────────────────────────


def _emit_variable_fidelity(checker: StubChecker, module_name: str) -> None:
    """Compare variable annotations between stub and impl for *module_name*.

    Only compares variables PRESENT in both stub and impl.
    Variables absent from impl are caught by E97B1/E97B2 dispatch.
    """
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
        # Skip variables absent from impl (E97B1 handles them)
        if var_name not in impl_all:
            continue

        stub_annotation = stub_ann_node.annotation

        # Skip ClassVar-annotated attributes
        if stub_annotation is not None and _is_classvar(stub_annotation):
            log.debug(
                "Skipping ClassVar '%s' in module '%s'",
                var_name,
                module_name,
            )
            continue

        # Check if variable exists in implementation
        impl_annotation, impl_source_node = impl_vars.get(var_name, (None, None))
        msg_node = impl_source_node if impl_source_node is not None else impl_node

        if stub_annotation is not None and impl_annotation is None:
            # Stub annotates, implementation does not → W97B5
            if c.impl_missing_policy in ("error", "warn"):
                log.debug(
                    "Impl missing annotation for '%s' in '%s' (policy=%s)",
                    var_name,
                    module_name,
                    c.impl_missing_policy,
                )
                checker.add_message(
                    "impl-missing-annotation",
                    node=msg_node,
                    args=(var_name, module_name),
                )
        elif stub_annotation is not None and impl_annotation is not None:
            # Both annotated → normalize and compare
            stub_normalized = AnnotationNormalizer.normalize(stub_annotation)
            impl_normalized = AnnotationNormalizer.normalize(impl_annotation)

            if stub_normalized is None or impl_normalized is None:
                log.debug(
                    "Normalization failed for '%s' in '%s': stub=%s, impl=%s",
                    var_name,
                    module_name,
                )
                checker.add_message(
                    "annotation-unverifiable",
                    node=msg_node,
                    args=(var_name, module_name),
                )
            elif stub_normalized != impl_normalized:
                log.debug(
                    "Annotation mismatch for '%s' in '%s': stub=%s, impl=%s",
                    var_name,
                    module_name,
                    stub_normalized,
                    impl_normalized,
                )
                checker.add_message(
                    "annotation-mismatch",
                    node=msg_node,
                    args=(var_name, module_name, stub_normalized, impl_normalized),
                )
            else:
                log.debug(
                    "Annotations match for '%s' in '%s': %s",
                    var_name,
                    module_name,
                    stub_normalized,
                )


# ── Callable fidelity dispatcher ───────────────────────────────────────────────


def _emit_callable_fidelity(checker: StubChecker, module_name: str) -> None:
    """Compare callable signatures between stub and impl for *module_name*.

    Dispatches to ``_emit_callable_fidelity_issues`` for each stub callable.
    """
    f = checker._fidelity
    stub_callables = f.stub_callable_nodes.get(module_name, {})
    impl_callables = f.impl_callable_nodes.get(module_name, {})
    module_entry = checker._coverage.module_index.get(module_name, (None, None))
    impl_node = module_entry[1]

    if not stub_callables:
        return
    if impl_node is None:
        return

    for func_name, stub_func in stub_callables.items():
        impl_func = impl_callables.get(func_name)
        _emit_callable_fidelity_issues(
            CallableComparisonCtx(
                checker=checker,
                module_name=module_name,
                func_name=func_name,
                msg_node=impl_node,
                stub_func=stub_func,
                impl_func=impl_func,
            )
        )


# ── Stub symbol check (E97B1/E97B2) ────────────────────────────────────────────


def _emit_stub_symbol_check(checker: StubChecker, module_name: str) -> None:
    """Emit E97B1/E97B2 and class comparison for all stub symbols.

    E97B1: symbol declared in stub but absent from implementation.
    E97B2: symbol exists in both but with different kind (class vs function vs var).
    """
    f = checker._fidelity
    c = checker._coverage
    impl_all = f.impl_all_names.get(module_name, set())
    stub_vars = f.stub_variable_nodes.get(module_name, {})
    stub_callables = f.stub_callable_nodes.get(module_name, {})
    stub_classes = f.stub_class_nodes.get(module_name, {})

    impl_node = c.module_index.get(module_name, (None, None))[1]
    if impl_node is None:
        return

    # Build a set of all stub symbols with their kinds
    stub_kinds: dict[str, str] = {}
    for vname in stub_vars:
        stub_kinds[vname] = "variable"
    for fname in stub_callables:
        stub_kinds[fname] = "callable"
    for cname in stub_classes:
        stub_kinds[cname] = "class"

    # Build impl kinds
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

    for sym_name, stub_kind in stub_kinds.items():
        if sym_name not in impl_all:
            # E97B1: stub symbol missing from impl
            log.debug(
                "Stub symbol '%s' in module '%s' has no implementation",
                sym_name,
                module_name,
            )
            checker.add_message(
                "stub-symbol-missing",
                node=impl_node,
                args=(sym_name, module_name),
            )
        else:
            impl_kind = impl_kinds.get(sym_name, "unknown")
            if stub_kind != impl_kind:
                # E97B2: kind mismatch
                log.debug(
                    "Kind mismatch for '%s' in '%s': stub=%s, impl=%s",
                    sym_name,
                    module_name,
                    stub_kind,
                    impl_kind,
                )
                checker.add_message(
                    "symbol-kind-mismatch",
                    node=impl_node,
                    args=(sym_name, module_name, stub_kind, impl_kind),
                )

    # Delegate class comparison for matched classes
    for cname, stub_class in stub_classes.items():
        impl_class = f.impl_class_nodes.get(module_name, {}).get(cname)
        if impl_class is None:
            # Already handled by E97B1
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


# ── Public API ─────────────────────────────────────────────────────────────────


def emit_fidelity_violations(checker: StubChecker) -> None:
    """Emit all Phase 3 violations for every module in *stub_index*.

    Calls ``_emit_stub_symbol_check``, ``_emit_variable_fidelity``,
    and ``_emit_callable_fidelity`` for each module.
    """
    for module_name in checker._coverage.stub_index:
        _emit_stub_symbol_check(checker, module_name)
        _emit_variable_fidelity(checker, module_name)
        _emit_callable_fidelity(checker, module_name)