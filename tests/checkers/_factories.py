"""Shared non-fixture factory functions and parametrise tables for the
python-setup checker test suite.

Distinct from ``tests/conftest.py``: pytest auto-discovers and auto-injects
``conftest.py`` fixtures, but module-level callables / data tables used by
``@pytest.mark.parametrize`` rows at collection time must be importable.
This module is the single import target — every checker test file does
``from tests.checkers._factories import ...`` so collection never depends on
which pytest ``rootdir`` setting is active.

Tables here are pure data (no side effects, no `tmp_path`); row data is
free LOC and does NOT count against the per-file LOC gate. Helpers that
build astroid modules from source / assert message ids live here too.
"""

from __future__ import annotations
from typing import Any, TYPE_CHECKING
import inspect
from pathlib import Path
from unittest.mock import MagicMock
import astroid
import pytest
from pylint.testutils import CheckerTestCase
from python_setup_lint.testing import _make_tc as _make_tc_factory

if TYPE_CHECKING:
    from pylint.checkers import BaseChecker
    from python_setup_lint.checkers.stub_checker import StubChecker
    from python_setup_lint.checkers.stub_import_contract import ImportUsage

_p = pytest.param


# ── Generic message helpers ──


def make_tc(checker_class: type[BaseChecker]) -> CheckerTestCase:
    return _make_tc_factory(checker_class)


# ── no-try-import checker ──

_NO_TRY_DETECT_CASES: list[Any] = [
    _p("try:\n    import litellm\nexcept ImportError:\n    pass\n", 1, ("ImportError",), id="import_in_try_except_importerror"),
    _p("try:\n    import litellm\nexcept ModuleNotFoundError:\n    pass\n", 1, (), id="import_in_try_except_modulenotfound"),
    _p("try:\n    from pydantic import ValidationError\nexcept ImportError:\n    pass\n", 1, (), id="from_import_in_try_except_importerror"),
    _p("try:\n    import httpx\nexcept:\n    pass\n", 1, ("bare except",), id="import_in_try_bare_except"),
    _p("try:\n    import litellm\nexcept (ImportError, ModuleNotFoundError):\n    pass\n", 1, (), id="import_in_try_tuple_import_errors"),
    _p("try:\n    import litellm\nexcept ImportError:\n    pass\n\ntry:\n    import httpx\nexcept ImportError:\n    pass\n", 2, (), id="two_imports_separate_try_blocks"),
    _p("try:\n    import litellm\nexcept ImportError:\n    pass\nexcept ModuleNotFoundError:\n    pass\n", 2, (), id="two_imports_separate_handlers_one_try"),
    _p("try:\n    import litellm\nexcept ValueError:\n    pass\n", 0, (), id="import_in_try_non_import_handler_not_flagged"),
    _p("try:\n    import httpx\nexcept ValueError:\n    pass\nexcept ImportError:\n    pass\nexcept OSError:\n    pass\n", 1, (), id="handler_mixed_import_and_non_import"),
    _p("try:\n    import litellm as _litellm\nexcept ImportError:\n    _litellm = None\n", 1, (), id="proxy_module_level_guard"),
]

_NO_TRY_DO_NOT_DETECT_CASES: list[Any] = [
    _p("try:\n    x = 1 / 0\nexcept ZeroDivisionError:\n    pass\n", id="try_without_import"),
    _p("import os\nx = os.path.join('a', 'b')\n", id="import_outside_try"),
    _p("", id="empty_module"),
    _p("try:\n    result = api_call()\nexcept ConnectionError:\n    result = None\n", id="non_import_exception_handling"),
]


# ── beartype checker ──

_BEARTYPE_MISS_CASES: list[Any] = [
    _p("def foo(): pass", 1, None, id="plain_def"),
    _p("async def foo(): pass", 1, None, id="async_def"),
    _p("class X:\n    def method(self): pass", 1, "method", id="public_method_in_class"),
    _p("def foo(): pass\ndef bar(): pass\n", 2, None, id="multiple_public_functions"),
]

_BEARTYPE_SOURCE_ROOT_CASES: list[Any] = [
    _p("def foo(): pass", "tests/test_mod.py", 0, id="outside_source_root"),
    _p("def foo(): pass", "src/prod.py", 1, id="under_source_root"),
]

_BEARTYPE_SKIP_CASES: list[Any] = [
    _p("def _helper(): pass", 0, id="private_function"),
    _p("def public(): pass\ndef _private(): pass\n", 1, id="mixed_public_and_private"),
    _p("class X:\n    def __init__(self): pass", 0, id="init_skipped"),
    _p("class X:\n    def __str__(self): pass", 0, id="str_skipped"),
    _p("class X:\n    def __init__(self): pass\n    def run(self): pass", 1, id="dunder_only_init_skipped_then_public"),
]


# ── stub normalizer ──

_NORMALIZER_INFER_CASES: list[Any] = [
    _p("x: str", "str", id="infer_simple_name"),
    _p("x: list[int]", "list[int]", id="infer_builtin_list"),
    _p("x: str | None", "str | None", id="infer_native_union"),
    _p("x: 'SomeFutureType'", None, id="infer_uninferable_returns_non_null"),
]


# ── stub checker ──

_STUB_FILE_CLASSIFICATION_CASES: list[Any] = [
    _p("/workspace/tests/test_foo.py", ["/workspace/src"], None, None, 0, id="test_file_in_tests_dir"),
    _p("/workspace/src/test_example.py", ["/workspace/src"], ["test_*.py", "tests/"], None, 0, id="test_file_named_test_prefixed"),
    _p("/workspace/other/foo.py", ["/workspace/src"], None, None, 0, id="file_outside_source_root_skipped"),
    _p("/workspace/src/generated/foo.py", ["/workspace/src"], None, ["src/generated/"], 0, id="opted_out_by_directory"),
    _p("/workspace/src/vendor/external.py", ["/workspace/src"], None, ["src/vendor/"], 0, id="opted_out_by_filename"),
]

_RESOLVE_RELATIVE_CASES: list[Any] = [
    _p("mod_a", 0, "os", False, "os", id="absolute_import"),
    _p("mod_a", 0, None, False, "", id="absolute_no_modname"),
    _p("mypkg", 1, None, True, "mypkg", id="same_package_init"),
    _p("mypkg", 1, "mod_a", True, "mypkg.mod_a", id="same_package_init_with_name"),
    _p("mypkg.mod_a", 2, "sibling", False, "sibling", id="parent_package"),
    _p("pkg.sub.mod_a", 3, "other", False, "other", id="grandparent_package"),
    _p("mod_a", 3, "other", True, "other", id="level_exceeds_depth"),
]

_IS_TYPE_CHECKING_GUARD_CASES: list[Any] = [
    _p("TYPE_CHECKING", True, id="name_form"),
    _p("typing.TYPE_CHECKING", True, id="typing_dot_name"),
    _p("SOME_FLAG", False, id="other_name"),
    _p("os.name", False, id="other_attribute"),
]

_IN_TYPE_CHECKING_BLOCK_POSITIVE_CASES: list[Any] = [
    _p("if TYPE_CHECKING:\n    from foo import Bar\n", lambda m: m.body[0].body[0], id="under_type_checking"),
    _p("if TYPE_CHECKING:\n    if True:\n        from foo import Bar\n", lambda m: m.body[0].body[0].body[0], id="nested_inside_type_checking"),
]

_IN_TYPE_CHECKING_BLOCK_NEGATIVE_CASES: list[Any] = [
    _p("from foo import Bar\n", lambda m: m.body[0], id="not_under_type_checking"),
]


# ── stub coverage helper tests ──

_MATCHES_PATH_CASES: list[Any] = [
    _p("/workspace/src/foo.py", [], False, id="empty_patterns_returns_false"),
    _p("src/generated/foo.py", ["src/generated/"], True, id="directory_prefix_match"),
    _p("/workspace/src/generated/foo.py", ["src/generated/"], True, id="directory_prefix_with_leading_slash"),
    _p("/workspace/src/handwritten/foo.py", ["src/generated/"], False, id="directory_prefix_no_match"),
    _p("/workspace/src/test_example.py", ["test_*.py"], True, id="fnmatch_full_path"),
    _p("/workspace/src/foo/bar_test.py", ["*_test.py"], True, id="fnmatch_basename"),
    _p("/workspace/src/prod.py", ["test_*.py"], False, id="fnmatch_no_match"),
    _p("src\\generated\\foo.py", ["src\\generated\\"], True, id="backslash_pattern"),
    _p("/workspace/tests/test_foo.py", ["tests/", "test_*.py", "*_test.py"], True, id="multiple_patterns_any_match"),
    _p("/workspace/src/prod.py", ["tests/", "test_*.py"], False, id="multiple_patterns_none_match"),
]

_DEFAULT_TEST_PATTERNS = ["tests/", "test_*.py", "*_test.py", "conftest.py"]

_IS_TEST_FILE_CASES: list[Any] = [
    _p("/workspace/tests/test_foo.py", _DEFAULT_TEST_PATTERNS, True, id="tests_dir_match"),
    _p("/workspace/src/test_example.py", _DEFAULT_TEST_PATTERNS, True, id="test_prefixed_filename"),
    _p("/workspace/src/foo_test.py", _DEFAULT_TEST_PATTERNS, True, id="suffixed_filename"),
    _p("/workspace/src/conftest.py", _DEFAULT_TEST_PATTERNS, True, id="conftest"),
    _p("/workspace/src/prod.py", _DEFAULT_TEST_PATTERNS, False, id="production_file_not_test"),
]

_IS_TEST_FILE_CUSTOM_CASES: list[Any] = [
    _p("/workspace/specs/test_foo.py", ["specs/"], True, id="custom_pattern_matches"),
    _p("/workspace/tests/test_foo.py", ["specs/"], False, id="custom_pattern_excludes_tests"),
]

_IS_OPTED_OUT_CASES: list[Any] = [
    _p("/workspace/src/generated/foo.py", ["src/generated/"], True, id="opted_out_by_directory"),
    _p("/workspace/src/handwritten/foo.py", ["src/generated/"], False, id="not_opted_out"),
    _p("/workspace/src/vendor_foo.py", ["vendor_*.py"], True, id="opted_out_by_filename"),
    _p("/workspace/src/foo.py", [], False, id="empty_opt_out"),
]

_IS_INIT_EXEMPT_CASES: list[Any] = [
    _p("", True, id="empty_body_exempt"),
    _p("from .sub import Foo\nimport os\n", True, id="only_imports_exempt"),
    _p("__all__ = ['Foo', 'Bar']\n", True, id="all_assignment_exempt"),
    _p("def __getattr__(name): ...\n", False, id="getattr_defined_not_exempt"),
    _p("def helper(): pass\n", False, id="function_def_not_exempt"),
    _p("class Helper: pass\n", False, id="class_def_not_exempt"),
    _p("setup(name='foo')\n", False, id="standalone_expression_not_exempt"),
    _p("x = 1\n", False, id="non_all_assignment_not_exempt"),
    _p("x: int = 1\n", False, id="ann_assign_not_exempt"),
    _p("import os\nif os.name == 'nt':\n    x = 1\n", False, id="if_block_not_exempt"),
]

_IS_TRIVIAL_TEST_DATA_CASES: list[Any] = [
    _p("", True, id="empty_module_trivial"),
    _p("x = 1\ny = 'hello'\nz = 3.14\n", True, id="literal_assignments_trivial"),
    _p("def helper(): pass\n", False, id="function_def_not_trivial"),
    _p("class Data: pass\n", False, id="class_def_not_trivial"),
    _p("import os\n", False, id="import_not_trivial"),
    _p("1 + 1\n", False, id="expression_not_trivial"),
    _p("x = 1\nif True:\n    y = 2\n", False, id="if_block_not_trivial"),
]

_HAS_MAIN_BLOCK_CASES: list[Any] = [
    _p("if __name__ == '__main__':\n    main()\n", True, id="double_equals"),
    _p('if __name__ == "__main__":\n    main()\n', True, id="double_quotes"),
    _p("def foo(): pass\n", False, id="no_main_block"),
    _p("if __name__ != '__main__':\n    pass\n", False, id="different_condition"),
    _p("", False, id="empty_module"),
]

_IS_UNDER_SOURCE_ROOT_CASES: list[Any] = [
    _p("/workspace/src/prod.py", ["/workspace/src"], True, id="path_under_root"),
    _p("/workspace/tests/foo.py", ["/workspace/src"], False, id="path_not_under_root"),
    _p("/workspace/lib/foo.py", ["/workspace/src", "/workspace/lib"], True, id="multiple_roots"),
]


# ── stub_callable: extract param descriptors ──

_EXTRACT_PARAM_CASES: list[Any] = [
    _p("def foo() -> None: ...", [], [], id="empty_function"),
    _p("def foo(a, b, /) -> None: ...", ["a", "b"], [inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_ONLY], id="positional_only"),
    _p("def foo(a, b) -> None: ...", ["a", "b"], [inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_OR_KEYWORD], id="positional_or_keyword"),
    _p("def foo(*args) -> None: ...", ["args"], [inspect.Parameter.VAR_POSITIONAL], id="var_positional"),
    _p("def foo(*, x, y) -> None: ...", ["x", "y"], [inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.KEYWORD_ONLY], id="keyword_only"),
    _p("def foo(**kwargs) -> None: ...", ["kwargs"], [inspect.Parameter.VAR_KEYWORD], id="var_keyword"),
]

_EXTRACT_DEFAULT_CASES: list[Any] = [
    _p("def foo(a, b=1) -> None: ...", [False, True], id="default_presence_detected"),
    _p("def foo(*, x, y='hello') -> None: ...", [False, True], id="default_presence_kwonly"),
]

_EXTRACT_STRIP_SELF_CASES: list[Any] = [
    _p("def bar(self, x, y) -> None: ...", True, ["x", "y"], id="strip_self"),
    _p("def bar(cls, x, y) -> None: ...", True, ["x", "y"], id="strip_cls"),
    _p("def bar(a, b) -> None: ...", True, ["a", "b"], id="no_strip_non_method"),
]

_EXTRACT_ANNOTATION_CASES: list[Any] = [
    _p("def foo(x: int, y: str | None) -> None: ...", "int", None, id="annotations_extracted"),
    _p("def foo(*args: int) -> None: ...", "int", None, id="vararg_annotation"),
    _p("def foo(**kwargs: str) -> None: ...", "str", None, id="kwarg_annotation"),
]


# ── stub_callable: compare descriptors ──

_COMPARE_DESCRIPTOR_CASES: list[Any] = [
    _p([("a", inspect.Parameter.POSITIONAL_OR_KEYWORD, False), ("b", inspect.Parameter.POSITIONAL_OR_KEYWORD, False)], [("a", inspect.Parameter.POSITIONAL_OR_KEYWORD, False), ("b", inspect.Parameter.POSITIONAL_OR_KEYWORD, False)], None, id="identical_params"),
    _p([("a", inspect.Parameter.POSITIONAL_OR_KEYWORD, False), ("b", inspect.Parameter.POSITIONAL_OR_KEYWORD, False)], [("a", inspect.Parameter.POSITIONAL_OR_KEYWORD, False)], "param_count", id="param_count_mismatch"),
    _p([("a", inspect.Parameter.POSITIONAL_OR_KEYWORD, False)], [("b", inspect.Parameter.POSITIONAL_OR_KEYWORD, False)], "param_name", id="param_name_mismatch"),
    _p([("x", inspect.Parameter.POSITIONAL_OR_KEYWORD, False)], [("x", inspect.Parameter.KEYWORD_ONLY, False)], "param_kind", id="param_kind_mismatch"),
    _p([("x", inspect.Parameter.POSITIONAL_OR_KEYWORD, True)], [("x", inspect.Parameter.POSITIONAL_OR_KEYWORD, False)], "param_default", id="default_presence_mismatch"),
    _p([], [], None, id="empty_lists"),
]

_COMPARE_ANNOTATION_CASES: list[Any] = [
    _p(["int", "str"], ["int", "str"], 0, None, id="all_match_returns_empty"),
    _p(["int", "str"], ["int", "int"], 1, "y", id="param_annotation_mismatch_detected"),
    _p([None], ["int"], 0, None, id="skips_missing_annotations"),
    _p([None], [None], 0, None, id="skips_no_annotation_on_both"),
]

_COMPARE_RETURN_CASES: list[Any] = [
    _p(None, None, "skip_both_none", True, id="both_none"),
    _p(None, "int", "skip_both_none", True, id="stub_none_skipped"),
    _p("int", None, "skip_both_none", True, id="impl_none_skipped"),
    _p("int", "int", "compare", True, id="matching_returns"),
    _p("str", "int", "compare", False, id="mismatched_returns"),
    _p("typing.List[int]", "list[int]", "compare", True, id="normalized_typing"),
]


# ── stub_class fidelity: _normalize_bases ──

_NORMALIZE_BASES_CASES: list[Any] = [
    _p("class Foo(BaseModel): ...\n", ["BaseModel"], id="simple_name"),
    _p("class Foo(pydantic.BaseModel): ...\n", ["BaseModel"], id="attribute_base"),
    _p("class Foo(object): ...\n", ["builtins.object"], id="builtins_object"),
    _p("class Foo(B, A, C): ...\n", ["A", "B", "C"], id="multiple_bases_sorted"),
    _p("class Foo(Generic[T]): ...\n", ["Generic"], id="subscript_base"),
]

_IS_PUBLIC_METHOD_CASES: list[Any] = [
    _p("foo", True, id="plain_name"),
    _p("_helper", False, id="private_name"),
    _p("__str__", False, id="dunder_str"),
    _p("__init__", True, id="init"),
    _p("__new__", True, id="new"),
    _p("__repr__", False, id="repr"),
]


# ── stub_class: E97B1 / E97B2 ──

_STUB_SYMBOL_MISSING_CASES: list[Any] = [
    _p("x: int = 1\n", "x: int\nclass Foo: ...\n", "stub-symbol-missing", 1, "Foo", id="stub_class_missing_from_impl"),
    _p("x: int = 1\n", "x: int\ndef foo(): ...\n", "stub-symbol-missing", 1, "foo", id="stub_func_missing_from_impl"),
    _p("x: int = 1\n", "x: int\ny: str\n", "stub-symbol-missing", 1, "y", id="stub_var_missing_from_impl"),
]

_KIND_MISMATCH_CASES: list[Any] = [
    _p("Foo: int = 1\n", "class Foo: ...\n", "symbol-kind-mismatch", id="stub_class_impl_var"),
    _p("foo: int = 1\n", "def foo(): ...\n", "symbol-kind-mismatch", id="stub_func_impl_var"),
    _p("def Foo(): ...\n", "class Foo: ...\n", "symbol-kind-mismatch", id="stub_class_impl_func"),
    _p("class Foo: ...\n", "Foo: int\n", "symbol-kind-mismatch", id="stub_var_impl_class"),
]


# ── stub docstring checker ──

_DOCSTRING_NO_COMPANION_CASES: list[Any] = [
    _p('def foo():\n    """My docstring."""\n    pass\n', 0, id="no_companion_plain_func"),
    _p('async def foo():\n    """My docstring."""\n    pass\n', 0, id="no_companion_async_func"),
    _p('class MyClass:\n    def method(self):\n        """Method doc."""\n        pass\n', 0, id="no_companion_method"),
]

_DOCSTRING_DOES_NOT_DETECT_CASES: list[Any] = [
    _p("def foo():\n    pass\n", id="no_docstring_no_message"),
    _p("def foo():\n    ...\n", id="empty_body_no_message"),
    _p('class MyClass:\n    """Class-level docs."""\n    pass\n', id="class_docstring_no_message"),
    _p("def foo():\n    42\n    pass\n", id="non_string_first_expr"),
]

_DOCSTRING_DETECT_CASES: list[Any] = [
    _p('def foo():\n    """Usage docstring."""\n    pass\n', 1, "foo", id="function_docstring_detected"),
    _p('async def foo():\n    """Usage docstring."""\n    pass\n', 1, None, id="async_function_docstring_detected"),
    _p('class MyClass:\n    def method(self):\n        """Method doc."""\n        pass\n', 1, "method", id="method_docstring_detected"),
    _p('def foo():\n    """Doc."""\n    pass\n\ndef bar():\n    pass\n', 1, None, id="mixed_docstrings_and_no_docstrings"),
]


# ── AnnotationNormalizer._apply_rewrites ──

_APPLY_REWRITES_CASES: list[Any] = [
    _p("typing.List[str]", "list[str]", id="rewrite_typing_list"),
    _p("typing.Dict[str, int]", "dict[str, int]", id="rewrite_typing_dict"),
    _p("typing.Optional[str]", "str | None", id="rewrite_typing_optional"),
    _p("typing.Union[str, int]", "str | int", id="rewrite_typing_union"),
    _p("typing.Union[list[str], int]", "list[str] | int", id="rewrite_typing_union_nested_generic"),
    _p("collections.abc.Callable", "collections.abc.Callable", id="rewrite_no_match_passes_through"),
]

_SPLIT_OUTER_COMMAS_CASES: list[Any] = [
    _p("str, int, float", ["str", "int", "float"], id="simple"),
    _p("list[str], int", ["list[str]", "int"], id="with_brackets"),
]


# ── AnnotationNormalizer._ast_string ──

_AST_STRING_CASES: list[Any] = [
    _p("x: list[str]", ["list"], "contains", id="subscript"),
    _p("x: int | str", ["int | str"], "equals", id="binary_op_union"),
    _p("x: typing.Optional[str]", ["typing.Optional"], "contains", id="attribute"),
    _p("x: tuple[int, str]", None, "not_none", id="tuple"),
    _p("x: Literal['hello']", ["hello"], "contains", id="const"),
    _p("x: dict[str, list[int]]", ["dict", "list"], "contains", id="nested_subscript"),
]


# ── stub_coverage: shared checker construction ──


def make_coverage_checker(**config_kwargs: Any) -> tuple[StubChecker, CheckerTestCase]:
    from python_setup_lint.checkers.stub_checker import StubChecker

    tc = CheckerTestCase()
    tc.CHECKER_CLASS = StubChecker
    tc.setup_method()
    for key, value in config_kwargs.items():
        setattr(tc.linter.config, key, value)
    tc.checker.open()
    return tc.checker, tc


# ── stub_import_contract helpers ──


def build_import_contract_state(
    *,
    module_index: dict | None = None,
    stub_index: dict | None = None,
    declaration_index: dict | None = None,
    import_usages: list | None = None,
) -> tuple[StubChecker, CheckerTestCase]:

    tc = make_tc(_stub_checker_class())
    c = tc.checker._coverage
    if module_index is not None:
        c.module_index = module_index
    if stub_index is not None:
        c.stub_index = stub_index
    if declaration_index is not None:
        c.declaration_index = declaration_index
    if import_usages is not None:
        c.import_usages = import_usages
        for usage in import_usages:
            if usage.importer_module not in c.module_index:
                mock_node = MagicMock()
                mock_node.name = usage.importer_module
                mock_node.position = None
                c.module_index[usage.importer_module] = (
                    Path(f"/workspace/src/{usage.importer_module}.py"),
                    mock_node,
                )
    return tc.checker, tc


def _stub_checker_class() -> type[StubChecker]:
    from python_setup_lint.checkers.stub_checker import StubChecker
    return StubChecker


def import_usage(*args: Any, **kwargs: Any) -> ImportUsage:
    from python_setup_lint.checkers.stub_import_contract import ImportUsage
    return ImportUsage(*args, **kwargs)


# ── stub_docstring: shared walker ──


def walk_both_release_for_pyi(
    code: str,
    py_path: Path,
    source_roots: list[str] | None = None,
) -> list:
    from pylint.testutils import UnittestLinter
    from pylint.utils import ASTWalker
    from python_setup_lint.checkers.stub_checker import StubChecker
    from python_setup_lint.checkers.stub_docstring_checker import StubDocstringChecker

    pyi_path = py_path.with_suffix(".pyi")
    pyi_path.parent.mkdir(parents=True, exist_ok=True)
    pyi_path.write_text("# stub\n")
    module_name = py_path.stem
    linter = UnittestLinter()
    stub = StubChecker(linter)
    stub_doc = StubDocstringChecker(linter)
    linter.register_checker(stub_doc)
    if source_roots:
        linter.config.source_roots = source_roots
    stub.open()
    module = astroid.parse(code, module_name=module_name)
    module.file = str(py_path)
    walker = ASTWalker(linter)
    walker.add_checker(stub)
    walker.add_checker(stub_doc)
    walker.walk(module)
    return linter.release_messages()


# ── stub_checker: import-usage / contract-violations tables ──

_IMPORT_USAGE_FIELD_CASES: list[Any] = [
    _p({"importer_module": "mod_a", "lineno": 5, "target_module": "mod_b", "symbol_name": "Foo", "alias": None, "is_star": False}, {"importer_module": "mod_a", "lineno": 5, "target_module": "mod_b", "symbol_name": "Foo", "alias": None, "is_star": False}, id="fields"),
    _p({"importer_module": "mod_a", "lineno": 3, "target_module": "mod_b", "symbol_name": None, "alias": None, "is_star": False}, {"symbol_name": None}, id="module_import_symbol_name_none"),
    _p({"importer_module": "mod_a", "lineno": 7, "target_module": "mod_b", "symbol_name": "*", "alias": None, "is_star": True}, {"is_star": True}, id="star_import_is_star"),
]

_IMPORT_CONTRACT_CASES: list[Any] = [
    _p("mod_a", False, None, "mod_a", "Foo", False, None, "missing-module-stub-for-import", 1, id="e97a2_when_target_no_stub"),
    _p("mod_b", True, {"Foo"}, "mod_a", "Bar", False, None, "missing-import-declaration", 1, id="e97a1_when_symbol_not_declared"),
    _p("mod_b", True, {"Foo"}, "mod_a", "Foo", False, None, None, 0, id="no_violation_when_symbol_declared"),
    _p("mod_b", True, None, "mod_a", "*", True, "error", "star-import-unresolvable", 1, id="e97a3_star_import"),
]

_STAR_POLICY_CASES: list[Any] = [
    _p("error", 1, id="star_policy_error"),
    _p("ignore", 0, id="star_policy_ignore"),
]

_VARIABLE_FIDELITY_CASES: list[Any] = [
    _p("ClassVar[int]", True, id="classvar_skipped"),
    _p("int", False, id="non_classvar"),
]


# ── stub_checker: shared walk helpers ──


def walk_stub_close_release(
    code: str,
    file_path: str,
    *,
    source_roots: list[str] | None = None,
    test_patterns: list[str] | None = None,
    stub_opt_out: list[str] | None = None,
    stub_roots: list[str] | None = None,
    module_name: str = "test_module",
) -> list:
    from python_setup_lint.checkers.stub_checker import StubChecker

    tc = _make_tc_factory(StubChecker)
    if source_roots is not None:
        tc.linter.config.source_roots = source_roots
    if test_patterns is not None:
        tc.linter.config.test_patterns = test_patterns
    if stub_opt_out is not None:
        tc.linter.config.stub_opt_out = stub_opt_out
    if stub_roots is not None:
        tc.linter.config.stub_roots = stub_roots
    module = astroid.parse(code, module_name=module_name)
    module.file = file_path
    tc.checker.open()
    tc.walk(module)
    tc.checker.close()
    return tc.linter.release_messages()


# ── T1-pyi-exemption layout rows ──

_PYI_EXEMPT_LOG_LAYOUT_CASES: list[Any] = [
    _p("init", "from .sub import Foo\n", "Exempt mypkg: __init__.py", id="init_exempt_logs_record"),
    _p("main", "\ndef run():\n    pass\nif __name__ == '__main__':\n    run()\n", "Exempt script: standalone", id="main_exempt_logs_record"),
    _p("conftest", "import pytest\n", "Exempt conftest_root: conftest.py", id="conftest_exempt_logs_record"),
    _p("trivial_data", "x = 1\ny = 'hello'\n", "Exempt tests.data.fixture_data: trivial test data", id="trivial_test_data_exempt_logs_record"),
]


def materialize_pyi_exempt_layout(
    tmp_path: Path,
    layout_kind: str,
    code: str,
) -> tuple[str, list[str], str]:
    src = tmp_path / "src"
    if layout_kind == "init":
        pkg = src / "mypkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text(code)
        return str(pkg / "__init__.py"), [str(src)], "mypkg"
    if layout_kind == "main":
        src.mkdir()
        (src / "script.py").write_text(code)
        return str(src / "script.py"), [str(src)], "script"
    if layout_kind == "conftest":
        src.mkdir()
        (src / "conftest.py").write_text(code)
        return str(src / "conftest.py"), [str(src)], "conftest_root"
    if layout_kind == "trivial_data":
        data_dir = tmp_path / "tests" / "data"
        data_dir.mkdir(parents=True)
        data_file = data_dir / "fixture_data.py"
        data_file.write_text(code)
        return str(data_file), [str(tmp_path / "src")], "tests.data.fixture_data"
    raise ValueError(f"unknown layout_kind {layout_kind!r}")


# ── stub_checker: import-contract / star-policy state builders ──


def _build_star_import_policy_state(star_policy: str, import_usage_factory: Any) -> tuple[CheckerTestCase, StubChecker]:
    from python_setup_lint.checkers.stub_checker import StubChecker

    mock_b = MagicMock()
    mock_b.name = "mod_b"
    mock_b.position = None
    mock_a = MagicMock()
    mock_a.name = "mod_a"
    mock_a.position = None
    tc = _make_tc_factory(StubChecker)
    tc.checker._coverage.module_index = {
        "mod_a": (Path("/workspace/src/mod_a.py"), mock_a),
        "mod_b": (Path("/workspace/src/mod_b.py"), mock_b),
    }
    tc.checker._coverage.stub_index = {"mod_b": Path("/workspace/src/mod_b.pyi")}
    tc.checker._coverage.star_import_policy = star_policy
    tc.checker._coverage.import_usages = [import_usage_factory()]
    return tc, tc.checker


def _star_usage_factory() -> ImportUsage:
    from python_setup_lint.checkers.stub_import_contract import ImportUsage
    return ImportUsage("mod_a", 1, "mod_b", "*", None, True)


# ── stub_checker: .pyi companion-resolution ──

_STUB_RESOLUTION_CASES: list[Any] = [
    _p("inline", "x = 1\n", "has_stub", 0, id="inline_stub_detected"),
    _p("package", "x = 1\n", "mypkg", 0, id="package_init_stub_detected"),
    _p("stub_root", "x = 1\n", "foo", 0, id="stub_root_resolution"),
    _p("no_stub", "y = 2\n", "unstubbed", 1, id="missing_stub_emits_e97a0"),
    _p("empty", "", "", 0, id="no_stub_no_error_on_empty"),
]


def walk_stub_resolution_layout(
    tmp_path: Path,
    layout_kind: str,
    code: str,
    module_name: str,
) -> list:
    from python_setup_lint.checkers.stub_checker import StubChecker

    tc = _make_tc_factory(StubChecker)
    if layout_kind == "empty":
        tc.checker.open()
        tc.checker.close()
        return tc.linter.release_messages()
    src = tmp_path / "src"
    src.mkdir()
    tc.linter.config.source_roots = [str(src)]
    py_file = src / f"{module_name}.py"
    pyi_file: Path | None = None
    if layout_kind == "package":
        pkg = src / module_name
        pkg.mkdir(parents=True)
        py_file = pkg / "__init__.py"
        pyi_file = pkg / "__init__.pyi"
    elif layout_kind == "stub_root":
        stub_root = tmp_path / "stubs"
        stub_root.mkdir()
        pyi_file = stub_root / f"{module_name}.pyi"
        tc.linter.config.stub_roots = [str(stub_root)]
    elif layout_kind == "inline":
        pyi_file = src / f"{module_name}.pyi"
    py_file.write_text(code)
    if pyi_file is not None:
        pyi_file.write_text("x: int\n")
    tc.checker.open()
    module = astroid.parse(code, module_name=module_name)
    module.file = str(py_file)
    tc.walk(module)
    tc.checker.close()
    return tc.linter.release_messages()


# ── stub_coverage: _resolve_stub layout ──

_RESOLVE_STUB_CASES: list[Any] = [
    _p("inline", "returns_pyi", id="inline_stub"),
    _p("package", "returns_pyi", id="package_init_stub"),
    _p("no_stub", "returns_none", id="no_stub_returns_none"),
    _p("stub_root", "returns_pyi", id="stub_root_resolution"),
]


def materialize_resolve_stub_layout(tmp_path: Path, layout_kind: str) -> tuple:
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

_EMIT_COVERAGE_CASES: list[Any] = [
    _p("in_index", "mod_a", 1, id="one_missing_module"),
    _p("no_missing", "", 0, id="no_missing_emits_nothing"),
    _p("skip_module_not_in_index", "ghost_module", 0, id="skip_module_not_in_index"),
]


def make_emit_coverage_state(
    tmp_path: Path, setup_kind: str, stub_missing_module: str
) -> tuple[CheckerTestCase, MagicMock]:
    from python_setup_lint.checkers.stub_checker import StubChecker

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


# ── shared subprocess-integration helpers ──


def _run_pylint(
    tmp_path: Path,
    mod_py: str,
    mod_pyi: str,
    enable: str,
    *,
    project_src: Path,
) -> str:
    import os
    import subprocess
    import sys

    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "__init__.pyi").write_text("")
    (src / "mod_a.py").write_text(mod_py)
    (src / "mod_a.pyi").write_text(mod_pyi)
    (tmp_path / "pyproject.toml").write_text(
        f"""\
[tool.pylint.MASTER]
load-plugins = "python_setup_lint.checkers.stub_checker"

[tool.pylint.stub-checker]
source-roots = ["{src}"]
"""
    )
    env = {**os.environ, "PYTHONPATH": str(project_src)}
    result = subprocess.run(
        [sys.executable, "-m", "pylint", str(src), "--disable=all", f"--enable={enable}"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
        check=False,
    )
    return result.stdout + result.stderr


# ── class-fidelity end-to-end rows ──

_CLASS_FIDELITY_INTEGRATION_CASES: list[Any] = [
    _p("x: int = 1\n", "\nx: int\nclass Foo: ...\n", "stub-symbol-missing", "E97B1", id="integration_stub_symbol_missing"),
    _p("Foo: int = 1\n", "class Foo: ...\n", "symbol-kind-mismatch", "E97B2", id="integration_kind_mismatch"),
    _p("\nclass Foo:\n    x: int = 1\n", "\nclass Foo(BaseModel):\n    x: int\n", "annotation-mismatch", "E97B4", id="integration_base_class_mismatch"),
    _p("x: str = 'hello'\n", "x: int\n", "annotation-mismatch", "E97B4", id="integration_variable_annotation_mismatch"),
    _p("x = 1\n", "x: int\n", "impl-missing-annotation", "W97B5", id="integration_impl_missing_annotation"),
]

_CALLABLE_FIDELITY_INTEGRATION_CASES: list[Any] = [
    _p("\ndef foo(x: int, y: str) -> None: ...\n", "\ndef foo(x: int) -> None: ...\n", "signature-mismatch", "E97B3", id="signature_mismatch"),
    _p("\ndef foo() -> int: ...\n", "\ndef foo() -> str: ...\n", "annotation-mismatch", "E97B4", id="return_annotation_mismatch"),
]


# ── stub_class: shared walk-with-pair helper ──


def walk_stub_checker_with_pair(
    tmp_path: Path,
    py_code: str,
    pyi_code: str,
    module_name: str = "mod_a",
) -> list:
    from python_setup_lint.checkers.stub_checker import StubChecker

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


# ── stub_checker: import-contract setup helper ──


def setup_and_emit_import_contract(
    *,
    target_module: str,
    has_stub: bool,
    declared_symbols: set[str] | None,
    importer: str,
    symbol: str | None,
    is_star: bool,
    star_policy: str | None,
) -> tuple[CheckerTestCase, list]:
    from python_setup_lint.checkers.stub_import_contract import (
        ImportUsage,
        emit_import_contract_violations,
    )

    target_path_str = f"/workspace/src/{target_module}.py"
    target_node = MagicMock()
    target_node.name = target_module
    module_index = {target_module: (Path(target_path_str), target_node)}
    stub_index = (
        {target_module: Path(f"/workspace/src/{target_module}.pyi")} if has_stub else {}
    )
    declaration_index = (
        {target_module: declared_symbols} if declared_symbols is not None else {}
    )
    import_usages = [ImportUsage(importer, 1, target_module, symbol, None, is_star)]
    checker, _tc = build_import_contract_state(
        module_index=module_index,
        stub_index=stub_index,
        declaration_index=declaration_index,
        import_usages=import_usages,
    )
    if star_policy is not None:
        checker._coverage.star_import_policy = star_policy
    emit_import_contract_violations(checker)
    return _tc, _tc.linter.release_messages()


# ── stub_checker: registered message codes ──

_STUB_CHECKER_MSGS_CASES: list[Any] = [
    _p("E97A0", "missing-module-stub", id="E97A0"),
    _p("E97A1", "missing-import-declaration", id="E97A1"),
    _p("E97A2", "missing-module-stub-for-import", id="E97A2"),
    _p("E97A3", "star-import-unresolvable", id="E97A3"),
]
