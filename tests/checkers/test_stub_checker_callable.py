"""Unit and integration tests for Invariant 3 — callable fidelity.

Tests parameter descriptor extraction, callable comparison, and end-to-end
pylint runs for signature mismatch detection.
"""

from __future__ import annotations

import inspect
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import astroid

from python_setup_lint.checkers.stub_checker import StubChecker
from python_setup_lint.checkers.stub_fidelity import (
    CallableComparisonCtx,
    ParamDescriptor,
    _compare_callable_annotations,
    _compare_callable_descriptors,
    _compare_return_annotations,
    _extract_param_descriptors,
)

if TYPE_CHECKING:
    import pytest

PROJECT_SRC = Path(__file__).resolve().parents[3] / "src"


def _parse_func(code: str):
    module = astroid.parse(code, module_name="test")
    return module.body[0]


def _extract(func_node, *, strip_self: bool = False):
    return _extract_param_descriptors(func_node.args, strip_self=strip_self)


class TestParamDescriptor:
    """ParamDescriptor fields and defaults."""

    def test_fields(self):
        p = ParamDescriptor(name="x", kind=inspect.Parameter.POSITIONAL_OR_KEYWORD, has_default=True, annotation_normalized="int")
        assert p.name == "x"
        assert p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
        assert p.has_default is True
        assert p.annotation_normalized == "int"

    def test_no_annotation(self):
        p = ParamDescriptor(name="y", kind=inspect.Parameter.KEYWORD_ONLY, has_default=False, annotation_normalized=None)
        assert p.annotation_normalized is None


class TestExtractParamDescriptors:
    """_extract_param_descriptors correctly captures all parameter kinds."""

    def test_empty_function(self):
        f = _parse_func("def foo() -> None: ...")
        assert _extract(f) == []

    def test_positional_only(self):
        f = _parse_func("def foo(a, b, /) -> None: ...")
        descs = _extract(f)
        assert len(descs) == 2
        assert descs[0].name == "a"
        assert descs[0].kind == inspect.Parameter.POSITIONAL_ONLY

    def test_positional_or_keyword(self):
        f = _parse_func("def foo(a, b) -> None: ...")
        descs = _extract(f)
        assert descs[0].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD

    def test_var_positional(self):
        f = _parse_func("def foo(*args) -> None: ...")
        descs = _extract(f)
        assert descs[0].kind == inspect.Parameter.VAR_POSITIONAL

    def test_keyword_only(self):
        f = _parse_func("def foo(*, x, y) -> None: ...")
        descs = _extract(f)
        assert descs[0].kind == inspect.Parameter.KEYWORD_ONLY

    def test_var_keyword(self):
        f = _parse_func("def foo(**kwargs) -> None: ...")
        descs = _extract(f)
        assert descs[0].kind == inspect.Parameter.VAR_KEYWORD

    def test_default_presence_detected(self):
        f = _parse_func("def foo(a, b=1) -> None: ...")
        descs = _extract(f)
        assert descs[0].has_default is False
        assert descs[1].has_default is True

    def test_default_presence_kwonly(self):
        f = _parse_func("def foo(*, x, y='hello') -> None: ...")
        descs = _extract(f)
        assert descs[0].has_default is False
        assert descs[1].has_default is True

    def test_strip_self(self):
        f = _parse_func("def bar(self, x, y) -> None: ...")
        descs = _extract(f, strip_self=True)
        assert len(descs) == 2
        assert descs[0].name == "x"

    def test_strip_cls(self):
        f = _parse_func("def bar(cls, x, y) -> None: ...")
        descs = _extract(f, strip_self=True)
        assert len(descs) == 2
        assert descs[0].name == "x"

    def test_no_strip_non_method(self):
        f = _parse_func("def bar(a, b) -> None: ...")
        descs = _extract(f, strip_self=True)
        assert len(descs) == 2
        assert descs[0].name == "a"

    def test_annotations_extracted(self):
        f = _parse_func("def foo(x: int, y: str | None) -> None: ...")
        descs = _extract(f)
        assert "int" in descs[0].annotation_normalized
        assert descs[1].annotation_normalized is not None

    def test_vararg_annotation(self):
        f = _parse_func("def foo(*args: int) -> None: ...")
        descs = _extract(f)
        assert "int" in descs[0].annotation_normalized

    def test_kwarg_annotation(self):
        f = _parse_func("def foo(**kwargs: str) -> None: ...")
        descs = _extract(f)
        assert "str" in descs[0].annotation_normalized


class TestCompareCallableDescriptors:
    """_compare_callable_descriptors correctly identifies mismatches."""

    def _p(self, name, kind=inspect.Parameter.POSITIONAL_OR_KEYWORD, has_default=False):
        return ParamDescriptor(name=name, kind=kind, has_default=has_default, annotation_normalized=None)

    def test_identical_params(self):
        a = [self._p("a"), self._p("b")]
        b = [self._p("a"), self._p("b")]
        assert _compare_callable_descriptors(a, b) is None

    def test_param_count_mismatch(self):
        a = [self._p("a"), self._p("b")]
        b = [self._p("a")]
        result = _compare_callable_descriptors(a, b)
        assert "param_count" in result

    def test_param_name_mismatch(self):
        a = [self._p("a")]
        b = [self._p("b")]
        result = _compare_callable_descriptors(a, b)
        assert "param_name" in result

    def test_param_kind_mismatch(self):
        a = [ParamDescriptor("x", inspect.Parameter.POSITIONAL_OR_KEYWORD, False, None)]
        b = [ParamDescriptor("x", inspect.Parameter.KEYWORD_ONLY, False, None)]
        result = _compare_callable_descriptors(a, b)
        assert "param_kind" in result

    def test_default_presence_mismatch(self):
        a = [self._p("x", has_default=True)]
        b = [self._p("x", has_default=False)]
        result = _compare_callable_descriptors(a, b)
        assert "param_default" in result

    def test_empty_lists(self):
        assert _compare_callable_descriptors([], []) is None


class TestCompareCallableAnnotations:
    """_compare_callable_annotations compares param annotations correctly."""

    def _p(self, name, ann):
        return ParamDescriptor(name=name, kind=inspect.Parameter.POSITIONAL_OR_KEYWORD, has_default=False, annotation_normalized=ann)

    def test_all_match_returns_empty(self):
        a = [self._p("x", "int"), self._p("y", "str")]
        b = [self._p("x", "int"), self._p("y", "str")]
        assert _compare_callable_annotations(a, b) == []

    def test_param_annotation_mismatch_detected(self):
        a = [self._p("x", "int"), self._p("y", "str")]
        b = [self._p("x", "int"), self._p("y", "int")]
        result = _compare_callable_annotations(a, b)
        assert len(result) == 1
        assert result[0][0] == "y"

    def test_skips_missing_annotations(self):
        a = [self._p("x", None)]
        b = [self._p("x", "int")]
        assert _compare_callable_annotations(a, b) == []

    def test_skips_no_annotation_on_both(self):
        a = [self._p("x", None)]
        b = [self._p("x", None)]
        assert _compare_callable_annotations(a, b) == []

    def test_empty_descriptors(self):
        assert _compare_callable_annotations([], []) == []


class TestCompareReturnAnnotations:
    """_compare_return_annotations compares return annotations."""

    def test_both_none(self):
        stub, impl = _compare_return_annotations(None, None)
        assert stub is None and impl is None

    def test_stub_none(self):
        module = astroid.parse("def foo() -> int: ...\n", module_name="test")
        stub, impl = _compare_return_annotations(None, module.body[0].returns)
        assert stub is None and impl is None

    def test_impl_none(self):
        module = astroid.parse("def foo() -> int: ...\n", module_name="test")
        stub, impl = _compare_return_annotations(module.body[0].returns, None)
        assert stub is None and impl is None

    def test_matching_returns(self):
        stub_mod = astroid.parse("def foo() -> int: ...\n", module_name="test")
        impl_mod = astroid.parse("def foo() -> int: ...\n", module_name="test")
        stub, impl = _compare_return_annotations(stub_mod.body[0].returns, impl_mod.body[0].returns)
        assert stub is not None and impl is not None
        assert stub == impl

    def test_mismatched_returns(self):
        stub_mod = astroid.parse("def foo() -> str: ...\n", module_name="test")
        impl_mod = astroid.parse("def foo() -> int: ...\n", module_name="test")
        stub, impl = _compare_return_annotations(stub_mod.body[0].returns, impl_mod.body[0].returns)
        assert stub != impl

    def test_normalized_typing(self):
        stub_mod = astroid.parse("def foo() -> typing.List[int]: ...\n", module_name="test")
        impl_mod = astroid.parse("def foo() -> list[int]: ...\n", module_name="test")
        stub, impl = _compare_return_annotations(stub_mod.body[0].returns, impl_mod.body[0].returns)
        assert stub == impl


class TestCallableComparisonCtx:
    """CallableComparisonCtx fields and defaults."""

    def test_fields(self):
        stub_mod = astroid.parse("def foo(x: int) -> None: ...\n", module_name="test")
        impl_mod = astroid.parse("def foo(x: int) -> None: ...\n", module_name="test")
        ctx = CallableComparisonCtx(
            checker=None,  # type: ignore[arg-type]
            module_name="mod_a",
            func_name="foo",
            msg_node=impl_mod,
            stub_func=stub_mod.body[0],
            impl_func=impl_mod.body[0],
        )
        assert ctx.module_name == "mod_a"


class TestEndToEndCallable:
    """Integration tests running pylint as subprocess."""

    def test_integration_signature_mismatch(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "__init__.pyi").write_text("")
        (src / "mod_a.py").write_text("""
def foo(x: int, y: str) -> None: ...
""")
        (src / "mod_a.pyi").write_text("""
def foo(x: int) -> None: ...
""")
        (tmp_path / "pyproject.toml").write_text(
            f"""\
[tool.pylint.MASTER]
load-plugins = "python_setup_lint.checkers.stub_checker"

[tool.pylint.stub-checker]
source-roots = ["{src}"]
"""
        )
        result = subprocess.run(
            [sys.executable, "-m", "pylint", str(src), "--disable=all", "--enable=signature-mismatch"],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env={**__import__("os").environ, "PYTHONPATH": str(PROJECT_SRC)},
        )
        combined = result.stdout + result.stderr
        assert "E97B3" in combined

    def test_integration_return_annotation_mismatch(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "__init__.pyi").write_text("")
        (src / "mod_a.py").write_text("""
def foo() -> int: ...
""")
        (src / "mod_a.pyi").write_text("""
def foo() -> str: ...
""")
        (tmp_path / "pyproject.toml").write_text(
            f"""\
[tool.pylint.MASTER]
load-plugins = "python_setup_lint.checkers.stub_checker"

[tool.pylint.stub-checker]
source-roots = ["{src}"]
"""
        )
        result = subprocess.run(
            [sys.executable, "-m", "pylint", str(src), "--disable=all", "--enable=annotation-mismatch"],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env={**__import__("os").environ, "PYTHONPATH": str(PROJECT_SRC)},
        )
        combined = result.stdout + result.stderr
        assert "E97B4" in combined