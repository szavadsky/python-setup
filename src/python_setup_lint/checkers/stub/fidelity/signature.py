"""Callable fidelity comparison (Invariant 3 — the E97B3 family).

Extracts :class:`ParamDescriptor` lists from Astroid argument nodes,
compares the signature shape (count / name / kind / default presence),
compares parameter and return annotations, and emits E97B3
(``signature-mismatch``), E97B4 (``annotation-mismatch``), and I97B6
(``annotation-unverifiable``) via the checker.

Functions:

- :func:`_extract_param_descriptors` — Astroid ``Arguments`` →
  :class:`ParamDescriptor` list, all 5 parameter kinds, optional
  ``self``/``cls`` strip.
- :func:`_compare_callable_descriptors` — count/name/kind/default compare.
- :func:`_compare_callable_annotations` — returns mismatches triples.
- :func:`_compare_return_annotations` — normalizes both sides.
- :func:`_emit_callable_fidelity_issues` — emits E97B3/E97B4/I97B6 for one pair.
- :func:`_emit_callable_fidelity` — dispatches all stub callables for a module.

Topologically downstream of ``_ast_helpers``; not depended on by
``kind``.  ``annotation._compare_class_methods`` calls into this module
to delegate public-method fidelity.
"""

from __future__ import annotations

import inspect
import structlog
from typing import TYPE_CHECKING

from astroid import nodes

from python_setup_lint.checkers.stub.normalizer import AnnotationNormalizer

from ._ast_helpers import CallableComparisonCtx, ParamDescriptor

if TYPE_CHECKING:
    from python_setup_lint.checkers.stub.checker import StubChecker

log = structlog.get_logger(__name__)

__all__ = [
    "_compare_callable_annotations",
    "_compare_callable_descriptors",
    "_compare_return_annotations",
    "_emit_callable_fidelity",
    "_emit_callable_fidelity_issues",
    "_extract_param_descriptors",
]


def _extract_param_descriptors(
    args: nodes.Arguments,
    *,
    strip_self: bool = False,
) -> list[ParamDescriptor]:
    descriptors: list[ParamDescriptor] = []

    n_pos = len(args.posonlyargs or [])
    n_args = len(args.args or [])
    n_regular = n_pos + n_args
    n_defaults = len(args.defaults or [])

    def _has_default(idx: int) -> bool:
        # True if param at index *idx* (across posonlyargs + args) has a default.
        # Defaults are right-aligned in the ``defaults`` list.
        return n_defaults > 0 and idx >= n_regular - n_defaults

    # Positional-only parameters
    for i, p in enumerate(args.posonlyargs or []):
        ann = (args.posonlyargs_annotations or [None] * n_pos)[i]
        descriptors.append(
            ParamDescriptor(
                name=p.name,
                kind=inspect.Parameter.POSITIONAL_ONLY,
                has_default=_has_default(i),
                annotation_normalized=(
                    AnnotationNormalizer.normalize(ann) if ann is not None else None
                ),
            )
        )

    # Positional-or-keyword parameters
    for i, p in enumerate(args.args or []):
        idx = n_pos + i
        ann = (args.annotations or [None] * n_args)[i]
        descriptors.append(
            ParamDescriptor(
                name=p.name,
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                has_default=_has_default(idx),
                annotation_normalized=(
                    AnnotationNormalizer.normalize(ann) if ann is not None else None
                ),
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
                    AnnotationNormalizer.normalize(args.varargannotation)
                    if args.varargannotation is not None
                    else None
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
                annotation_normalized=(
                    AnnotationNormalizer.normalize(ann) if ann is not None else None
                ),
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
                    AnnotationNormalizer.normalize(args.kwargannotation)
                    if args.kwargannotation is not None
                    else None
                ),
            )
        )

    # Strip self/cls if requested
    if strip_self and descriptors and descriptors[0].name in ("self", "cls"):
        descriptors = descriptors[1:]

    return descriptors


def _compare_callable_descriptors(
    stub_params: list[ParamDescriptor],
    impl_params: list[ParamDescriptor],
) -> str | None:

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
    mismatches: list[tuple[str, str, str]] = []
    for sp, ip in zip(stub_params, impl_params, strict=True):
        if (
            sp.annotation_normalized is not None
            and ip.annotation_normalized is not None
        ):
            if sp.annotation_normalized != ip.annotation_normalized:
                mismatches.append(
                    (sp.name, sp.annotation_normalized, ip.annotation_normalized)
                )
    return mismatches


def _compare_return_annotations(
    stub_returns: nodes.NodeNG | None,
    impl_returns: nodes.NodeNG | None,
) -> tuple[str | None, str | None]:
    if stub_returns is None or impl_returns is None:
        return (None, None)

    stub_norm = AnnotationNormalizer.normalize(stub_returns)
    impl_norm = AnnotationNormalizer.normalize(impl_returns)
    return (stub_norm, impl_norm)


def _emit_callable_fidelity_issues(ctx: CallableComparisonCtx) -> None:
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
            "Signature mismatch",
            func=ctx.func_name,
            module=ctx.module_name,
            detail=sig_mismatch,
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
            "Annotation mismatch for param",
            param=pname,
            module=ctx.module_name,
            func=ctx.func_name,
            stub=stub_val,
            impl=impl_val,
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
                "Return annotations match",
                func=ctx.func_name,
                module=ctx.module_name,
                annotation=stub_ret,
            )
        else:
            log.debug(
                "Return annotation mismatch",
                func=ctx.func_name,
                module=ctx.module_name,
                stub=stub_ret,
                impl=impl_ret,
            )
            ctx.checker.add_message(
                "annotation-mismatch",
                node=ctx.msg_node,
                args=(ctx.func_name, ctx.module_name, stub_ret, impl_ret),
            )
    elif ctx.stub_func.returns is not None and ctx.impl_func.returns is not None:
        # Both have return annotations but one or both failed normalization
        log.debug(
            "Return annotation unverifiable", func=ctx.func_name, module=ctx.module_name
        )
        ctx.checker.add_message(
            "annotation-unverifiable",
            node=ctx.msg_node,
            args=(ctx.func_name, ctx.module_name),
        )


def _emit_callable_fidelity(checker: StubChecker, module_name: str) -> None:
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
