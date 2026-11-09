"""Parametrize rows and walker for class-fidelity stub checks.

Split by checker domain out of the former 1393-line ``_factories.py`` (pylint
C0302). Paired with ``tests/checkers/test_stub_checker_class.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import astroid
import pytest

from python_setup_lint.testing import _make_tc as _make_tc_factory

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.mark.structures import ParameterSet

_p = pytest.param


# ── stub_class fidelity: _normalize_bases ──

_NORMALIZE_BASES_CASES: list[ParameterSet] = [
    _p("class Foo(BaseModel): ...\n", ["BaseModel"], id="simple_name"),
    _p("class Foo(pydantic.BaseModel): ...\n", ["BaseModel"], id="attribute_base"),
    _p("class Foo(object): ...\n", ["builtins.object"], id="builtins_object"),
    _p("class Foo(B, A, C): ...\n", ["A", "B", "C"], id="multiple_bases_sorted"),
    _p("class Foo(Generic[T]): ...\n", ["Generic"], id="subscript_base"),
]

_IS_PUBLIC_METHOD_CASES: list[ParameterSet] = [
    _p("foo", True, id="plain_name"),
    _p("_helper", False, id="private_name"),
    _p("__str__", False, id="dunder_str"),
    _p("__init__", True, id="init"),
    _p("__new__", True, id="new"),
    _p("__repr__", False, id="repr"),
]


# ── stub_class: E97B1 / E97B2 ──

_STUB_SYMBOL_MISSING_CASES: list[ParameterSet] = [
    _p(
        "x: int = 1\n",
        "x: int\nclass Foo: ...\n",
        "stub-symbol-missing",
        1,
        "Foo",
        id="stub_class_missing_from_impl",
    ),
    _p(
        "x: int = 1\n",
        "x: int\ndef foo(): ...\n",
        "stub-symbol-missing",
        1,
        "foo",
        id="stub_func_missing_from_impl",
    ),
    _p(
        "x: int = 1\n",
        "x: int\ny: str\n",
        "stub-symbol-missing",
        1,
        "y",
        id="stub_var_missing_from_impl",
    ),
]

_KIND_MISMATCH_CASES: list[ParameterSet] = [
    _p(
        "Foo: int = 1\n",
        "class Foo: ...\n",
        "symbol-kind-mismatch",
        id="stub_class_impl_var",
    ),
    _p(
        "foo: int = 1\n",
        "def foo(): ...\n",
        "symbol-kind-mismatch",
        id="stub_func_impl_var",
    ),
    _p(
        "def Foo(): ...\n",
        "class Foo: ...\n",
        "symbol-kind-mismatch",
        id="stub_class_impl_func",
    ),
    _p(
        "class Foo: ...\n",
        "Foo: int\n",
        "symbol-kind-mismatch",
        id="stub_var_impl_class",
    ),
]


# ── class-fidelity end-to-end rows ──

_CLASS_FIDELITY_INTEGRATION_CASES: list[ParameterSet] = [
    _p(
        "x: int = 1\n",
        "\nx: int\nclass Foo: ...\n",
        "stub-symbol-missing",
        "E97B1",
        id="integration_stub_symbol_missing",
    ),
    _p(
        "Foo: int = 1\n",
        "class Foo: ...\n",
        "symbol-kind-mismatch",
        "E97B2",
        id="integration_kind_mismatch",
    ),
    _p(
        "\nclass Foo:\n    x: int = 1\n",
        "\nclass Foo(BaseModel):\n    x: int\n",
        "annotation-mismatch",
        "E97B4",
        id="integration_base_class_mismatch",
    ),
    _p(
        "x: str = 'hello'\n",
        "x: int\n",
        "annotation-mismatch",
        "E97B4",
        id="integration_variable_annotation_mismatch",
    ),
    _p(
        "x = 1\n",
        "x: int\n",
        "impl-missing-annotation",
        "W97B5",
        id="integration_impl_missing_annotation",
    ),
]


# ── stub_class: shared walk-with-pair helper ──


def walk_stub_checker_with_pair(
    tmp_path: Path,
    py_code: str,
    pyi_code: str,
    /,
    module_name: str = "mod_a",
) -> list[Any]:
    from python_setup_lint.checkers.stub.checker import StubChecker

    src = tmp_path / "src"
    src.mkdir()
    (src / f"{module_name}.py").write_text(py_code)
    (src / f"{module_name}.pyi").write_text(pyi_code)
    tc = _make_tc_factory(StubChecker)
    tc.linter.config.source_roots = [str(src)]
    tc.checker.open()
    module = astroid.parse(py_code, module_name=module_name)
    module.file = str(src / f"{module_name}.py")
    tc.walk(module)
    tc.checker.close()
    return tc.linter.release_messages()
