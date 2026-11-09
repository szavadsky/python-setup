"""Parametrize rows for ``AnnotationNormalizer`` tests.

Split by checker domain out of the former 1393-line ``_factories.py`` (pylint
C0302). Paired with ``tests/checkers/test_stub_normalizer.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from _pytest.mark.structures import ParameterSet

_p = pytest.param


# ── stub normalizer ──

_NORMALIZER_INFER_CASES: list[ParameterSet] = [
    _p("x: str", "str", id="infer_simple_name"),
    _p("x: list[int]", "list[int]", id="infer_builtin_list"),
    _p("x: str | None", "str | None", id="infer_native_union"),
    _p("x: 'SomeFutureType'", None, id="infer_uninferable_returns_non_null"),
]


# ── AnnotationNormalizer._apply_rewrites ──

_APPLY_REWRITES_CASES: list[ParameterSet] = [
    _p("typing.List[str]", "list[str]", id="rewrite_typing_list"),
    _p("typing.Dict[str, int]", "dict[str, int]", id="rewrite_typing_dict"),
    _p("typing.Optional[str]", "str | None", id="rewrite_typing_optional"),
    _p("typing.Union[str, int]", "str | int", id="rewrite_typing_union"),
    _p(
        "typing.Union[list[str], int]",
        "list[str] | int",
        id="rewrite_typing_union_nested_generic",
    ),
    _p(
        "collections.abc.Callable",
        "collections.abc.Callable",
        id="rewrite_no_match_passes_through",
    ),
]

_SPLIT_OUTER_COMMAS_CASES: list[ParameterSet] = [
    _p("str, int, float", ["str", "int", "float"], id="simple"),
    _p("list[str], int", ["list[str]", "int"], id="with_brackets"),
]


# ── AnnotationNormalizer._ast_string ──

_AST_STRING_CASES: list[ParameterSet] = [
    _p("x: list[str]", ["list"], "contains", id="subscript"),
    _p("x: int | str", ["int | str"], "equals", id="binary_op_union"),
    _p("x: typing.Optional[str]", ["typing.Optional"], "contains", id="attribute"),
    _p("x: tuple[int, str]", None, "not_none", id="tuple"),
    _p("x: Literal['hello']", ["hello"], "contains", id="const"),
    _p("x: dict[str, list[int]]", ["dict", "list"], "contains", id="nested_subscript"),
]
