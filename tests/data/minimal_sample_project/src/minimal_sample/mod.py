"""Module with planted violations for all custom linters.

Each section triggers exactly one checker.  The violations are intentional
and serve as integration-test targets.
"""

from __future__ import annotations

import asyncio  # noqa: F401
import logging
import tempfile
from typing import ClassVar  # noqa: F401

import httpx


# ── 1. unnamed_tuple_dict_checker ────────────────────────────────────
# Dict value is a bare tuple literal with >1 unnamed fields.

user_map: dict[str, tuple[str, int]] = {
    "alice": ("Alice", 42),
    "bob": ("Bob", 37),
}

# ── 2. generic_key_dict_checker ───────────────────────────────────────
# dict[str, X] where X is a domain type (MessageDef, Record, etc.).

from collections.abc import Mapping  # noqa: F401, E402  # import after usage for grouping

MessageDef = dict[str, str]  # type: ignore  # simplified stand-in for test purposes

rule_registry: dict[str, MessageDef] = {
    "W9701": {"message": "test", "symbol": "test"},
}


# ── 3. suppression_justification_checker ─────────────────────────────
# Suppression comment without technical justification.


# pylint: disable=some-rule
def _bare_suppression() -> None:  # noqa: unused-argument
    pass

# ── 3b. suppression_justification_checker (brush-off) ────────────────────
# Brush-off justification that should trigger W9704.


def _brushoff_suppression() -> None:  # noqa: F401  # pre-existing
    pass

# ── 3c. suppression_justification_checker (carry-from PASSING) ──────
# Legitimate "carried from external library" justification — should NOT trigger W9704.


def _carry_from_external() -> None:  # noqa: F401  # carried from external library httpx for type compatibility
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


# ── 9. structlog_checker (use-structured-logging) ─────────────────────
# Logger call with printf-style formatting (multiple args).


def log_with_printf() -> None:
    logger.info("Found %d items", 42)  # should trigger use-structured-logging


# ── 10. docstring_checker (docstring-in-impl) ──────────────────────────
# Usage docstring in .py that should be in .pyi.


def public_func_with_usage_docstring(x: int, y: int) -> int:
    """Calculate the sum of two numbers.

    Args:
        x: First number.
        y: Second number.

    Returns:
        The sum of x and y.
    """
    return x + y


# ── 11. docstring_checker (generic-return-requires-returns) ────────────
# Function with non-None return type but no Returns: clause.


def public_func_missing_returns_clause() -> int:
    """Calculate something but missing Returns clause."""
    return 42


# ── 12. docstring_checker (internal-helper-docstring-allowed) ─────────
# _-prefixed helper with a docstring (allowed but noted).


def _helper_with_docstring() -> None:
    """This internal helper has a docstring (allowed)."""
    pass


# ── 13. stub_checker (missing-module-stub-for-import) ─────────────────
# Import a project-local module that has no .pyi stub.

from .no_stub_module import NO_STUB_CONSTANT  # noqa: F401, E402  # should trigger missing-module-stub-for-import


# ── 14. stub_checker (missing-import-declaration) ─────────────────────
# Import a symbol not declared in the target's .pyi.

from .import_target import UNDECLARED_SYMBOL  # noqa: F401, E402  # should trigger missing-import-declaration


# ── 15. stub_checker (star-import-unresolvable) ──────────────────────
# Star import from a project-local module.

from .star_module import *  # noqa: F403, E402  # should trigger star-import-unresolvable


# ── 16. stub_checker (annotation-mismatch) ────────────────────────────
# Variable annotation differs between .pyi and .py.

annot_mismatch_var: int = 42  # .pyi says str → mismatch


# ── 17. stub_checker (impl-missing-annotation) ─────────────────────────
# Variable annotated in .pyi but not in .py.

impl_missing_annot_var = "hello"  # .pyi has annotation → impl-missing-annotation


# ── 18. stub_checker (annotation-unverifiable) ────────────────────────
# Annotation too complex to normalize (slice syntax in .pyi).

unverifiable_var: int = 42  # .pyi has list[1:2] → unverifiable


# ── 19. stub_checker (signature-mismatch) ──────────────────────────────
# Function signature differs between .pyi and .py.


def sig_mismatch_func(a: int) -> bool:  # .pyi has (a: int, b: str) → mismatch
    return True


# ── 20. stub_checker (symbol-kind-mismatch) ───────────────────────────
# Symbol is a class in .pyi but a function in .py.


def KindMismatch() -> None:  # .pyi has class → kind mismatch
    pass



# ── 21. duplicate-code (R0801) ──────────────────────────────────────────
# Planted duplicate with ≥10 identical lines for R0801 detection.


def _duplicate_a():
    """First half of planted duplicate for R0801 detection."""
    a = 1
    b = 2
    c = a + b
    d = c * 2
    e = d - a
    f = e // 3
    g = f + b
    h = g * a
    i = h - c
    j = i * 2
    k = j // d
    return k
