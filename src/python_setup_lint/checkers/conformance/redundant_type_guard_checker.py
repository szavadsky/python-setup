"""Pylint checker: flag isinstance guards redundant over type annotations.

If a function parameter is annotated with a type, an ``isinstance`` check
on that parameter for the same type is redundant — the type checker and
``@beartype`` already enforce it.
"""

from __future__ import annotations


from astroid import nodes
from beartype import beartype
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter  # noqa: TCH002  # TYPE_CHECKING-only import; pylint is a dev dependency

from python_setup_lint.checkers._base import MessageDef, _msgs


class RedundantTypeGuardChecker(BaseChecker):
    """AST visitor that flags isinstance guards redundant over type annotations."""

    name: str = "redundant-type-guard"
    msgs = _msgs(
        W9729=MessageDef(
            message="Redundant type guard: 'isinstance(%s, %s)' check on parameter '%s' annotated as '%s'",
            symbol="redundant-type-guard",
            description="Remove checks redundant over type annotations / @beartype. "
            "If a parameter is already typed, isinstance checks are redundant.",
        ),
    )

    @beartype
    def visit_if(self, node: nodes.If) -> None:
        # Only flag at function scope — skip class-scoped methods
        if self._has_class_ancestor(node):
            return

        # Find enclosing function
        enclosing_func = self._find_enclosing_function(node)
        if enclosing_func is None:
            return

        # Check: test must be `not isinstance(x, T)` followed by a raise
        if not self._is_not_isinstance_guard(node):
            return

        # Extract the isinstance call details
        call = node.test.operand  # type: ignore[union-attr]  # guaranteed by _is_not_isinstance_guard
        param_name = self._get_isinstance_arg_name(call)
        guard_type = self._get_isinstance_type_name(call)
        if param_name is None or guard_type is None:
            return

        # Look up the parameter annotation in the enclosing function
        ann_type = self._get_param_annotation(enclosing_func, param_name)
        if ann_type is None:
            return

        # Only flag when the annotation type name matches the isinstance check type
        if ann_type == guard_type:
            self.add_message(
                "redundant-type-guard",
                node=node,
                args=(param_name, guard_type, param_name, ann_type),
            )

    @staticmethod
    def _has_class_ancestor(node: nodes.If) -> bool:  # pylint: disable=W9705  # private helper; return semantics evident from type + name
        """Return True if *node* is nested inside a class definition."""
        parent = node.parent
        while parent is not None:
            if isinstance(parent, nodes.ClassDef):
                return True
            parent = parent.parent
        return False

    @staticmethod
    def _find_enclosing_function(node: nodes.If) -> nodes.FunctionDef | None:  # pylint: disable=W9705  # private helper; return semantics evident from type + name
        """Walk up to find the nearest enclosing FunctionDef."""
        parent = node.parent
        while parent is not None:
            if isinstance(parent, nodes.FunctionDef):
                return parent
            parent = parent.parent
        return None

    @staticmethod
    def _is_not_isinstance_guard(node: nodes.If) -> bool:  # pylint: disable=W9705  # private helper; return semantics evident from type + name
        """Return True if *node* is ``if not isinstance(x, T): raise ...``."""
        # Test must be `not <call>`
        if not isinstance(node.test, nodes.UnaryOp):
            return False
        if node.test.op != "not":
            return False
        operand = node.test.operand
        if not isinstance(operand, nodes.Call):
            return False
        # Call must be `isinstance(...)`
        if not isinstance(operand.func, nodes.Name):
            return False
        if operand.func.name != "isinstance":
            return False
        # Body must contain a raise statement
        if not node.body:
            return False
        first_stmt = node.body[0]
        if not isinstance(first_stmt, nodes.Raise):
            return False
        return True

    @staticmethod
    def _get_isinstance_arg_name(call: nodes.Call) -> str | None:  # pylint: disable=W9705  # private helper; return semantics evident from type + name
        """Extract the variable name from an isinstance call's first arg."""
        if not call.args:
            return None
        first = call.args[0]
        if isinstance(first, nodes.Name):
            return first.name
        return None

    @staticmethod
    def _get_isinstance_type_name(call: nodes.Call) -> str | None:  # pylint: disable=W9705  # private helper; return semantics evident from type + name
        """Extract the type name from an isinstance call's second arg.

        Only handles single-type checks (not tuples of types).
        """
        if len(call.args) < 2:
            return None
        second = call.args[1]
        if isinstance(second, nodes.Name):
            return second.name
        return None

    @staticmethod
    def _get_param_annotation(func: nodes.FunctionDef, param_name: str) -> str | None:  # pylint: disable=W9705  # private helper; return semantics evident from type + name
        """Return the annotation type name for *param_name* in *func*, or None."""
        for arg, ann in zip(func.args.args, func.args.annotations):
            if arg.name == param_name:
                if ann is None:
                    return None
                # Simple name annotation: `x: int`
                if isinstance(ann, nodes.Name):
                    return ann.name
                # Union annotation: `x: int | str` — not a single type match
                return None
        return None


@beartype
def register(linter: PyLinter) -> None:
    linter.register_checker(RedundantTypeGuardChecker(linter))
