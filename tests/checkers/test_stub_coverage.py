"""Unit tests for python_setup_lint.checkers.stub_coverage helper functions.

These exercise the private helpers directly rather than via the checker,
giving coverage for each function individually (private-complex-unit category).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import astroid
from pylint.testutils import CheckerTestCase

from python_setup_lint.checkers.stub_checker import StubChecker
from python_setup_lint.checkers.stub_coverage import (
    _has_main_block,
    _index_stub_declarations,
    _is_init_exempt,
    _is_opted_out,
    _is_test_file,
    _is_trivial_test_data,
    _is_under_source_root,
    _matches_path,
    _resolve_stub,
    emit_coverage_violations,
)

if TYPE_CHECKING:
    import pytest


def _make_checker(**config_kwargs: str | list[str]) -> StubChecker:
    """Create a StubChecker instance with optional config overrides."""
    tc = CheckerTestCase()
    tc.CHECKER_CLASS = StubChecker
    tc.setup_method()
    for key, value in config_kwargs.items():
        setattr(tc.linter.config, key, value)
    tc.checker.open()
    return tc.checker


def _parse(code: str, module_name: str = "") -> astroid.Module:
    """Parse Python source and return AST module."""
    return astroid.parse(code, module_name=module_name)


class TestMatchesPath:
    """_matches_path — pattern matching against string paths."""

    def test_empty_patterns_returns_false(self):
        assert _matches_path("/workspace/src/foo.py", []) is False

    def test_directory_prefix_match(self):
        assert _matches_path("src/generated/foo.py", ["src/generated/"]) is True

    def test_directory_prefix_with_leading_slash(self):
        assert _matches_path("/workspace/src/generated/foo.py", ["src/generated/"]) is True

    def test_directory_prefix_no_match(self):
        assert _matches_path("/workspace/src/handwritten/foo.py", ["src/generated/"]) is False

    def test_fnmatch_full_path(self):
        assert _matches_path("/workspace/src/test_example.py", ["test_*.py"]) is True

    def test_fnmatch_basename(self):
        assert _matches_path("/workspace/src/foo/bar_test.py", ["*_test.py"]) is True

    def test_fnmatch_no_match(self):
        assert _matches_path("/workspace/src/prod.py", ["test_*.py"]) is False

    def test_backslash_pattern(self):
        assert _matches_path("src\\generated\\foo.py", ["src\\generated\\"]) is True

    def test_multiple_patterns_any_match(self):
        assert (
            _matches_path(
                "/workspace/tests/test_foo.py",
                ["tests/", "test_*.py", "*_test.py"],
            )
            is True
        )

    def test_multiple_patterns_none_match(self):
        assert (
            _matches_path(
                "/workspace/src/prod.py",
                ["tests/", "test_*.py"],
            )
            is False
        )


class TestIsTestFile:
    """_is_test_file — classifies paths as test files."""

    def test_tests_dir_match(self):
        checker = _make_checker(test_patterns=["tests/", "test_*.py", "*_test.py", "conftest.py"])
        assert _is_test_file(checker, Path("/workspace/tests/test_foo.py")) is True

    def test_test_prefixed_filename(self):
        checker = _make_checker(test_patterns=["tests/", "test_*.py", "*_test.py", "conftest.py"])
        assert _is_test_file(checker, Path("/workspace/src/test_example.py")) is True

    def test_suffixed_filename(self):
        checker = _make_checker(test_patterns=["tests/", "test_*.py", "*_test.py", "conftest.py"])
        assert _is_test_file(checker, Path("/workspace/src/foo_test.py")) is True

    def test_conftest(self):
        checker = _make_checker(test_patterns=["tests/", "test_*.py", "*_test.py", "conftest.py"])
        assert _is_test_file(checker, Path("/workspace/src/conftest.py")) is True

    def test_production_file_not_test(self):
        checker = _make_checker(test_patterns=["tests/", "test_*.py", "*_test.py", "conftest.py"])
        assert _is_test_file(checker, Path("/workspace/src/prod.py")) is False

    def test_custom_test_pattern(self):
        checker = _make_checker(test_patterns=["specs/"])
        assert _is_test_file(checker, Path("/workspace/specs/test_foo.py")) is True
        assert _is_test_file(checker, Path("/workspace/tests/test_foo.py")) is False


class TestIsOptedOut:
    """_is_opted_out — classifies paths as opted out."""

    def test_opted_out_by_directory(self):
        checker = _make_checker(stub_opt_out=["src/generated/"])
        assert _is_opted_out(checker, Path("/workspace/src/generated/foo.py")) is True

    def test_not_opted_out(self):
        checker = _make_checker(stub_opt_out=["src/generated/"])
        assert _is_opted_out(checker, Path("/workspace/src/handwritten/foo.py")) is False

    def test_opted_out_by_filename(self):
        checker = _make_checker(stub_opt_out=["vendor_*.py"])
        assert _is_opted_out(checker, Path("/workspace/src/vendor_foo.py")) is True

    def test_empty_opt_out(self):
        checker = _make_checker(stub_opt_out=[])
        assert _is_opted_out(checker, Path("/workspace/src/foo.py")) is False


class TestIsInitExempt:
    """_is_init_exempt — classifies __init__.py as exempt from stub requirement."""

    def test_empty_body_exempt(self):
        node = _parse("")
        assert _is_init_exempt(node) is True

    def test_only_imports_exempt(self):
        node = _parse("from .sub import Foo\nimport os\n")
        assert _is_init_exempt(node) is True

    def test_all_assignment_exempt(self):
        node = _parse("__all__ = ['Foo', 'Bar']\n")
        assert _is_init_exempt(node) is True

    def test_getattr_defined_not_exempt(self):
        node = _parse("def __getattr__(name): ...\n")
        assert _is_init_exempt(node) is False

    def test_function_def_not_exempt(self):
        node = _parse("def helper(): pass\n")
        assert _is_init_exempt(node) is False

    def test_class_def_not_exempt(self):
        node = _parse("class Helper: pass\n")
        assert _is_init_exempt(node) is False

    def test_standalone_expression_not_exempt(self):
        node = _parse("setup(name='foo')\n")
        assert _is_init_exempt(node) is False

    def test_non_all_assignment_not_exempt(self):
        node = _parse("x = 1\n")
        assert _is_init_exempt(node) is False

    def test_ann_assign_not_exempt(self):
        node = _parse("x: int = 1\n")
        assert _is_init_exempt(node) is False

    def test_if_block_not_exempt(self):
        node = _parse("import os\nif os.name == 'nt':\n    x = 1\n")
        assert _is_init_exempt(node) is False


class TestIsTrivialTestData:
    """_is_trivial_test_data — classifies modules as trivial test data."""

    def test_empty_module_trivial(self):
        node = _parse("")
        assert _is_trivial_test_data(node) is True

    def test_literal_assignments_trivial(self):
        node = _parse("x = 1\ny = 'hello'\nz = 3.14\n")
        assert _is_trivial_test_data(node) is True

    def test_function_def_not_trivial(self):
        node = _parse("def helper(): pass\n")
        assert _is_trivial_test_data(node) is False

    def test_class_def_not_trivial(self):
        node = _parse("class Data: pass\n")
        assert _is_trivial_test_data(node) is False

    def test_import_not_trivial(self):
        node = _parse("import os\n")
        assert _is_trivial_test_data(node) is False

    def test_expression_not_trivial(self):
        node = _parse("1 + 1\n")
        assert _is_trivial_test_data(node) is False

    def test_if_block_not_trivial(self):
        node = _parse("x = 1\nif True:\n    y = 2\n")
        assert _is_trivial_test_data(node) is False


class TestHasMainBlock:
    """_has_main_block — detects if __name__ == '__main__': guard."""

    def test_double_equals(self):
        node = _parse("if __name__ == '__main__':\n    main()\n")
        assert _has_main_block(node) is True

    def test_double_quotes(self):
        node = _parse('if __name__ == "__main__":\n    main()\n')
        assert _has_main_block(node) is True

    def test_no_main_block(self):
        node = _parse("def foo(): pass\n")
        assert _has_main_block(node) is False

    def test_different_condition(self):
        node = _parse("if __name__ != '__main__':\n    pass\n")
        assert _has_main_block(node) is False

    def test_empty_module(self):
        node = _parse("")
        assert _has_main_block(node) is False


class TestIsUnderSourceRoot:
    """_is_under_source_root — checks path vs configured source roots."""

    def test_path_under_root(self):
        checker = _make_checker(source_roots=["/workspace/src"])
        assert _is_under_source_root(checker, Path("/workspace/src/prod.py")) is True

    def test_path_not_under_root(self):
        checker = _make_checker(source_roots=["/workspace/src"])
        assert _is_under_source_root(checker, Path("/workspace/tests/foo.py")) is False

    def test_multiple_roots(self):
        checker = _make_checker(source_roots=["/workspace/src", "/workspace/lib"])
        assert _is_under_source_root(checker, Path("/workspace/lib/foo.py")) is True


class TestResolveStub:
    """_resolve_stub — resolves .pyi companions."""

    def test_inline_stub(self, tmp_path: Path):
        py_path = tmp_path / "mod.py"
        py_path.write_text("x = 1\n")
        stub_path = tmp_path / "mod.pyi"
        stub_path.write_text("x: int\n")
        checker = _make_checker(source_roots=[str(tmp_path)])
        result = _resolve_stub(checker, py_path)
        assert result == stub_path

    def test_package_init_stub(self, tmp_path: Path):
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        py_path = pkg / "__init__.py"
        py_path.write_text("x = 1\n")
        stub_path = pkg / "__init__.pyi"
        stub_path.write_text("x: int\n")
        checker = _make_checker(source_roots=[str(tmp_path)])
        result = _resolve_stub(checker, py_path)
        assert result == stub_path

    def test_no_stub_returns_none(self, tmp_path: Path):
        py_path = tmp_path / "mod.py"
        py_path.write_text("x = 1\n")
        checker = _make_checker(source_roots=[str(tmp_path)])
        result = _resolve_stub(checker, py_path)
        assert result is None

    def test_stub_root_resolution(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        py_path = src / "mod.py"
        py_path.write_text("x = 1\n")
        stub_root = tmp_path / "stubs"
        stub_root.mkdir()
        stub_path = stub_root / "mod.pyi"
        stub_path.write_text("x: int\n")
        checker = _make_checker(source_roots=[str(src)], stub_roots=[str(stub_root)])
        result = _resolve_stub(checker, py_path)
        assert result == stub_path


class TestIndexStubDeclarations:
    """_index_stub_declarations — indexes top-level declarations from .pyi."""

    def test_function_and_class_declarations(self, tmp_path: Path):
        stub_path = tmp_path / "mod.pyi"
        stub_path.write_text("""
x: int
def foo(): ...
class Bar: ...
""")
        checker = _make_checker()
        checker._fidelity.stub_variable_nodes["mod"] = {}
        checker._fidelity.stub_callable_nodes["mod"] = {}
        checker._fidelity.stub_class_nodes["mod"] = {}
        _index_stub_declarations(checker, "mod", stub_path)
        assert "x" in checker._coverage.declaration_index.get("mod", set())
        assert "foo" in checker._coverage.declaration_index.get("mod", set())
        assert "Bar" in checker._coverage.declaration_index.get("mod", set())


class TestEmitCoverageViolations:
    """emit_coverage_violations — emits E97A0 for modules without stubs."""

    def test_emits_for_one_missing_module(self, tmp_path: Path):
        tc = CheckerTestCase()
        tc.CHECKER_CLASS = StubChecker
        tc.setup_method()
        mock_node = MagicMock()
        mock_node.name = "mod_a"
        tc.checker._coverage.module_index["mod_a"] = (tmp_path / "mod_a.py", mock_node)
        tc.checker._coverage.stub_missing = {"mod_a"}
        emit_coverage_violations(tc.checker)
        msgs = tc.linter.release_messages()
        assert len(msgs) == 1
        assert msgs[0].msg_id == "missing-module-stub"

    def test_no_missing_emits_nothing(self, tmp_path: Path):
        tc = CheckerTestCase()
        tc.CHECKER_CLASS = StubChecker
        tc.setup_method()
        tc.checker._coverage.stub_missing = set()
        emit_coverage_violations(tc.checker)
        msgs = tc.linter.release_messages()
        assert len(msgs) == 0

    def test_skip_module_not_in_index(self, tmp_path: Path):
        tc = CheckerTestCase()
        tc.CHECKER_CLASS = StubChecker
        tc.setup_method()
        tc.checker._coverage.stub_missing = {"ghost_module"}
        emit_coverage_violations(tc.checker)
        msgs = tc.linter.release_messages()
        assert len(msgs) == 0