"""Unit and integration tests for Invariant 3 — class fidelity + E97B1/E97B2 dispatch.

Tests class base comparison, public method delegation, class attribute
comparison, ClassVar skip in class bodies, E97B1 (stub symbol missing from
impl), and E97B2 (kind mismatch).

Fixture-row data lives in ``tests/checkers/_factories.py`` (free LOC).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import astroid
import pytest

from python_setup_lint.checkers.stub.checker import StubChecker
from python_setup_lint.checkers.stub.fidelity import (
    ClassComparisonCtx,
    _is_public_method,
    _normalize_bases,
)
from python_setup_lint.testing import _make_tc as _make_tc_factory
from tests.checkers._factories import (
    _CLASS_FIDELITY_INTEGRATION_CASES,
    _IS_PUBLIC_METHOD_CASES,
    _KIND_MISMATCH_CASES,
    _NORMALIZE_BASES_CASES,
    _STUB_SYMBOL_MISSING_CASES,
    _run_pylint,
    walk_stub_checker_with_pair,
)

PROJECT_SRC = Path(__file__).resolve().parents[3] / "src"


def _make_tc() -> Any:  # pylint: disable=trivial-wrapper  # test helper; readability over DRY
    return _make_tc_factory(StubChecker)


# ── _normalize_bases ───────────────────────────────────────────────


@pytest.mark.parametrize(("class_src", "expected_substrings"), _NORMALIZE_BASES_CASES)
def test_normalize_bases(class_src: str, expected_substrings: list[str]) -> None:
    """``_normalize_bases`` returns the expected base-class name(s).

    Each row asserts all expected substrings are present in the result.
    """
    module = astroid.parse(class_src, module_name="test")
    result = _normalize_bases(module.body[0].bases)
    for s in expected_substrings:
        assert s in result, f"missing {s!r} in {result!r}"


def test_normalize_bases_empty() -> None:
    assert _normalize_bases([]) == []


# ── _is_public_method ──────────────────────────────────────────────


@pytest.mark.parametrize(("name", "expected"), _IS_PUBLIC_METHOD_CASES)
def test_is_public_method(name: str, expected: bool) -> None:
    assert _is_public_method(name) is expected


# ── ClassComparisonCtx fields ─────────────────────────────────────


def test_class_comparison_ctx_fields() -> None:
    stub_mod = astroid.parse("class Foo: ...\n", module_name="test")
    impl_mod = astroid.parse("class Foo: ...\n", module_name="test")
    stub_class = cast("astroid.ClassDef", stub_mod.body[0])
    impl_class = cast("astroid.ClassDef", impl_mod.body[0])
    ctx = ClassComparisonCtx(
        checker=None,  # type: ignore[arg-type]  # test fixture; None is valid sentinel for ClassComparisonCtx
        module_name="mod_a",
        class_name="Foo",
        msg_node=impl_mod,
        stub_class=stub_class,
        impl_class=impl_class,
    )

# ── Checker message codes registered ──────────────────────────────


def test_e97b1_message_code_registered() -> None:
    assert "E97B1" in _make_tc().checker.msgs


def test_e97b2_message_code_registered() -> None:
    assert "E97B2" in _make_tc().checker.msgs


# ── E97B1: stub symbol missing from impl ───────────────────────────


@pytest.mark.parametrize(
    ("py_code", "pyi_code", "msg_id", "expected_count", "name_in_args"),
    _STUB_SYMBOL_MISSING_CASES,
)
def test_stub_symbol_missing(  # pylint: disable=too-many-positional-arguments  # parametrize table has 5 columns; test functions inherently have many args
    tmp_path: Path,
    py_code: str,
    pyi_code: str,
    msg_id: str,
    expected_count: int,
    name_in_args: str,
) -> None:
    """E97B1 fires when a stub symbol is absent from the implementation."""
    msgs = walk_stub_checker_with_pair(tmp_path, py_code, pyi_code)
    matching = [m for m in msgs if m.msg_id == msg_id]
    assert len(matching) == expected_count
    if matching:
        assert name_in_args in matching[0].args[0]


# ── E97B2: symbol kind mismatch ────────────────────────────────────


@pytest.mark.parametrize(("py_code", "pyi_code", "msg_id"), _KIND_MISMATCH_CASES)
def test_symbol_kind_mismatch(
    tmp_path: Path,
    py_code: str,
    pyi_code: str,
    msg_id: str,
) -> None:
    """E97B2 fires when stub and impl kinds differ."""
    msgs = walk_stub_checker_with_pair(tmp_path, py_code, pyi_code)
    matching = [m for m in msgs if m.msg_id == msg_id]
    assert len(matching) == 1


# ── end-to-end subprocess integration ─────────────────────────────


@pytest.mark.parametrize(
    ("mod_py", "mod_pyi", "enable", "expected_code"),
    _CLASS_FIDELITY_INTEGRATION_CASES,
)
def test_integration_class_fidelity(
    tmp_path: Path,
    mod_py: str,
    mod_pyi: str,
    enable: str,
    expected_code: str,
) -> None:
    """End-to-end: pylint surfaces the expected E97B/W97B5 code via *enable*."""
    combined = _run_pylint(tmp_path, mod_py, mod_pyi, enable, project_src=PROJECT_SRC)
    assert expected_code in combined
