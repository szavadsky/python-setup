"""Unit and integration tests for Invariant 3 — class fidelity + E97B1/E97B2 dispatch.

Tests class base comparison, public method delegation, class attribute comparison,
ClassVar skip in class bodies, E97B1 (stub symbol missing from impl), and
E97B2 (kind mismatch).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import astroid

from python_setup_lint.checkers.stub_checker import StubChecker
from python_setup_lint.checkers.stub_fidelity import (
    ClassComparisonCtx,
    _is_public_method,
    _normalize_bases,
)
from python_setup_lint.testing import _make_tc as _make_tc_factory

_make_tc = lambda: _make_tc_factory(StubChecker)

PROJECT_SRC = Path(__file__).resolve().parents[3] / "src"


class TestNormalizeBases:
    """_normalize_bases correctly normalizes base class AST nodes."""

    def test_empty_bases(self):
        assert _normalize_bases([]) == []

    def test_simple_name(self):
        module = astroid.parse("class Foo(BaseModel): ...\n", module_name="test")
        result = _normalize_bases(module.body[0].bases)
        assert result == ["BaseModel"]

    def test_attribute_base(self):
        module = astroid.parse("class Foo(pydantic.BaseModel): ...\n", module_name="test")
        result = _normalize_bases(module.body[0].bases)
        assert result == ["BaseModel"]

    def test_builtins_object(self):
        module = astroid.parse("class Foo(object): ...\n", module_name="test")
        result = _normalize_bases(module.body[0].bases)
        assert "builtins.object" in result

    def test_multiple_bases_sorted(self):
        module = astroid.parse("class Foo(B, A, C): ...\n", module_name="test")
        result = _normalize_bases(module.body[0].bases)
        assert result == ["A", "B", "C"]

    def test_subscript_base(self):
        module = astroid.parse("class Foo(Generic[T]): ...\n", module_name="test")
        result = _normalize_bases(module.body[0].bases)
        assert result == ["Generic"]


class TestIsPublicMethod:
    """_is_public_method correctly identifies public methods."""

    def test_plain_name(self):
        assert _is_public_method("foo") is True

    def test_private_name(self):
        assert _is_public_method("_helper") is False

    def test_dunder_str(self):
        assert _is_public_method("__str__") is False

    def test_init(self):
        assert _is_public_method("__init__") is True

    def test_new(self):
        assert _is_public_method("__new__") is True

    def test_repr(self):
        assert _is_public_method("__repr__") is False


class TestClassComparisonCtx:
    """ClassComparisonCtx fields and defaults."""

    def test_fields(self):
        stub_mod = astroid.parse("class Foo: ...\n", module_name="test")
        impl_mod = astroid.parse("class Foo: ...\n", module_name="test")
        ctx = ClassComparisonCtx(
            checker=None,  # type: ignore[arg-type]
            module_name="mod_a",
            class_name="Foo",
            msg_node=impl_mod,
            stub_class=stub_mod.body[0],
            impl_class=impl_mod.body[0],
        )
        assert ctx.module_name == "mod_a"
        assert ctx.class_name == "Foo"


class TestStubSymbolMissing:
    """E97B1 fires when stub symbol is absent from implementation."""

    def _run_stub_checker(self, tmp_path: Path, py_code: str, pyi_code: str, module_name: str = "mod_a"):
        src = tmp_path / "src"
        src.mkdir()
        (src / f"{module_name}.py").write_text(py_code)
        (src / f"{module_name}.pyi").write_text(pyi_code)
        tc = _make_tc()
        tc.linter.config.source_roots = [str(src)]
        tc.checker.open()
        module = astroid.parse(py_code, module_name=module_name)
        module.file = str(src / f"{module_name}.py")
        tc.walk(module)
        tc.checker.close()
        return tc.linter.release_messages()

    def test_stub_class_missing_from_impl(self, tmp_path: Path):
        msgs = self._run_stub_checker(tmp_path, "x: int = 1\n", "x: int\nclass Foo: ...\n")
        e97b1 = [m for m in msgs if m.msg_id == "stub-symbol-missing"]
        assert len(e97b1) == 1
        assert "Foo" in e97b1[0].args[0]

    def test_stub_func_missing_from_impl(self, tmp_path: Path):
        msgs = self._run_stub_checker(tmp_path, "x: int = 1\n", "x: int\ndef foo(): ...\n")
        e97b1 = [m for m in msgs if m.msg_id == "stub-symbol-missing"]
        assert len(e97b1) == 1
        assert "foo" in e97b1[0].args[0]

    def test_stub_var_missing_from_impl(self, tmp_path: Path):
        msgs = self._run_stub_checker(tmp_path, "x: int = 1\n", "x: int\ny: str\n")
        e97b1 = [m for m in msgs if m.msg_id == "stub-symbol-missing"]
        assert len(e97b1) == 1
        assert "y" in e97b1[0].args[0]

    def test_e97b1_message_code_registered(self):
        tc = _make_tc()
        assert "E97B1" in tc.checker.msgs

    def test_e97b2_message_code_registered(self):
        tc = _make_tc()
        assert "E97B2" in tc.checker.msgs


class TestSymbolKindMismatch:
    """E97B2 fires when stub and impl kinds differ."""

    def _run_stub_checker(self, tmp_path: Path, py_code: str, pyi_code: str, module_name: str = "mod_a"):
        src = tmp_path / "src"
        src.mkdir()
        (src / f"{module_name}.py").write_text(py_code)
        (src / f"{module_name}.pyi").write_text(pyi_code)
        tc = _make_tc()
        tc.linter.config.source_roots = [str(src)]
        tc.checker.open()
        module = astroid.parse(py_code, module_name=module_name)
        module.file = str(src / f"{module_name}.py")
        tc.walk(module)
        tc.checker.close()
        return tc.linter.release_messages()

    def test_stub_class_impl_var(self, tmp_path: Path):
        msgs = self._run_stub_checker(tmp_path, "Foo: int = 1\n", "class Foo: ...\n")
        e97b2 = [m for m in msgs if m.msg_id == "symbol-kind-mismatch"]
        assert len(e97b2) == 1

    def test_stub_func_impl_var(self, tmp_path: Path):
        msgs = self._run_stub_checker(tmp_path, "foo: int = 1\n", "def foo(): ...\n")
        e97b2 = [m for m in msgs if m.msg_id == "symbol-kind-mismatch"]
        assert len(e97b2) == 1

    def test_stub_class_impl_func(self, tmp_path: Path):
        msgs = self._run_stub_checker(tmp_path, "def Foo(): ...\n", "class Foo: ...\n")
        e97b2 = [m for m in msgs if m.msg_id == "symbol-kind-mismatch"]
        assert len(e97b2) == 1

    def test_stub_var_impl_class(self, tmp_path: Path):
        msgs = self._run_stub_checker(tmp_path, "class Foo: ...\n", "Foo: int\n")
        e97b2 = [m for m in msgs if m.msg_id == "symbol-kind-mismatch"]
        assert len(e97b2) == 1


class TestEndToEndClass:
    """Integration tests running pylint as subprocess."""

    def test_integration_stub_symbol_missing(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "__init__.pyi").write_text("")
        (src / "mod_a.py").write_text("x: int = 1\n")
        (src / "mod_a.pyi").write_text("""
x: int
class Foo: ...
""")
        (tmp_path / "pyproject.toml").write_text(
            f"""\
[tool.pylint.MASTER]
load-plugins = "python_setup_lint.checkers.stub_checker"

[tool.pylint.stub-checker]
source-roots = ["{src}"]
"""
        )
        env = {**__import__("os").environ, "PYTHONPATH": str(PROJECT_SRC)}
        result = subprocess.run(
            [sys.executable, "-m", "pylint", str(src), "--disable=all", "--enable=stub-symbol-missing"],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env=env,
        )
        assert "E97B1" in (result.stdout + result.stderr)

    def test_integration_kind_mismatch(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "__init__.pyi").write_text("")
        (src / "mod_a.py").write_text("Foo: int = 1\n")
        (src / "mod_a.pyi").write_text("class Foo: ...\n")
        (tmp_path / "pyproject.toml").write_text(
            f"""\
[tool.pylint.MASTER]
load-plugins = "python_setup_lint.checkers.stub_checker"

[tool.pylint.stub-checker]
source-roots = ["{src}"]
"""
        )
        env = {**__import__("os").environ, "PYTHONPATH": str(PROJECT_SRC)}
        result = subprocess.run(
            [sys.executable, "-m", "pylint", str(src), "--disable=all", "--enable=symbol-kind-mismatch"],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env=env,
        )
        assert "E97B2" in (result.stdout + result.stderr)

    def test_integration_base_class_mismatch(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "__init__.pyi").write_text("")
        (src / "mod_a.py").write_text("""
class Foo:
    x: int = 1
""")
        (src / "mod_a.pyi").write_text("""
class Foo(BaseModel):
    x: int
""")
        (tmp_path / "pyproject.toml").write_text(
            f"""\
[tool.pylint.MASTER]
load-plugins = "python_setup_lint.checkers.stub_checker"

[tool.pylint.stub-checker]
source-roots = ["{src}"]
"""
        )
        env = {**__import__("os").environ, "PYTHONPATH": str(PROJECT_SRC)}
        result = subprocess.run(
            [sys.executable, "-m", "pylint", str(src), "--disable=all", "--enable=annotation-mismatch"],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env=env,
        )
        assert "E97B4" in (result.stdout + result.stderr)

    def test_integration_variable_annotation_mismatch(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "__init__.pyi").write_text("")
        (src / "mod_a.py").write_text("x: str = 'hello'\n")
        (src / "mod_a.pyi").write_text("x: int\n")
        (tmp_path / "pyproject.toml").write_text(
            f"""\
[tool.pylint.MASTER]
load-plugins = "python_setup_lint.checkers.stub_checker"

[tool.pylint.stub-checker]
source-roots = ["{src}"]
"""
        )
        env = {**__import__("os").environ, "PYTHONPATH": str(PROJECT_SRC)}
        result = subprocess.run(
            [sys.executable, "-m", "pylint", str(src), "--disable=all", "--enable=annotation-mismatch"],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env=env,
        )
        assert "E97B4" in (result.stdout + result.stderr)

    def test_integration_impl_missing_annotation(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "__init__.pyi").write_text("")
        (src / "mod_a.py").write_text("x = 1\n")
        (src / "mod_a.pyi").write_text("x: int\n")
        (tmp_path / "pyproject.toml").write_text(
            f"""\
[tool.pylint.MASTER]
load-plugins = "python_setup_lint.checkers.stub_checker"

[tool.pylint.stub-checker]
source-roots = ["{src}"]
"""
        )
        env = {**__import__("os").environ, "PYTHONPATH": str(PROJECT_SRC)}
        result = subprocess.run(
            [sys.executable, "-m", "pylint", str(src), "--disable=all", "--enable=impl-missing-annotation"],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env=env,
        )
        assert "W97B5" in (result.stdout + result.stderr)