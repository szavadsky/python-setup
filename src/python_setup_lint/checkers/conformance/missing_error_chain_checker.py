"""Pylint checker: require error chaining (raise X from Y) inside except handlers.

Bare ``raise SomeException(...)`` inside an ``except`` block loses the original
traceback.  The checker flags any ``raise`` with an explicit exception that
lacks a ``from`` clause when it appears inside an ``except`` handler.
"""

from __future__ import annotations

from astroid import nodes
from beartype import beartype
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter  # TYPE_CHECKING-only import; pylint is a dev dependency

from python_setup_lint.checkers._base import MessageDef, _msgs


class MissingErrorChainChecker(BaseChecker):
    """AST visitor that flags bare raises inside except handlers."""

    name: str = "missing-error-chain"
    msgs = _msgs(
        W9739=MessageDef(
            message="Raise without cause: 'raise %s' inside 'except %s' without 'from'",
            symbol="missing-error-chain",
            description="Chain errors: raise X from Y. Bare raise inside except loses the original traceback.",
        ),
    )

    @beartype
    def visit_raise(self, node: nodes.Raise) -> None:
        # Bare `raise` (re-raise) is fine — it preserves the original exception.
        if node.exc is None:
            return

        # If there's already a `from` clause, the error is chained.
        if node.cause is not None:
            return

        # Check if we're inside an except handler.
        except_handler = self._find_enclosing_except_handler(node)
        if except_handler is None:
            return

        # Extract the type name of the caught exception for the message.
        caught_type = self._except_type_name(except_handler)

        # Extract the raised expression as a string for the message.
        raised_text = node.exc.as_string()

        self.add_message(
            "missing-error-chain",
            node=node,
            args=(raised_text, caught_type),
        )

    @staticmethod
    def _find_enclosing_except_handler(node: nodes.Raise) -> nodes.ExceptHandler | None:  # pylint: disable=W9705  # private helper; return semantics evident from type + name
        """Walk up the AST to find the nearest enclosing ``except`` handler."""
        for ancestor in node.node_ancestors():
            if isinstance(ancestor, nodes.ExceptHandler):
                return ancestor
        return None

    @staticmethod
    def _except_type_name(handler: nodes.ExceptHandler) -> str:  # pylint: disable=W9705  # private helper; return semantics evident from type + name
        """Return a human-readable name for the caught exception type."""
        if handler.type is None:
            return "bare except"
        return handler.type.as_string()


def register(linter: PyLinter) -> None:  # pylint: disable=missing-beartype  # pylint entry point, signature fixed by pylint API; @beartype cannot resolve PyLinter forward ref
    linter.register_checker(MissingErrorChainChecker(linter))
