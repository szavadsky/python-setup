"""Unit tests for python_setup_lint.checkers.asyncio_timeout_checker.

Verifies the AST checker detects (and does not detect) the correct
asyncio.timeout() / anyio.fail_after() wrapping patterns.
"""

from __future__ import annotations

import pytest

from python_setup_lint.checkers.asyncio_timeout_checker import AsyncTimeoutChecker
from python_setup_lint.testing import _walk_and_release


_DETECT_CASES: list[pytest.Param] = [
    pytest.param(
        "async def f():\n    async with httpx.AsyncClient() as c:\n        resp = await c.get('https://example.com')\n",
        "c.get",
        id="bare_await_in_async_client",
    ),
    pytest.param(
        "async def f():\n    async with httpx.AsyncClient() as c:\n        resp = await c.post('https://example.com')\n",
        "c.post",
        id="post_without_timeout",
    ),
    pytest.param(
        "async def f():\n    c = httpx.AsyncClient()\n    resp = await c.get('https://example.com')\n",
        "c.get",
        id="no_async_with_at_all",
    ),
    pytest.param(
        "async def f():\n    async with httpx.AsyncClient(timeout=30) as c:\n        resp = await c.get('https://example.com')\n",
        "c.get",
        id="httpx_native_timeout_not_asyncio_timeout",
    ),
    pytest.param(
        "async def f():\n    async with asyncio.timeout(5):\n        pass\n    async with httpx.AsyncClient() as c:\n        resp = await c.get('https://example.com')\n",
        "c.get",
        id="timeout_not_enclosing_await",
    ),
]


_DO_NOT_DETECT_CASES: list[pytest.Param] = [
    pytest.param(
        "async def f():\n    async with asyncio.timeout(5):\n        async with httpx.AsyncClient() as c:\n            resp = await c.get('https://example.com')\n",
        id="asyncio_timeout_wrapping_async_client",
    ),
    pytest.param(
        "async def f():\n    async with anyio.fail_after(5):\n        async with httpx.AsyncClient() as c:\n            resp = await c.get('https://example.com')\n",
        id="anyio_fail_after_wrapping_async_client",
    ),
    pytest.param(
        "async def f():\n    async with anyio.move_on_after(5):\n        async with httpx.AsyncClient() as c:\n            resp = await c.get('https://example.com')\n",
        id="anyio_move_on_after_wrapping_async_client",
    ),
    pytest.param(
        "async def f():\n    async with asyncio.timeout(5):\n        async with httpx.AsyncClient() as c:\n            resp = await c.post('https://example.com', json={'k': 'v'})\n",
        id="post_with_asyncio_timeout",
    ),
    pytest.param(
        "async def f():\n    async with asyncio.timeout(5):\n        async with httpx.AsyncClient() as c:\n            resp = await c.request('GET', 'https://example.com')\n",
        id="request_with_asyncio_timeout",
    ),
    pytest.param(
        "async def f():\n    x = 1 + 2\n",
        id="no_await_at_all",
    ),
    pytest.param(
        "async def f():\n    result = await some_other_fn()\n",
        id="non_http_await",
    ),
    pytest.param(
        "",
        id="empty_module",
    ),
]


@pytest.mark.parametrize("code, expected_first_arg", _DETECT_CASES)
def test_detects_missing_timeout(code: str, expected_first_arg: str) -> None:
    """Checker must flag await calls missing enclosing timeout."""
    msgs = _walk_and_release(code, AsyncTimeoutChecker)
    assert len(msgs) >= 1, f"Expected ≥1 message, got 0 for:\n{code}"
    assert msgs[0].msg_id == "asyncio-timeout"
    assert msgs[0].args[0] == expected_first_arg, (
        f"Expected args[0]={expected_first_arg!r}, got {msgs[0].args[0]!r}"
    )


@pytest.mark.parametrize("code", _DO_NOT_DETECT_CASES)
def test_does_not_detect(code: str) -> None:
    """Checker must NOT flag code with proper timeout wrapping."""
    msgs = _walk_and_release(code, AsyncTimeoutChecker)
    assert len(msgs) == 0, (
        f"Expected 0 messages, got {len(msgs)} for:\n{code}\n"
        f"Messages: {[(m.msg_id, m.args) for m in msgs]}"
    )


def test_multiple_awaits_one_missing() -> None:
    """Only the await outside the timeout is flagged."""
    code = (
        "async def f():\n"
        "    async with asyncio.timeout(5):\n"
        "        async with httpx.AsyncClient() as c:\n"
        "            resp = await c.get('https://ok.com')\n"
        "    async with httpx.AsyncClient() as c2:\n"
        "        resp = await c2.get('https://bad.com')\n"
    )
    msgs = _walk_and_release(code, AsyncTimeoutChecker)
    assert len(msgs) == 1
    assert msgs[0].args[0] == "c2.get"


def test_nested_async_functions() -> None:
    """Timeout in outer function does NOT protect await in inner function."""
    code = (
        "async def inner():\n"
        "    async with httpx.AsyncClient() as c:\n"
        "        resp = await c.get('https://example.com')\n"
        "\n"
        "async def outer():\n"
        "    async with asyncio.timeout(5):\n"
        "        await inner()\n"
    )
    msgs = _walk_and_release(code, AsyncTimeoutChecker)
    assert len(msgs) == 1
    assert msgs[0].args[0] == "c.get"
