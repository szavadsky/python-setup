"""Parametrize rows for ``BeartypeCoverageChecker`` tests.

Split by checker domain out of the former 1393-line ``_factories.py`` (pylint
C0302). Paired with ``tests/checkers/test_beartype_checker.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from _pytest.mark.structures import ParameterSet

_p = pytest.param


# ── beartype checker ──

_BEARTYPE_MISS_CASES: list[ParameterSet] = [
    _p("def foo(): pass", 1, None, id="plain_def"),
    _p("async def foo(): pass", 1, None, id="async_def"),
    _p("class X:\n    def method(self): pass", 1, "method", id="public_method_in_class"),
    _p("def foo(): pass\ndef bar(): pass\n", 2, None, id="multiple_public_functions"),
]

_BEARTYPE_SOURCE_ROOT_CASES: list[ParameterSet] = [
    _p("def foo(): pass", "tests/test_mod.py", 0, id="outside_source_root"),
    _p("def foo(): pass", "src/prod.py", 1, id="under_source_root"),
]

_BEARTYPE_SKIP_CASES: list[ParameterSet] = [
    _p("def _helper(): pass", 0, id="private_function"),
    _p("def public(): pass\ndef _private(): pass\n", 1, id="mixed_public_and_private"),
    _p("class X:\n    def __init__(self): pass", 0, id="init_skipped"),
    _p("class X:\n    def __str__(self): pass", 0, id="str_skipped"),
    _p(
        "class X:\n    def __init__(self): pass\n    def run(self): pass",
        1,
        id="dunder_only_init_skipped_then_public",
    ),
]
