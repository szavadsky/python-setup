"""Pylint checker: require asyncio.timeout() / anyio.fail_after() wrapping.

Reports W9703 for ``await`` calls on HTTP-method calls (``client.get()``,
``client.post()``, etc.) that are NOT enclosed in an ``async with
asyncio.timeout(...):`` or ``async with anyio.fail_after(...):`` block.

Checker logic
-------------
- Walks AST for ``Await`` nodes whose value is a ``Call`` with an HTTP-method
  attribute (``get``, ``post``, ``put``, ``patch``, ``delete``, ``request``,
  ``stream``, ``send``).
- Walks up the AST to find an enclosing ``AsyncWith`` whose expression is
  ``asyncio.timeout(...)``, ``anyio.fail_after(...)``, or
  ``anyio.move_on_after(...)``.
- Continues past non-timeout ``AsyncWith`` blocks (e.g. ``async with
  httpx.AsyncClient() as client:``) to find an outer timeout wrapper.
- Emits ``W9703`` for every flagged await.

W-level only — does not affect build exit codes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes
from pylint.checkers import BaseChecker

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class AsyncTimeoutChecker(BaseChecker):
    """AST visitor that flags await calls missing enclosing timeout context."""

    name: str = "asyncio-timeout"

    def visit_await(self, node: nodes.Await) -> None: ...


def register(linter: PyLinter) -> None: ...
