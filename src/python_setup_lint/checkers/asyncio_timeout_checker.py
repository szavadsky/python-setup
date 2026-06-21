"""Pylint checker: require asyncio.timeout() / anyio.fail_after() wrapping.

Reports W9703 for ``await`` calls on ``httpx.AsyncClient.*`` (or other
registered external async-call functions) that are NOT enclosed in an
``async with asyncio.timeout(...):`` or ``async with anyio.fail_after(...):``
block.

Per CodingRules External Call Requirements:
    "Timeout via asyncio.timeout(). Separate connect/read. Configurable,
     documented in .pyi. Neither None nor 0 in production."
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes
from pylint.checkers import BaseChecker

if TYPE_CHECKING:
    from pylint.lint import PyLinter

_HTTP_METHODS: frozenset[str] = frozenset({
    "get", "post", "put", "patch", "delete", "request", "stream", "send",
})

_KNOWN_TIMEOUT_FUNCS: frozenset[str] = frozenset({
    "asyncio.timeout",
    "anyio.fail_after",
    "anyio.move_on_after",
})


class AsyncTimeoutChecker(BaseChecker):
    """AST visitor that flags await calls missing enclosing timeout context."""

    name = "asyncio-timeout"
    msgs = {
        "W9703": (
            "External async call '%s' without enclosing asyncio.timeout() / anyio.fail_after()",
            "asyncio-timeout",
            "External async calls must be wrapped in asyncio.timeout() or anyio.fail_after().",
        ),
    }

    def visit_await(self, node: nodes.Await) -> None:
        if not isinstance(node.value, nodes.Call):
            return
        call = node.value
        client_name = self._resolve_client_name(call)
        if client_name is None:
            return
        if self._has_enclosing_timeout(node):
            return
        self.add_message("asyncio-timeout", node=node, args=(client_name,))

    @staticmethod
    def _resolve_client_name(call: nodes.Call) -> str | None:
        """Return a human-readable call name if this is an HTTP-method call.

        Matches patterns like ``client.get(...)``, ``client.post(...)``
        where the method is a known HTTP verb.  This is intentionally
        broad (any variable name) to catch httpx, aiohttp, and similar
        async HTTP clients without hardcoding import paths.
        """
        func = call.func
        if isinstance(func, nodes.Attribute):
            method_name = func.attrname
            if method_name in _HTTP_METHODS and isinstance(func.expr, nodes.Name):
                return f"{func.expr.name}.{method_name}"
        return None

    @staticmethod
    def _has_enclosing_timeout(node: nodes.Await) -> bool:
        """Walk up the AST to find an enclosing ``AsyncWith`` with a timeout expression.

        Continues past non-timeout ``AsyncWith`` blocks (e.g. ``async with
        httpx.AsyncClient()``) to find an outer timeout wrapper.
        """
        parent = node.parent
        while parent is not None:
            if isinstance(parent, nodes.AsyncWith):
                for expr, _ in parent.items:
                    if AsyncTimeoutChecker._is_timeout_call(expr):
                        return True
                # Don't stop here — keep walking up past non-timeout AsyncWith
            if isinstance(parent, (nodes.FunctionDef, nodes.AsyncFunctionDef, nodes.Module)):
                return False
            parent = parent.parent
        return False

    @staticmethod
    def _is_timeout_call(expr: nodes.NodeNG | None) -> bool:
        """Check if *expr* is a call to ``asyncio.timeout(...)`` or ``anyio.fail_after(...)``."""
        if not isinstance(expr, nodes.Call):
            return False
        func = expr.func
        if isinstance(func, nodes.Attribute):
            return f"{func.expr.as_string()}.{func.attrname}" in _KNOWN_TIMEOUT_FUNCS
        if isinstance(func, nodes.Name):
            return func.name in {"timeout", "fail_after", "move_on_after"}
        return False


def register(linter: PyLinter) -> None:
    linter.register_checker(AsyncTimeoutChecker(linter))
