"""Parametrize rows for callable-fidelity stub checks.

Split by checker domain out of the former 1393-line ``_factories.py`` (pylint
C0302). Paired with ``tests/checkers/test_stub_checker_callable.py``.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from _pytest.mark.structures import ParameterSet

_p = pytest.param


# ── stub_callable: extract param descriptors ──

_EXTRACT_PARAM_CASES: list[ParameterSet] = [
    _p("def foo() -> None: ...", [], [], id="empty_function"),
    _p(
        "def foo(a, b, /) -> None: ...",
        ["a", "b"],
        [inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_ONLY],
        id="positional_only",
    ),
    _p(
        "def foo(a, b) -> None: ...",
        ["a", "b"],
        [
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ],
        id="positional_or_keyword",
    ),
    _p(
        "def foo(*args) -> None: ...",
        ["args"],
        [inspect.Parameter.VAR_POSITIONAL],
        id="var_positional",
    ),
    _p(
        "def foo(*, x, y) -> None: ...",
        ["x", "y"],
        [inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.KEYWORD_ONLY],
        id="keyword_only",
    ),
    _p(
        "def foo(**kwargs) -> None: ...",
        ["kwargs"],
        [inspect.Parameter.VAR_KEYWORD],
        id="var_keyword",
    ),
]

_EXTRACT_DEFAULT_CASES: list[ParameterSet] = [
    _p("def foo(a, b=1) -> None: ...", [False, True], id="default_presence_detected"),
    _p(
        "def foo(*, x, y='hello') -> None: ...",
        [False, True],
        id="default_presence_kwonly",
    ),
]

_EXTRACT_STRIP_SELF_CASES: list[ParameterSet] = [
    _p("def bar(self, x, y) -> None: ...", True, ["x", "y"], id="strip_self"),
    _p("def bar(cls, x, y) -> None: ...", True, ["x", "y"], id="strip_cls"),
    _p("def bar(a, b) -> None: ...", True, ["a", "b"], id="no_strip_non_method"),
]

_EXTRACT_ANNOTATION_CASES: list[ParameterSet] = [
    _p(
        "def foo(x: int, y: str | None) -> None: ...",
        "int",
        None,
        id="annotations_extracted",
    ),
    _p("def foo(*args: int) -> None: ...", "int", None, id="vararg_annotation"),
    _p("def foo(**kwargs: str) -> None: ...", "str", None, id="kwarg_annotation"),
]


# ── stub_callable: compare descriptors ──

_COMPARE_DESCRIPTOR_CASES: list[ParameterSet] = [
    _p(
        [
            ("a", inspect.Parameter.POSITIONAL_OR_KEYWORD, False),
            ("b", inspect.Parameter.POSITIONAL_OR_KEYWORD, False),
        ],
        [
            ("a", inspect.Parameter.POSITIONAL_OR_KEYWORD, False),
            ("b", inspect.Parameter.POSITIONAL_OR_KEYWORD, False),
        ],
        None,
        id="identical_params",
    ),
    _p(
        [
            ("a", inspect.Parameter.POSITIONAL_OR_KEYWORD, False),
            ("b", inspect.Parameter.POSITIONAL_OR_KEYWORD, False),
        ],
        [("a", inspect.Parameter.POSITIONAL_OR_KEYWORD, False)],
        "param_count",
        id="param_count_mismatch",
    ),
    _p(
        [("a", inspect.Parameter.POSITIONAL_OR_KEYWORD, False)],
        [("b", inspect.Parameter.POSITIONAL_OR_KEYWORD, False)],
        "param_name",
        id="param_name_mismatch",
    ),
    _p(
        [("x", inspect.Parameter.POSITIONAL_OR_KEYWORD, False)],
        [("x", inspect.Parameter.KEYWORD_ONLY, False)],
        "param_kind",
        id="param_kind_mismatch",
    ),
    _p(
        [("x", inspect.Parameter.POSITIONAL_OR_KEYWORD, True)],
        [("x", inspect.Parameter.POSITIONAL_OR_KEYWORD, False)],
        "param_default",
        id="default_presence_mismatch",
    ),
    _p([], [], None, id="empty_lists"),
]

_COMPARE_ANNOTATION_CASES: list[ParameterSet] = [
    _p(["int", "str"], ["int", "str"], 0, None, id="all_match_returns_empty"),
    _p(["int", "str"], ["int", "int"], 1, "y", id="param_annotation_mismatch_detected"),
    _p([None], ["int"], 0, None, id="skips_missing_annotations"),
    _p([None], [None], 0, None, id="skips_no_annotation_on_both"),
]

_COMPARE_RETURN_CASES: list[ParameterSet] = [
    _p(None, None, "skip_both_none", True, id="both_none"),
    _p(None, "int", "skip_both_none", True, id="stub_none_skipped"),
    _p("int", None, "skip_both_none", True, id="impl_none_skipped"),
    _p("int", "int", "compare", True, id="matching_returns"),
    _p("str", "int", "compare", False, id="mismatched_returns"),
    _p("typing.List[int]", "list[int]", "compare", True, id="normalized_typing"),
]


_CALLABLE_FIDELITY_INTEGRATION_CASES: list[ParameterSet] = [
    _p(
        "\ndef foo(x: int, y: str) -> None: ...\n",
        "\ndef foo(x: int) -> None: ...\n",
        "signature-mismatch",
        "E97B3",
        id="signature_mismatch",
    ),
    _p(
        "\ndef foo() -> int: ...\n",
        "\ndef foo() -> str: ...\n",
        "annotation-mismatch",
        "E97B4",
        id="return_annotation_mismatch",
    ),
]
