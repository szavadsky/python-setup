"""Two-phase annotation normalizer for stub-vs-impl comparison.

Phase 1: Astroid ``infer()`` — resolved type string (~94% hit rate).
Phase 2: AST-string walking + rewrite rules — fallback for Uninferable (~6%).
"""

from __future__ import annotations

import re
from collections.abc import Callable  # noqa: TC003
from typing import TYPE_CHECKING

import astroid
from astroid import bases, nodes
from beartype import beartype

if TYPE_CHECKING:
    from astroid.typing import SuccessfulInferenceResult

# Rewrite-rule table: old-style typing -> native syntax

## These are forward-looking infrastructure; the current codebase uses

## native syntax exclusively (per T3a spike report)

_REWRITE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^typing\.List\[(.+)\]$"), r"list[\1]"),
    (re.compile(r"^typing\.Dict\[(.+),\s*(.+)\]$"), r"dict[\1, \2]"),
    (re.compile(r"^typing\.Optional\[(.+)\]$"), r"\1 | None"),
]

## Union rewrite is handled separately (comma-splitting + rejoin with ` | `)

_UNION_RE = re.compile(r"^typing\.Union\[(.+)\]$")

class AnnotationNormalizer:
    """Two-phase annotation normalizer for stub-vs-impl comparison.

    Phase 1: Astroid ``infer()`` — resolved type string (~94% hit rate).
    Phase 2: AST-string walking + rewrite rules — fallback for Uninferable (~6%).

    Returns:
        The normalized annotation string, or ``None`` if the annotation cannot be
        normalized.
    """

    @staticmethod
    @beartype
    def normalize(ann_node: nodes.NodeNG | None) -> str | None:
        if ann_node is None:
            return None

        # Phase 1: try infer()
        result = AnnotationNormalizer._infer_phase(ann_node)
        if result is not None:
            return result

        # Phase 2: AST-string walking + rewrite rules
        raw = AnnotationNormalizer._ast_string(ann_node)
        if raw is None:
            return None
        return AnnotationNormalizer._apply_rewrites(raw)

    @staticmethod
    def _infer_phase(ann_node: nodes.NodeNG) -> str | None:
        try:
            inferred = ann_node.infer()
            results = list(inferred)
        except astroid.InferenceError:
            return None

        if not results:
            return None
        if any(r is astroid.Uninferable for r in results):
            return None

        result = results[0]
        if isinstance(result, nodes.ClassDef):
            # Only accept inference when the original node is a bare Name.
            # If it's a Subscript (e.g. ``list[int]``) the inference resolves
            # to the base ClassDef (``list``) and drops the type parameters,
            # causing false matches between ``list[int]`` and ``list[str]``.
            if isinstance(ann_node, nodes.Name):
                return result.name
            return None
        # For non-ClassDef results (UnionType, Const, etc) the str() form
        # is unreliable — fall through to Phase 2 (AST-string walking).
        return None

    # -- AST-string dispatch ---------------------------------------------------

    _AST_STRING_DISPATCH: dict[
        type, Callable[[SuccessfulInferenceResult], str | None]
    ] = {}

    @staticmethod
    def _ast_string(node: SuccessfulInferenceResult) -> str | None:
        # Const is a subclass of Proxy in astroid, so check it first.
        if isinstance(node, nodes.Const):
            return repr(node.value)
        # Try the dispatch table for known NodeNG subclasses.
        handler = AnnotationNormalizer._AST_STRING_DISPATCH.get(type(node))
        if handler is not None:
            return handler(node)
        # Proxy is not a NodeNG; extract the proxied node and recurse.
        # NOTE: This check must come AFTER all specific node type checks
        # because Tuple, List, Dict, Set, and Const all inherit from Proxy.
        if isinstance(node, bases.Proxy):
            return AnnotationNormalizer._ast_string(node._proxied)
        return None

    @staticmethod
    def _string_name(node: SuccessfulInferenceResult) -> str | None:
        if not isinstance(node, nodes.Name):
            return None
        return node.name

    @staticmethod
    def _string_subscript(node: SuccessfulInferenceResult) -> str | None:
        if not isinstance(node, nodes.Subscript):
            return None
        value_s = AnnotationNormalizer._ast_string(node.value)
        slice_s = AnnotationNormalizer._ast_string(node.slice)
        if value_s is None or slice_s is None:
            return None
        return f"{value_s}[{slice_s}]"

    @staticmethod
    def _string_binop(node: SuccessfulInferenceResult) -> str | None:
        if not isinstance(node, nodes.BinOp) or node.op != "|":
            return None
        left_s = AnnotationNormalizer._ast_string(node.left)
        right_s = AnnotationNormalizer._ast_string(node.right)
        if left_s is None or right_s is None:
            return None
        return f"{left_s} | {right_s}"

    @staticmethod
    def _string_attribute(node: SuccessfulInferenceResult) -> str | None:
        if not isinstance(node, nodes.Attribute):
            return None
        expr_s = AnnotationNormalizer._ast_string(node.expr)
        if expr_s is None:
            return None
        return f"{expr_s}.{node.attrname}"

    @staticmethod
    def _string_tuple(node: SuccessfulInferenceResult) -> str | None:
        if not isinstance(node, nodes.Tuple):
            return None
        elts: list[str] = []
        for e in node.elts:
            s = AnnotationNormalizer._ast_string(e)
            if s is None:
                return None
            elts.append(s)
        return f"({', '.join(elts)})"

    @staticmethod
    def _string_list(node: SuccessfulInferenceResult) -> str | None:
        if not isinstance(node, nodes.List):
            return None
        elts: list[str] = []
        for e in node.elts:
            s = AnnotationNormalizer._ast_string(e)
            if s is None:
                return None
            elts.append(s)
        return f"[{', '.join(elts)}]"

    @staticmethod
    def _string_unaryop(node: SuccessfulInferenceResult) -> str | None:
        if not isinstance(node, nodes.UnaryOp):
            return None
        operand_s = AnnotationNormalizer._ast_string(node.operand)
        if operand_s is None:
            return None
        return f"{node.op}{operand_s}"

    @staticmethod
    def _string_starred(node: SuccessfulInferenceResult) -> str | None:
        if not isinstance(node, nodes.Starred):
            return None
        value_s = AnnotationNormalizer._ast_string(node.value)
        if value_s is None:
            return None
        return f"*{value_s}"

    @staticmethod
    def _string_dict(node: SuccessfulInferenceResult) -> str | None:
        if not isinstance(node, nodes.Dict):
            return None
        pairs: list[str] = []
        for k, v in zip(node.keys, node.values, strict=False):
            ks = AnnotationNormalizer._ast_string(k)
            vs = AnnotationNormalizer._ast_string(v)
            if ks is None or vs is None:
                return None
            pairs.append(f"{ks}: {vs}")
        return "{" + ", ".join(pairs) + "}"

    @staticmethod
    def _string_ifexp(node: SuccessfulInferenceResult) -> str | None:
        if not isinstance(node, nodes.IfExp):
            return None
        test_s = AnnotationNormalizer._ast_string(node.test)
        body_s = AnnotationNormalizer._ast_string(node.body)
        orelse_s = AnnotationNormalizer._ast_string(node.orelse)
        if test_s is None or body_s is None or orelse_s is None:
            return None
        return f"{body_s} if {test_s} else {orelse_s}"

    @staticmethod
    def _apply_rewrites(s: str) -> str:
        # First apply non-Union pattern rewrites
        for pattern, replacement in _REWRITE_PATTERNS:
            if pattern.match(s):
                return pattern.sub(replacement, s)

        # Union rewrite: split on commas not inside brackets
        union_match = _UNION_RE.match(s)
        if union_match:
            inner = union_match.group(1)
            parts = AnnotationNormalizer._split_outer_commas(inner)
            return " | ".join(parts)

        return s

    @staticmethod
    def _split_outer_commas(s: str) -> list[str]:
        parts: list[str] = []
        depth = 0
        current: list[str] = []
        for ch in s:
            if ch in ("[", "<"):
                depth += 1
                current.append(ch)
            elif ch in ("]", ">"):
                depth -= 1
                current.append(ch)
            elif ch == "," and depth == 0:
                parts.append("".join(current).strip())
                current = []
            else:
                current.append(ch)
        last = "".join(current).strip()
        if last:
            parts.append(last)
        return parts


# Build the dispatch table after the class body so all handlers exist.
AnnotationNormalizer._AST_STRING_DISPATCH.update({
    nodes.Name: AnnotationNormalizer._string_name,
    nodes.Subscript: AnnotationNormalizer._string_subscript,
    nodes.BinOp: AnnotationNormalizer._string_binop,
    nodes.Attribute: AnnotationNormalizer._string_attribute,
    nodes.Tuple: AnnotationNormalizer._string_tuple,
    nodes.List: AnnotationNormalizer._string_list,
    nodes.UnaryOp: AnnotationNormalizer._string_unaryop,
    nodes.Starred: AnnotationNormalizer._string_starred,
    nodes.Dict: AnnotationNormalizer._string_dict,
    nodes.IfExp: AnnotationNormalizer._string_ifexp,
})
