"""Module with planted violations for all custom linters.

Each section triggers exactly one checker.  The violations are intentional
and serve as integration-test targets.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from typing import ClassVar

import httpx


# ── 1. unnamed_tuple_dict_checker ────────────────────────────────────
# Dict value is a bare tuple literal with >1 unnamed fields.

user_map: dict[str, tuple[str, int]] = {
    "alice": ("Alice", 42),
    "bob": ("Bob", 37),
}

# ── 2. generic_key_dict_checker ───────────────────────────────────────
# dict[str, X] where X is a domain type (MessageDef, Record, etc.).

from collections.abc import Mapping  # noqa: E402  # import after usage for grouping

MessageDef = dict[str, str]  # type: ignore  # simplified stand-in for test purposes

rule_registry: dict[str, MessageDef] = {
    "W9701": {"message": "test", "symbol": "test"},
}


# ── 3. suppression_justification_checker ─────────────────────────────
# Suppression comment without technical justification.

# pylint: disable=some-rule
def _bare_suppression() -> None:  # noqa: unused-argument
    pass


# ── 4. beartype_checker ──────────────────────────────────────────────
# Public function missing @beartype decorator.

def public_func_missing_beartype() -> str:  # should trigger missing-beartype
    return "hello"


# ── 5. no_try_import_checker ─────────────────────────────────────────
# try/except ImportError pattern.

def try_import_guard() -> None:
    try:
        import nonexistent_module  # noqa: F401  # planted violation
    except ImportError:
        pass


# ── 6. asyncio_timeout_checker ───────────────────────────────────────
# await call on HTTP method without enclosing asyncio.timeout().

async def fetch_without_timeout() -> None:
    client = httpx.AsyncClient()
    response = await client.get("https://example.com")  # should trigger asyncio-timeout
    print(response)


# ── 7. tmp_path_checker ──────────────────────────────────────────────
# tempfile usage (mkdtemp / mkstemp / NamedTemporaryFile).

def create_temp_dir() -> str:
    return tempfile.mkdtemp()  # should trigger tempfile-mkdtemp-in-test


# ── 8. structlog_checker ─────────────────────────────────────────────
# stdlib logging instead of structlog.

logger = logging.getLogger(__name__)  # should trigger use-structlog
