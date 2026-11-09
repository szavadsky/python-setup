"""Parametrize rows and layout builders for stub-coverage tests.

Split by checker domain out of the former 1393-line ``_factories.py`` (pylint
C0302). Paired with ``tests/checkers/test_stub_coverage.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest
from pylint.testutils import CheckerTestCase

if TYPE_CHECKING:
    from _pytest.mark.structures import ParameterSet

    from python_setup_lint.checkers.stub.checker import StubChecker

_p = pytest.param


# ── stub coverage helper tests ──

_MATCHES_PATH_CASES: list[ParameterSet] = [
    _p("/workspace/src/foo.py", [], False, id="empty_patterns_returns_false"),
    _p("src/generated/foo.py", ["src/generated/"], True, id="directory_prefix_match"),
    _p(
        "/workspace/src/generated/foo.py",
        ["src/generated/"],
        True,
        id="directory_prefix_with_leading_slash",
    ),
    _p(
        "/workspace/src/handwritten/foo.py",
        ["src/generated/"],
        False,
        id="directory_prefix_no_match",
    ),
    _p("/workspace/src/test_example.py", ["test_*.py"], True, id="fnmatch_full_path"),
    _p("/workspace/src/foo/bar_test.py", ["*_test.py"], True, id="fnmatch_basename"),
    _p("/workspace/src/prod.py", ["test_*.py"], False, id="fnmatch_no_match"),
    _p("src\\generated\\foo.py", ["src\\generated\\"], True, id="backslash_pattern"),
    _p(
        "/workspace/tests/test_foo.py",
        ["tests/", "test_*.py", "*_test.py"],
        True,
        id="multiple_patterns_any_match",
    ),
    _p(
        "/workspace/src/prod.py",
        ["tests/", "test_*.py"],
        False,
        id="multiple_patterns_none_match",
    ),
]

_DEFAULT_TEST_PATTERNS = ["tests/", "test_*.py", "*_test.py", "conftest.py"]

_IS_TEST_FILE_CASES: list[ParameterSet] = [
    _p(
        "/workspace/tests/test_foo.py",
        _DEFAULT_TEST_PATTERNS,
        True,
        id="tests_dir_match",
    ),
    _p(
        "/workspace/src/test_example.py",
        _DEFAULT_TEST_PATTERNS,
        True,
        id="test_prefixed_filename",
    ),
    _p(
        "/workspace/src/foo_test.py",
        _DEFAULT_TEST_PATTERNS,
        True,
        id="suffixed_filename",
    ),
    _p("/workspace/src/conftest.py", _DEFAULT_TEST_PATTERNS, True, id="conftest"),
    _p(
        "/workspace/src/prod.py",
        _DEFAULT_TEST_PATTERNS,
        False,
        id="production_file_not_test",
    ),
]

_IS_TEST_FILE_CUSTOM_CASES: list[ParameterSet] = [
    _p("/workspace/specs/test_foo.py", ["specs/"], True, id="custom_pattern_matches"),
    _p(
        "/workspace/tests/test_foo.py",
        ["specs/"],
        False,
        id="custom_pattern_excludes_tests",
    ),
]

_IS_OPTED_OUT_CASES: list[ParameterSet] = [
    _p(
        "/workspace/src/generated/foo.py",
        ["src/generated/"],
        True,
        id="opted_out_by_directory",
    ),
    _p(
        "/workspace/src/handwritten/foo.py",
        ["src/generated/"],
        False,
        id="not_opted_out",
    ),
    _p(
        "/workspace/src/vendor_foo.py",
        ["vendor_*.py"],
        True,
        id="opted_out_by_filename",
    ),
    _p("/workspace/src/foo.py", [], False, id="empty_opt_out"),
]

_IS_INIT_EXEMPT_CASES: list[ParameterSet] = [
    _p("", True, id="empty_body_exempt"),
    _p("from .sub import Foo\nimport os\n", True, id="only_imports_exempt"),
    _p("__all__ = ['Foo', 'Bar']\n", True, id="all_assignment_exempt"),
    _p("def __getattr__(name): ...\n", False, id="getattr_defined_not_exempt"),
    _p("def helper(): pass\n", False, id="function_def_not_exempt"),
    _p("class Helper: pass\n", False, id="class_def_not_exempt"),
    _p("setup(name='foo')\n", False, id="standalone_expression_not_exempt"),
    _p("x = 1\n", False, id="non_all_assignment_not_exempt"),
    _p("x: int = 1\n", False, id="ann_assign_not_exempt"),
    _p("__version__: str = _version('x')\n", True, id="version_ann_assign_exempt"),
    _p("__all__: list[str] = []\n", True, id="all_ann_assign_exempt"),
    _p(
        "__version__: str = _version('x')\n__all__: list[str] = []\n",
        True,
        id="init_metadata_exempt",
    ),
    _p("import os\nif os.name == 'nt':\n    x = 1\n", False, id="if_block_not_exempt"),
]

_IS_TRIVIAL_TEST_DATA_CASES: list[ParameterSet] = [
    _p("", True, id="empty_module_trivial"),
    _p("x = 1\ny = 'hello'\nz = 3.14\n", True, id="literal_assignments_trivial"),
    _p("def helper(): pass\n", False, id="function_def_not_trivial"),
    _p("class Data: pass\n", False, id="class_def_not_trivial"),
    _p("import os\n", False, id="import_not_trivial"),
    _p("1 + 1\n", False, id="expression_not_trivial"),
    _p("x = 1\nif True:\n    y = 2\n", False, id="if_block_not_trivial"),
]

_HAS_MAIN_BLOCK_CASES: list[ParameterSet] = [
    _p("if __name__ == '__main__':\n    main()\n", True, id="double_equals"),
    _p('if __name__ == "__main__":\n    main()\n', True, id="double_quotes"),
    _p("def foo(): pass\n", False, id="no_main_block"),
    _p("if __name__ != '__main__':\n    pass\n", False, id="different_condition"),
    _p("", False, id="empty_module"),
]

_IS_UNDER_SOURCE_ROOT_CASES: list[ParameterSet] = [
    _p("/workspace/src/prod.py", ["/workspace/src"], True, id="path_under_root"),
    _p("/workspace/tests/foo.py", ["/workspace/src"], False, id="path_not_under_root"),
    _p(
        "/workspace/lib/foo.py",
        ["/workspace/src", "/workspace/lib"],
        True,
        id="multiple_roots",
    ),
]


# ── stub_coverage: shared checker construction ──


def make_coverage_checker(**config_kwargs: Any) -> tuple[StubChecker, CheckerTestCase]:
    from python_setup_lint.checkers.stub.checker import StubChecker

    tc = CheckerTestCase()
    tc.CHECKER_CLASS = StubChecker
    tc.setup_method()
    for key, value in config_kwargs.items():
        setattr(tc.linter.config, key, value)
    tc.checker.open()
    return tc.checker, tc


# ── stub_coverage: _resolve_stub layout ──

_RESOLVE_STUB_CASES: list[ParameterSet] = [
    _p("inline", "returns_pyi", id="inline_stub"),
    _p("package", "returns_pyi", id="package_init_stub"),
    _p("no_stub", "returns_none", id="no_stub_returns_none"),
    _p("stub_root", "returns_pyi", id="stub_root_resolution"),
]


def materialize_resolve_stub_layout(tmp_path: Path, layout_kind: str, /) -> tuple[StubChecker, Path, Path | None]:
    if layout_kind == "inline":
        py_path = tmp_path / "mod.py"
        py_path.write_text("x = 1\n")
        stub_path = tmp_path / "mod.pyi"
        stub_path.write_text("x: int\n")
        checker, _tc = make_coverage_checker(source_roots=[str(tmp_path)])
        return checker, py_path, stub_path
    if layout_kind == "package":
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        py_path = pkg / "__init__.py"
        py_path.write_text("x = 1\n")
        stub_path = pkg / "__init__.pyi"
        stub_path.write_text("x: int\n")
        checker, _tc = make_coverage_checker(source_roots=[str(tmp_path)])
        return checker, py_path, stub_path
    if layout_kind == "no_stub":
        py_path = tmp_path / "mod.py"
        py_path.write_text("x = 1\n")
        checker, _tc = make_coverage_checker(source_roots=[str(tmp_path)])
        return checker, py_path, None
    src = tmp_path / "src"
    src.mkdir()
    py_path = src / "mod.py"
    py_path.write_text("x = 1\n")
    stub_root = tmp_path / "stubs"
    stub_root.mkdir()
    stub_path = stub_root / "mod.pyi"
    stub_path.write_text("x: int\n")
    checker, _tc = make_coverage_checker(source_roots=[str(src)], stub_roots=[str(stub_root)])
    return checker, py_path, stub_path


# ── stub_coverage: emit_coverage_violations ──

_EMIT_COVERAGE_CASES: list[ParameterSet] = [
    _p("in_index", "mod_a", 1, id="one_missing_module"),
    _p("no_missing", "", 0, id="no_missing_emits_nothing"),
    _p("skip_module_not_in_index", "ghost_module", 0, id="skip_module_not_in_index"),
]


def make_emit_coverage_state(tmp_path: Path, setup_kind: str, stub_missing_module: str, /) -> tuple[CheckerTestCase, MagicMock]:
    from python_setup_lint.checkers.stub.checker import StubChecker

    tc = CheckerTestCase()
    tc.CHECKER_CLASS = StubChecker
    tc.setup_method()
    mock_node = MagicMock()
    mock_node.name = stub_missing_module or "anon"
    if not stub_missing_module:
        tc.checker._coverage.stub_missing = set()
    elif setup_kind == "in_index":
        tc.checker._coverage.module_index[stub_missing_module] = (
            tmp_path / f"{stub_missing_module}.py",
            mock_node,
        )
        tc.checker._coverage.stub_missing = {stub_missing_module}
    else:
        tc.checker._coverage.stub_missing = {stub_missing_module}
    return tc, mock_node
