"""Unit and integration tests for Invariant 3 — callable fidelity.

Tests parameter descriptor extraction, callable comparison, and end-to-end
pylint runs for signature mismatch detection.

Fixture-row data lives in ``tests/checkers/_factories.py`` (free LOC).
"""
from __future__ import annotations

import inspect
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import astroid
import pytest

from python_setup_lint.checkers.stub.fidelity import (
    CallableComparisonCtx,
    ParamDescriptor,
    _compare_callable_annotations,
    _compare_callable_descriptors,
    _compare_return_annotations,
    _extract_param_descriptors,
)
from tests.checkers._factories import (
    _CALLABLE_FIDELITY_INTEGRATION_CASES,
    _COMPARE_ANNOTATION_CASES,
    _COMPARE_DESCRIPTOR_CASES,
    _COMPARE_RETURN_CASES,
    _EXTRACT_ANNOTATION_CASES,
    _EXTRACT_DEFAULT_CASES,
    _EXTRACT_PARAM_CASES,
    _EXTRACT_STRIP_SELF_CASES,
    _run_pylint,
)

pytestmark = pytest.mark.no_external_api

if TYPE_CHECKING:
    pass

PROJECT_SRC = Path(__file__).resolve().parents[3] / "src"


def _parse_func(code: str) -> Any:
    """Parse a function source string and return the function astroid node."""
    module = astroid.parse(code, module_name="test")
    return module.body[0]


def _extract(func_node: astroid.FunctionDef, *, strip_self: bool = False) -> Any:  # pylint: disable=W9728  # test helper: shorter alias for _extract_param_descriptors
    """Wrap ``_extract_param_descriptors`` for short test bodies."""
    return _extract_param_descriptors(func_node.args, strip_self=strip_self)


def _p(name: str, ann: str | None = None) -> ParamDescriptor:
    """Build a positional-or-keyword ``ParamDescriptor`` with the given ann."""
    return ParamDescriptor(
        name=name,
        kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
        has_default=False,
        annotation_normalized=ann,
    )


def _build_descs(rows: list[tuple[str, Any, bool]]) -> list[ParamDescriptor]:
    """Build a list of ``ParamDescriptor`` from a row-tuple list."""
    return [
        ParamDescriptor(
            name=r[0], kind=r[1], has_default=r[2], annotation_normalized=None
        )
        for r in rows
    ]


def _returns_from_src(return_src: str | None) -> Any:
    """Parse ``def foo() -> <return_src>: ...`` and return the returns node (or None)."""
    if return_src is None:
        return None
    module = astroid.parse(f"def foo() -> {return_src}: ...\n", module_name="test")
    return module.body[0].returns


# ── ParamDescriptor fields ────────────────────────────────────────


def test_param_descriptor_given_fields_then_constructs_correctly() -> None:
    p = ParamDescriptor(
        name="x",
        kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
        has_default=True,
        annotation_normalized="int",
    )
    assert p.name == "x"
    assert p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert p.has_default is True
    assert p.annotation_normalized == "int"


def test_param_descriptor_given_no_annotation_then_annotation_is_none() -> None:
    p = ParamDescriptor(
        name="y",
        kind=inspect.Parameter.KEYWORD_ONLY,
        has_default=False,
        annotation_normalized=None,
    )
    assert p.annotation_normalized is None


# ── _extract_param_descriptors ─────────────────────────────────────


@pytest.mark.parametrize(
    ("func_src", "expected_names", "expected_kinds"), _EXTRACT_PARAM_CASES
)
def test_extract_param_descriptors_given_callable_then_returns_descriptors(
    func_src: str,
    expected_names: list[str],
    expected_kinds: list[Any],
) -> None:
    """Each row exercises a distinct parameter-kind classification path."""
    descs = _extract(_parse_func(func_src))
    assert [d.name for d in descs] == expected_names
    assert [d.kind for d in descs] == expected_kinds


@pytest.mark.parametrize(
    ("func_src", "expected_per_param_defaults"),
    _EXTRACT_DEFAULT_CASES,
)
def test_extract_param_descriptors_given_default_param_then_detects_default_presence(
    func_src: str,
    expected_per_param_defaults: list[bool],
) -> None:
    descs = _extract(_parse_func(func_src))
    assert [d.has_default for d in descs] == expected_per_param_defaults


@pytest.mark.parametrize(
    ("func_src", "strip_self", "expected_names"),
    _EXTRACT_STRIP_SELF_CASES,
)
def test_extract_param_descriptors_given_method_then_strips_self(
    func_src: str,
    strip_self: bool,
    expected_names: list[str],
) -> None:
    descs = _extract(_parse_func(func_src), strip_self=strip_self)
    assert [d.name for d in descs] == expected_names


@pytest.mark.parametrize(
    ("func_src", "needle_in_first", "_needle_in_second"),
    _EXTRACT_ANNOTATION_CASES,
)
def test_extract_annotations_given_callable_then_returns_annotations(
    func_src: str,
    needle_in_first: str | None,
    _needle_in_second: str | None,
) -> None:
    """Each row exercises annotation extraction — asserts substring presence."""
    descs = _extract(_parse_func(func_src))
    assert needle_in_first in descs[0].annotation_normalized


# ── _compare_callable_descriptors ─────────────────────────────────


@pytest.mark.parametrize(
    ("a_rows", "b_rows", "expected_failure"),
    _COMPARE_DESCRIPTOR_CASES,
)
def test_compare_callable_descriptors(
    a_rows: list[tuple[str, Any, bool]],
    b_rows: list[tuple[str, Any, bool]],
    expected_failure: str | None,
) -> None:
    """Each row exercises a distinct mismatch kind (count/name/kind/default)."""
    a = _build_descs(a_rows)
    b = _build_descs(b_rows)
    result = _compare_callable_descriptors(a, b)
    if expected_failure is None:
        assert result is None
    else:
        assert expected_failure in result, (  # type: ignore[operator]  # result is Any from test fixture; in-check works at runtime
            f"result={result!r} (expected substring {expected_failure!r})"
        )


# ── _compare_callable_annotations ──────────────────────────────────


@pytest.mark.parametrize(
    ("a_anns", "b_anns", "expected_count", "expected_first_arg_name"),
    _COMPARE_ANNOTATION_CASES,
)
def test_compare_callable_annotations(
    a_anns: list[str | None],
    b_anns: list[str | None],
    expected_count: int,
    expected_first_arg_name: str | None,
) -> None:
    a = [_p(name, ann) for name, ann in zip(["x", "y", "x"], a_anns, strict=False)]
    b = [_p(name, ann) for name, ann in zip(["x", "y", "x"], b_anns, strict=False)]
    result = _compare_callable_annotations(a, b)
    assert len(result) == expected_count, (
        f"a={a_anns!r} b={b_anns!r} → {len(result)} mismatches (expected {expected_count})"
    )
    if expected_first_arg_name is not None and result:
        assert result[0][0] == expected_first_arg_name


def test_compare_callable_annotations_given_empty_annotations_then_returns_empty() -> None:
    assert _compare_callable_annotations([], []) == []


# ── _compare_return_annotations ────────────────────────────────────


@pytest.mark.parametrize(
    ("stub_src", "impl_src", "assert_mode", "expected_eq"),
    _COMPARE_RETURN_CASES,
)
def test_compare_return_annotations_given_return_types_then_returns_diffs(
    stub_src: str | None,
    impl_src: str | None,
    assert_mode: str,
    expected_eq: bool,
) -> None:
    """Each row exercises a return-annotation comparison branch.

    Two modes (per row):
      - ``skip_both_none`` — when at least one input is None the comparison
        MUST return ``(None, None)`` (the skip path is taken).
      - ``compare``         — both inputs are non-None; the body asserts both
        outputs are non-None and ``stub == impl`` matches ``expected_eq``.
    """
    stub_node = _returns_from_src(stub_src)
    impl_node = _returns_from_src(impl_src)
    stub, impl = _compare_return_annotations(stub_node, impl_node)
    if assert_mode == "skip_both_none":
        assert stub is None and impl is None, f"got ({stub!r}, {impl!r})"
    elif assert_mode == "compare":
        assert stub is not None and impl is not None, f"got ({stub!r}, {impl!r})"
        assert (stub == impl) is expected_eq
    else:  # pragma: no cover - defensive
        raise AssertionError(f"unknown assert_mode {assert_mode!r}")


# ── CallableComparisonCtx fields ───────────────────────────────────


def test_callable_comparison_ctx_given_fields_then_constructs_correctly() -> None:
    stub_mod = astroid.parse("def foo(x: int) -> None: ...\n", module_name="test")
    impl_mod = astroid.parse("def foo(x: int) -> None: ...\n", module_name="test")
    stub_func = cast("astroid.FunctionDef", stub_mod.body[0])
    impl_func = cast("astroid.FunctionDef", impl_mod.body[0])
    ctx = CallableComparisonCtx(
        checker=None,  # type: ignore[arg-type]  # checker=None is valid; test creates checker-less test case
        module_name="mod_a",
        func_name="foo",
        msg_node=impl_mod,
        stub_func=stub_func,
        impl_func=impl_func,
    )


# ── end-to-end subprocess integration ─────────────────────────────


@pytest.mark.parametrize(
    ("mod_py", "mod_pyi", "enable", "expected_code"),
    _CALLABLE_FIDELITY_INTEGRATION_CASES,
)
def test_integration_callable_given_stub_and_impl_then_compares(
    tmp_path: Path,
    mod_py: str,
    mod_pyi: str,
    enable: str,
    expected_code: str,
) -> None:
    """End-to-end subprocess run: pylint surfaces the expected E97B code."""
    combined = _run_pylint(tmp_path, mod_py, mod_pyi, enable, project_src=PROJECT_SRC)
    assert expected_code in combined
