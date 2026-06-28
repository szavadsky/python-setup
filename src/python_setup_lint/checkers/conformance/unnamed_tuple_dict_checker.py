"""Pylint checker: prohibit unnamed-tuple dict values.

Flags ``dict`` literals whose values are bare ``tuple``/``Tuple[...]``
literals with >1 unnamed positional fields, suggesting they should use
a ``NamedTuple`` or dataclass instead.

Heuristic: triggers when a dict value is a ``tuple`` literal of length >= 2
with all-str/elem-typed members AND the dict is annotated
``dict[str, tuple[...]]`` or assigned to a ``ClassVar[dict[str, ...]]``.
"""

from __future__ import annotations

from astroid import nodes
from beartype import beartype
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter  # TYPE_CHECKING-only import; pylint is a dev dependency
from pylint.typing import MessageDefinitionTuple

from python_setup_lint.checkers._base import MessageDef, _msgs


class UnnamedTupleDictChecker(BaseChecker):
    """AST visitor that flags dict values that should be NamedTuples."""

    name: str = "unnamed-tuple-dict"
    msgs: dict[str, MessageDefinitionTuple] = _msgs(
        W9720=MessageDef(
            message="Dict value is a bare tuple literal with %d unnamed fields; "
            "use a NamedTuple or dataclass instead",
            symbol="unnamed-tuple-dict-value",
            description="Dict values that are bare tuple literals with >1 unnamed "
            "positional fields should use a NamedTuple or dataclass for clarity.",
        ),
    )

    @beartype
    def visit_annassign(self, node: nodes.AnnAssign) -> None:
        # Check annotated assignments for unnamed-tuple dict values.
        if not self._is_str_key_dict_annotation(node.annotation):
            return
        if not isinstance(node.value, nodes.Dict):
            return
        self._check_dict(node.value)

    @beartype
    def visit_assign(self, node: nodes.Assign) -> None:
        # Check assignments with type comments for unnamed-tuple dict values.
        if node.type_annotation is None:
            return
        if not self._is_str_key_dict_annotation(node.type_annotation):
            return
        if not isinstance(node.value, nodes.Dict):
            return
        self._check_dict(node.value)

    def _is_str_key_dict_annotation(self, ann: nodes.NodeNG | None) -> bool:
        """Check if annotation is ``dict[str, ...]`` or ``ClassVar[dict[str, ...]]``.

        Returns:
            True if the annotation is ``dict[str, ...]`` or ``ClassVar[dict[str, ...]]``.
        """
        if ann is None:
            return False

        # Unwrap ClassVar[...]
        if isinstance(ann, nodes.Subscript) and isinstance(ann.value, nodes.Name) and ann.value.name == "ClassVar" and ann.slice is not None and isinstance(ann.slice, nodes.Subscript):
            ann = ann.slice

        if not isinstance(ann, nodes.Subscript):
            return False
        if not isinstance(ann.value, nodes.Name):
            return False
        if ann.value.name not in ("dict", "Dict"):
            return False
        if ann.slice is None or not isinstance(ann.slice, nodes.Tuple):
            return False
        elts = ann.slice.elts
        if len(elts) < 1:
            return False
        key_ann = elts[0]
        if not isinstance(key_ann, nodes.Name):
            return False
        return key_ann.name == "str"

    def _check_dict(self, dict_node: nodes.Dict) -> None:
        """Check all values in a dict literal for bare tuple values."""
        for key, value in dict_node.items:
            if key is None:
                continue  # skip splat (**dict)
            if not isinstance(value, nodes.Tuple):
                continue
            if self._is_unnamed_tuple(value):
                self.add_message(
                    "unnamed-tuple-dict-value",
                    node=value,
                    args=(len(value.elts),),
                )

    @staticmethod
    def _is_unnamed_tuple(node: nodes.NodeNG) -> bool:
        """Check if *node* is a bare tuple literal with >1 unnamed fields.

        Returns:
            True if *node* is a bare tuple literal with >1 unnamed fields.
        """
        if not isinstance(node, nodes.Tuple):
            return False
        elts = node.elts
        if len(elts) < 2:
            return False
        # All elements should be simple literals (str, int, float, Name, etc.)
        # — not nested structures or complex expressions
        for elt in elts:
            if not isinstance(elt, (nodes.Const, nodes.Name, nodes.UnaryOp)):
                return False
            if isinstance(elt, nodes.UnaryOp) and not isinstance(elt.operand, nodes.Const):
                return False
        return True

    @staticmethod
    def _get_tuple_elts(node: nodes.Tuple) -> list:
        return node.elts


def register(linter: PyLinter) -> None:  # pylint: disable=missing-beartype  # pylint entry point, signature fixed by pylint API; @beartype cannot resolve PyLinter forward ref
    linter.register_checker(UnnamedTupleDictChecker(linter))
