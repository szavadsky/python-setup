from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes
from beartype import beartype
from pylint.checkers import BaseChecker

from python_setup_lint.checkers._base import MessageDef, _get_except_str, _msgs

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class SilentExceptChecker(BaseChecker):

    name: str = "silent-except"
    msgs = _msgs(
        W9740=MessageDef(
            message="Silent except handler: catches %s without logging or re-raising",
            symbol="silent-except",
            description="Caught errors must be logged or re-raised (CodingRules: fail-fast, "
            "no swallowed exceptions).",
        ),
    )

    @beartype
    def visit_excepthandler(self, node: nodes.ExceptHandler) -> None:
        # Skip if the handler re-raises or logs
        if self._has_raise(node):
            return
        if self._has_log_call(node):
            return

        # Emit warning
        except_str = _get_except_str(node)
        self.add_message(
            "silent-except",
            node=node,
            args=(except_str,),
        )

    @staticmethod
    def _has_raise(node: nodes.ExceptHandler) -> bool:  # pylint: disable=W9705  # private helper; return semantics evident from type + name
        """Return True if the handler body contains any raise statement."""
        for _ in node.nodes_of_class(nodes.Raise):
            return True
        return False

    @staticmethod
    def _has_log_call(node: nodes.ExceptHandler) -> bool:  # pylint: disable=W9705  # private helper; return semantics evident from type + name
        """Return True if the handler body contains a logging call.

        Recognises ``log.*(...)``, ``logger.*(...)``, ``logging.*(...)``,
        and any attribute call whose root name contains ``log`` (case-insensitive).
        """
        for child in node.nodes_of_class(nodes.Call):
            func = child.func
            # Attribute call: obj.method(...)
            if isinstance(func, nodes.Attribute):
                # Direct name check for common patterns
                if isinstance(func.expr, nodes.Name):
                    name = func.expr.name.lower()
                    if "log" in name:
                        return True
                # logging.warning(...) — module-level access
                if isinstance(func.expr, nodes.Attribute) and isinstance(func.expr.expr, nodes.Name):
                    name = func.expr.expr.name.lower()
                    if "log" in name:
                        return True
        return False


def register(linter: PyLinter) -> None:  # pylint: disable=missing-beartype  # pylint entry point, signature fixed by pylint API; @beartype cannot resolve PyLinter forward ref
    linter.register_checker(SilentExceptChecker(linter))
