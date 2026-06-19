"""Unit tests for python_setup_lint.checkers.stub_normalizer — AnnotationNormalizer.

Two-phase normalization: infer() → AST-string walking fallback.
Exercises Phase 1 (inference), Phase 2 (AST walking), and rewrite rules.
"""

from __future__ import annotations

import astroid
import pytest

from python_setup_lint.checkers.stub_normalizer import AnnotationNormalizer

from tests.checkers._factories import (
    _APPLY_REWRITES_CASES,
    _AST_STRING_CASES,
    _NORMALIZER_INFER_CASES,
    _SPLIT_OUTER_COMMAS_CASES,
)


# ── infer() phase ──────────────────────────────────────────────────


@pytest.mark.parametrize("code, expected", _NORMALIZER_INFER_CASES)
def test_normalize_infer(code: str, expected: str | None) -> None:
    """Phase-1 ``AnnotationNormalizer.normalize`` returns the expected string.

    For the uninferable forward-ref row ``expected is None`` selects the
    postcondition: assertion is ``result is not None`` (inference succeeds).
    Otherwise plain equality against ``expected``.
    """
    module = astroid.parse(code, module_name="test_mod")
    ann = module.body[0].annotation
    result = AnnotationNormalizer.normalize(ann)
    if expected is None:
        assert result is not None, f"inference of {code!r} should not return None"
    else:
        assert result == expected, f"normalize({code!r}) = {result!r} (expected {expected!r})"


# ── AST-string walking (Phase 2) ────────────────────────────────────


def _ann_from_code(code: str):
    """Parse ``x: <ann>`` and return the annotation node of body[0]."""
    module = astroid.parse(code, module_name="test_mod")
    return module.body[0].annotation


@pytest.mark.parametrize("code, expected, assert_mode", _AST_STRING_CASES)
def test_ast_string(code: str, expected: list[str] | None, assert_mode: str) -> None:
    """Phase-2 ``AnnotationNormalizer._ast_string`` walks and stringifies the node.

    Three modes (per row):
      - ``not_none``  — assert ``result is not None`` (no equality check).
      - ``equals``    — assert ``result == expected[0]`` (exact string match).
      - ``contains``  — assert every substring in ``expected`` is in ``result``.
    """
    result = AnnotationNormalizer._ast_string(_ann_from_code(code))
    if assert_mode == "not_none":
        assert result is not None, f"_ast_string({code!r}) returned None"
    elif assert_mode == "equals":
        assert result == expected[0], f"_ast_string({code!r}) = {result!r} (expected {expected[0]!r})"
    elif assert_mode == "contains":
        assert result is not None, f"_ast_string({code!r}) returned None"
        for needle in expected or []:
            assert needle in result, f"substring {needle!r} missing from {result!r}"
    else:  # pragma: no cover - defensive
        raise AssertionError(f"unknown assert_mode {assert_mode!r}")


# ── _apply_rewrites rewrite rules ──────────────────────────────────


@pytest.mark.parametrize("input_str, expected", _APPLY_REWRITES_CASES)
def test_apply_rewrites(input_str: str, expected: str) -> None:
    assert AnnotationNormalizer._apply_rewrites(input_str) == expected


# ── _split_outer_commas ────────────────────────────────────────────


@pytest.mark.parametrize("input_str, expected_parts", _SPLIT_OUTER_COMMAS_CASES)
def test_split_outer_commas(input_str: str, expected_parts: list[str]) -> None:
    parts = AnnotationNormalizer._split_outer_commas(input_str)
    assert parts == expected_parts