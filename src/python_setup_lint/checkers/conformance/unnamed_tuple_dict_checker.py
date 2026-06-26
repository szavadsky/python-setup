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
from pylint.lint import PyLinter  # noqa: TC002

from python_setup_lint.checkers._base import MessageDef


class UnnamedTupleDictChecker(BaseChecker):
    """AST visitor that flags dict values that should be NamedTuples."""

    name: str = "unnamed-tuple-dict"
    msgs: dict[str, MessageDef] = {
        "W9720": MessageDef(
            message="Dict value is a bare tuple literal with %d unnamed fields; "
            "use a NamedTuple or dataclass instead",
            symbol="unnamed-tuple-dict-value",
            description="Dict values that are bare tuple literals with >1 unnamed "
            "positional fields should use a NamedTuple or dataclass for clarity.",
        ),
    }

    @beartype
    def visit_annassign(self, node: nodes.AnnAssign) -> None:
        """Check annotated assignments for unnamed-tuple dict values."""
        if not self._is_str_key_dict_annotation(node.annotation):
            return
        if not isinstance(node.value, nodes.Dict):
            return
        self._check_dict(node.value)

    @beartype
    def visit_assign(self, node: nodes.Assign) -> None:
        """Check assignments with type comments for unnamed-tuple dict values."""
        if node.type_annotation is None:
            return
        if not self._is_str_key_dict_annotation(node.type_annotation):
            return
        if not isinstance(node.value, nodes.Dict):
            return
        self._check_dict(node.value)

    def _is_str_key_dict_annotation(self, ann: nodes.NodeNG | None) -> bool:
        """Check if annotation is ``dict[str, ...]`` or ``ClassVar[dict[str, ...]]``."""
        if ann is None:
            return False

        # Unwrap ClassVar[...]
        if isinstance(ann, nodes.Subscript):
            if isinstance(ann.value, nodes.Name) and ann.value.name == "ClassVar":
                if ann.slice is not None and isinstance(ann.slice, nodes.Subscript):
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
        if key_ann.name != "str":
            return False
        return True

    def _check_dict(self, dict_node: nodes.Dict) -> None:
        """Check all values in a dict literal for bare tuple values."""
        for key, value in dict_node.items:
            if key is None:
                continue  # skip splat (**dict)
            if self._is_unnamed_tuple(value):
                self.add_message(
                    "unnamed-tuple-dict-value",
                    node=value,
                    args=(len(self._get_tuple_elts(value)),),
                )

    @staticmethod
    def _is_unnamed_tuple(node: nodes.NodeNG) -> bool:
        """Check if *node* is a bare tuple literal with >1 unnamed fields."""
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
            if isinstance(elt, nodes.UnaryOp):
                if not isinstance(elt.operand, nodes.Const):
                    return False
        return True

    @staticmethod
    def _get_tuple_elts(node: nodes.Tuple) -> list:
        return node.elts


@beartype
def register(linter: PyLinter) -> None:
    linter.register_checker(UnnamedTupleDictChecker(linter))
