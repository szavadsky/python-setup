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

from python_setup_lint.testing import _make_tc as _make_tc_factory

if TYPE_CHECKING:
    from pylint.checkers import BaseChecker

# ── Generic message helpers ────────────────────────────────────────


def make_tc(checker_class: type[BaseChecker]) -> Any:
    """Create a ``CheckerTestCase`` for *checker_class* (thin wrapper over
    ``python_setup_lint.testing._make_tc``)."""
    return _make_tc_factory(checker_class)  # type: ignore[no-untyped-call]


# (The ``parse_module`` / ``msg_ids`` / ``filter_msgs`` / ``count_msg``
# helpers were drafted for callers filtering on msg_id strings; the live
# test bodies inline their filter expressions directly, so they were
# removed to keep the module lean.)


# ── no-try-import checker: parametrise tables ───────────────────────

# Each row is ``(src, expected_count, expected_args)``. The checker walks the
# code and counts emitted ``no-try-import`` messages; rows assert the count
# and (optionally) the first message's args tuple.
_NO_TRY_DETECT_CASES: list[Any] = [
    pytest.param(
        "try:\n    import litellm\nexcept ImportError:\n    pass\n",
        1,
        ("ImportError",),
        id="import_in_try_except_importerror",
    ),
    pytest.param(
        "try:\n    import litellm\nexcept ModuleNotFoundError:\n    pass\n",
        1,
        (),
        id="import_in_try_except_modulenotfound",
    ),
    pytest.param(
        "try:\n    from pydantic import ValidationError\nexcept ImportError:\n    pass\n",
        1,
        (),
        id="from_import_in_try_except_importerror",
    ),
    pytest.param(
        "try:\n    import httpx\nexcept:\n    pass\n",
        1,
        ("bare except",),
        id="import_in_try_bare_except",
    ),
    pytest.param(
        "try:\n    import litellm\nexcept (ImportError, ModuleNotFoundError):\n    pass\n",
        1,
        (),
        id="import_in_try_tuple_import_errors",
    ),
    pytest.param(
        "try:\n    import litellm\nexcept ImportError:\n    pass\n\n"
        "try:\n    import httpx\nexcept ImportError:\n    pass\n",
        2,
        (),
        id="two_imports_separate_try_blocks",
    ),
    pytest.param(
        "try:\n    import litellm\nexcept ImportError:\n    pass\n"
        "except ModuleNotFoundError:\n    pass\n",
        2,
        (),
        id="two_imports_separate_handlers_one_try",
    ),
    pytest.param(
        # not flagged: ImportError handler absent; ValueError does NOT trigger.
        "try:\n    import litellm\nexcept ValueError:\n    pass\n",
        0,
        (),
        id="import_in_try_non_import_handler_not_flagged",
    ),
    pytest.param(
        # only the ImportError handler counts; ValueError/OSError handlers are ignored.
        "try:\n    import httpx\nexcept ValueError:\n    pass\n"
        "except ImportError:\n    pass\nexcept OSError:\n    pass\n",
        1,
        (),
        id="handler_mixed_import_and_non_import",
    ),
    pytest.param(
        # proxy module-level guard pattern IS flagged (no opt-out in this checker).
        "try:\n    import litellm as _litellm\nexcept ImportError:\n    _litellm = None\n",
        1,
        (),
        id="proxy_module_level_guard",
    ),
]


_NO_TRY_DO_NOT_DETECT_CASES: list[Any] = [
    pytest.param(
        "try:\n    x = 1 / 0\nexcept ZeroDivisionError:\n    pass\n",
        id="try_without_import",
    ),
    pytest.param(
        "import os\nx = os.path.join('a', 'b')\n",
        id="import_outside_try",
    ),
    pytest.param(
        "",
        id="empty_module",
    ),
    pytest.param(
        "try:\n    result = api_call()\nexcept ConnectionError:\n    result = None\n",
        id="non_import_exception_handling",
    ),
]


# ── beartype checker: parametrise tables ────────────────────────────

# Rows: ``(src, expected_msg_count, expected_first_arg)`` for the
# ``missing-beartype`` verdict. ``expected_first_arg=None`` skips the
# args[0] check (used only for module-level functions, where args[0] is
# the function name not a method label).
_BEARTYPE_MISS_CASES: list[Any] = [
    pytest.param("def foo(): pass", 1, None, id="plain_def"),
    pytest.param("async def foo(): pass", 1, None, id="async_def"),
    pytest.param(
        "class X:\n    def method(self): pass", 1, "method", id="public_method_in_class"
    ),
    pytest.param(
        "def foo(): pass\ndef bar(): pass\n", 2, None, id="multiple_public_functions"
    ),
]

# Rows: ``(src, file_path, expected_count)`` — file under or outside the
# ``BeartypeCoverageChecker`` source root default ``src/``.
_BEARTYPE_SOURCE_ROOT_CASES: list[Any] = [
    pytest.param("def foo(): pass", "tests/test_mod.py", 0, id="outside_source_root"),
    pytest.param("def foo(): pass", "src/prod.py", 1, id="under_source_root"),
]

# Rows: ``(src, expected_missing_count)`` — these code segments must NOT
# trigger ``missing-beartype``.
_BEARTYPE_SKIP_CASES: list[Any] = [
    pytest.param("def _helper(): pass", 0, id="private_function"),
    pytest.param(
        "def public(): pass\ndef _private(): pass\n", 1, id="mixed_public_and_private"
    ),
    pytest.param("class X:\n    def __init__(self): pass", 0, id="init_skipped"),
    pytest.param("class X:\n    def __str__(self): pass", 0, id="str_skipped"),
    pytest.param(
        "class X:\n    def __init__(self): pass\n    def run(self): pass",
        1,
        id="dunder_only_init_skipped_then_public",
    ),
]


# ── stub normalizer: parametrise tables ─────────────────────────────

# Rows: ``(code, field, expected)`` where ``field`` is ``"annotation"`` or
# ``"returns"`` to extract from a parsed ``x: <ann>`` module body[0]. The
# normalizer is exercised via ``AnnotationNormalizer.normalize`` or
# ``AnnotationNormalizer._ast_string`` depending on the row's ``method``.
_NORMALIZER_INFER_CASES: list[Any] = [
    pytest.param("x: str", "str", id="infer_simple_name"),
    pytest.param("x: list[int]", "list[int]", id="infer_builtin_list"),
    pytest.param("x: str | None", "str | None", id="infer_native_union"),
    # forward-ref string returns non-None (inference succeeds at parse time)
    pytest.param("x: 'SomeFutureType'", None, id="infer_uninferable_returns_non_null"),
]


# ── stub checker: parametrise tables ────────────────────────────────


# (file_path, source_roots, test_patterns, stub_opt_out, expected_e97a0_count)
# — all rows run code ``x = 1\n`` (irrelevant: classification-only).
_STUB_FILE_CLASSIFICATION_CASES: list[Any] = [
    pytest.param(
        "/workspace/tests/test_foo.py",
        ["/workspace/src"],
        None,
        None,
        0,
        id="test_file_in_tests_dir",
    ),
    pytest.param(
        "/workspace/src/test_example.py",
        ["/workspace/src"],
        ["test_*.py", "tests/"],
        None,
        0,
        id="test_file_named_test_prefixed",
    ),
    pytest.param(
        "/workspace/other/foo.py",
        ["/workspace/src"],
        None,
        None,
        0,
        id="file_outside_source_root_skipped",
    ),
    pytest.param(
        "/workspace/src/generated/foo.py",
        ["/workspace/src"],
        None,
        ["src/generated/"],
        0,
        id="opted_out_by_directory",
    ),
    pytest.param(
        "/workspace/src/vendor/external.py",
        ["/workspace/src"],
        None,
        ["src/vendor/"],
        0,
        id="opted_out_by_filename",
    ),
]


# Rows for ``TestResolveRelative``: ``(modname, level, name, is_package, expected)``
_RESOLVE_RELATIVE_CASES: list[Any] = [
    pytest.param("mod_a", 0, "os", False, "os", id="absolute_import"),
    pytest.param("mod_a", 0, None, False, "", id="absolute_no_modname"),
    pytest.param("mypkg", 1, None, True, "mypkg", id="same_package_init"),
    pytest.param(
        "mypkg", 1, "mod_a", True, "mypkg.mod_a", id="same_package_init_with_name"
    ),
    pytest.param("mypkg.mod_a", 2, "sibling", False, "sibling", id="parent_package"),
    pytest.param("pkg.sub.mod_a", 3, "other", False, "other", id="grandparent_package"),
    pytest.param("mod_a", 3, "other", True, "other", id="level_exceeds_depth"),
]


# Rows: ``(code_to_parse, accessor_path, expected)`` — the ``accessor_path``
# is a list of attribute chains or list indices to walk into the parsed
# module's body[0]. Each row exercises ``_is_type_checking_guard`` boolean
# outcome (True/False expected).
#
# Simpler form below: ``(node_src, expected)`` where the parsed module's
# body[0].value is the operand. Used for both Name and Attribute forms.
_IS_TYPE_CHECKING_GUARD_CASES: list[Any] = [
    pytest.param("TYPE_CHECKING", True, id="name_form"),
    pytest.param("typing.TYPE_CHECKING", True, id="typing_dot_name"),
    pytest.param("SOME_FLAG", False, id="other_name"),
    pytest.param("os.name", False, id="other_attribute"),
]


# ``(code, accessor)`` — accessor returns the import astroid node relative to
# ``astroid.parse(code)``. Used by both ``_in_type_checking_block`` positive
# and negative tests.
_IN_TYPE_CHECKING_BLOCK_POSITIVE_CASES: list[Any] = [
    pytest.param(
        "if TYPE_CHECKING:\n    from foo import Bar\n",
        lambda m: m.body[0].body[0],
        id="under_type_checking",
    ),
    pytest.param(
        "if TYPE_CHECKING:\n    if True:\n        from foo import Bar\n",
        lambda m: m.body[0].body[0].body[0],
        id="nested_inside_type_checking",
    ),
]

_IN_TYPE_CHECKING_BLOCK_NEGATIVE_CASES: list[Any] = [
    pytest.param(
        "from foo import Bar\n",
        lambda m: m.body[0],
        id="not_under_type_checking",
    ),
]


# ── stub coverage helper tests: parametrise tables ───────────────────

# ``_matches_path`` rows: ``(path, patterns, expected)``.
_MATCHES_PATH_CASES: list[Any] = [
    pytest.param("/workspace/src/foo.py", [], False, id="empty_patterns_returns_false"),
    pytest.param(
        "src/generated/foo.py", ["src/generated/"], True, id="directory_prefix_match"
    ),
    pytest.param(
        "/workspace/src/generated/foo.py",
        ["src/generated/"],
        True,
        id="directory_prefix_with_leading_slash",
    ),
    pytest.param(
        "/workspace/src/handwritten/foo.py",
        ["src/generated/"],
        False,
        id="directory_prefix_no_match",
    ),
    pytest.param(
        "/workspace/src/test_example.py", ["test_*.py"], True, id="fnmatch_full_path"
    ),
    pytest.param(
        "/workspace/src/foo/bar_test.py", ["*_test.py"], True, id="fnmatch_basename"
    ),
    pytest.param("/workspace/src/prod.py", ["test_*.py"], False, id="fnmatch_no_match"),
    pytest.param(
        "src\\generated\\foo.py", ["src\\generated\\"], True, id="backslash_pattern"
    ),
    pytest.param(
        "/workspace/tests/test_foo.py",
        ["tests/", "test_*.py", "*_test.py"],
        True,
        id="multiple_patterns_any_match",
    ),
    pytest.param(
        "/workspace/src/prod.py",
        ["tests/", "test_*.py"],
        False,
        id="multiple_patterns_none_match",
    ),
]


# ``_is_test_file`` rows: ``(path, test_patterns, expected)``.
_DEFAULT_TEST_PATTERNS = ["tests/", "test_*.py", "*_test.py", "conftest.py"]
_IS_TEST_FILE_CASES: list[Any] = [
    pytest.param(
        "/workspace/tests/test_foo.py",
        _DEFAULT_TEST_PATTERNS,
        True,
        id="tests_dir_match",
    ),
    pytest.param(
        "/workspace/src/test_example.py",
        _DEFAULT_TEST_PATTERNS,
        True,
        id="test_prefixed_filename",
    ),
    pytest.param(
        "/workspace/src/foo_test.py",
        _DEFAULT_TEST_PATTERNS,
        True,
        id="suffixed_filename",
    ),
    pytest.param(
        "/workspace/src/conftest.py", _DEFAULT_TEST_PATTERNS, True, id="conftest"
    ),
    pytest.param(
        "/workspace/src/prod.py",
        _DEFAULT_TEST_PATTERNS,
        False,
        id="production_file_not_test",
    ),
]
# Custom-pattern split (must come before the default-pattern class uses it; the
# default-pattern list above is named inline so each row is self-contained).
_IS_TEST_FILE_CUSTOM_CASES: list[Any] = [
    # patterns=['specs/'] matches specs/ but NOT tests/
    pytest.param(
        "/workspace/specs/test_foo.py", ["specs/"], True, id="custom_pattern_matches"
    ),
    pytest.param(
        "/workspace/tests/test_foo.py",
        ["specs/"],
        False,
        id="custom_pattern_excludes_tests",
    ),
]


# ``_is_opted_out`` rows: ``(path, opt_out_patterns, expected)``.
_IS_OPTED_OUT_CASES: list[Any] = [
    pytest.param(
        "/workspace/src/generated/foo.py",
        ["src/generated/"],
        True,
        id="opted_out_by_directory",
    ),
    pytest.param(
        "/workspace/src/handwritten/foo.py",
        ["src/generated/"],
        False,
        id="not_opted_out",
    ),
    pytest.param(
        "/workspace/src/vendor_foo.py",
        ["vendor_*.py"],
        True,
        id="opted_out_by_filename",
    ),
    pytest.param("/workspace/src/foo.py", [], False, id="empty_opt_out"),
]


# ``_is_init_exempt`` rows: ``(code, expected)``.
_IS_INIT_EXEMPT_CASES: list[Any] = [
    pytest.param("", True, id="empty_body_exempt"),
    pytest.param("from .sub import Foo\nimport os\n", True, id="only_imports_exempt"),
    pytest.param("__all__ = ['Foo', 'Bar']\n", True, id="all_assignment_exempt"),
    pytest.param(
        "def __getattr__(name): ...\n", False, id="getattr_defined_not_exempt"
    ),
    pytest.param("def helper(): pass\n", False, id="function_def_not_exempt"),
    pytest.param("class Helper: pass\n", False, id="class_def_not_exempt"),
    pytest.param("setup(name='foo')\n", False, id="standalone_expression_not_exempt"),
    pytest.param("x = 1\n", False, id="non_all_assignment_not_exempt"),
    pytest.param("x: int = 1\n", False, id="ann_assign_not_exempt"),
    pytest.param(
        "import os\nif os.name == 'nt':\n    x = 1\n", False, id="if_block_not_exempt"
    ),
]


# ``_is_trivial_test_data`` rows: ``(code, expected)``.
_IS_TRIVIAL_TEST_DATA_CASES: list[Any] = [
    pytest.param("", True, id="empty_module_trivial"),
    pytest.param(
        "x = 1\ny = 'hello'\nz = 3.14\n", True, id="literal_assignments_trivial"
    ),
    pytest.param("def helper(): pass\n", False, id="function_def_not_trivial"),
    pytest.param("class Data: pass\n", False, id="class_def_not_trivial"),
    pytest.param("import os\n", False, id="import_not_trivial"),
    pytest.param("1 + 1\n", False, id="expression_not_trivial"),
    pytest.param("x = 1\nif True:\n    y = 2\n", False, id="if_block_not_trivial"),
]


# ``_has_main_block`` rows: ``(code, expected)``.
_HAS_MAIN_BLOCK_CASES: list[Any] = [
    pytest.param("if __name__ == '__main__':\n    main()\n", True, id="double_equals"),
    pytest.param('if __name__ == "__main__":\n    main()\n', True, id="double_quotes"),
    pytest.param("def foo(): pass\n", False, id="no_main_block"),
    pytest.param(
        "if __name__ != '__main__':\n    pass\n", False, id="different_condition"
    ),
    pytest.param("", False, id="empty_module"),
]


# ``_is_under_source_root`` rows: ``(path, source_roots, expected)``.
_IS_UNDER_SOURCE_ROOT_CASES: list[Any] = [
    pytest.param(
        "/workspace/src/prod.py", ["/workspace/src"], True, id="path_under_root"
    ),
    pytest.param(
        "/workspace/tests/foo.py", ["/workspace/src"], False, id="path_not_under_root"
    ),
    pytest.param(
        "/workspace/lib/foo.py",
        ["/workspace/src", "/workspace/lib"],
        True,
        id="multiple_roots",
    ),
]


# ── stub_callable parametrise: extract param descriptors ────────────

# Rows: ``(func_src, expected_names, expected_kinds)`` — kinds matched by
# inspecting positions in `expected_kinds` against the extracted list.
_EXTRACT_PARAM_CASES: list[Any] = [
    pytest.param("def foo() -> None: ...", [], [], id="empty_function"),
    pytest.param(
        "def foo(a, b, /) -> None: ...",
        ["a", "b"],
        [inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_ONLY],
        id="positional_only",
    ),
    pytest.param(
        "def foo(a, b) -> None: ...",
        ["a", "b"],
        [
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ],
        id="positional_or_keyword",
    ),
    pytest.param(
        "def foo(*args) -> None: ...",
        ["args"],
        [inspect.Parameter.VAR_POSITIONAL],
        id="var_positional",
    ),
    pytest.param(
        "def foo(*, x, y) -> None: ...",
        ["x", "y"],
        [inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.KEYWORD_ONLY],
        id="keyword_only",
    ),
    pytest.param(
        "def foo(**kwargs) -> None: ...",
        ["kwargs"],
        [inspect.Parameter.VAR_KEYWORD],
        id="var_keyword",
    ),
]


# Rows for default-presence detection: ``(func_src, expected_per_param_defaults)``
_EXTRACT_DEFAULT_CASES: list[Any] = [
    pytest.param(
        "def foo(a, b=1) -> None: ...", [False, True], id="default_presence_detected"
    ),
    pytest.param(
        "def foo(*, x, y='hello') -> None: ...",
        [False, True],
        id="default_presence_kwonly",
    ),
]


# Rows: ``(func_src, strip_self, expected_names)`` — exercises ``strip_self`` of
# ``_extract_param_descriptors``.
_EXTRACT_STRIP_SELF_CASES: list[Any] = [
    pytest.param("def bar(self, x, y) -> None: ...", True, ["x", "y"], id="strip_self"),
    pytest.param("def bar(cls, x, y) -> None: ...", True, ["x", "y"], id="strip_cls"),
    # non-method (no self/cls) → strip_self is a no-op
    pytest.param(
        "def bar(a, b) -> None: ...", True, ["a", "b"], id="no_strip_non_method"
    ),
]


# Rows: ``(func_src, needle_in_first_normalized, needle_in_second_normalized)`` —
# exercises annotation extraction; only verifies substrings present.
_EXTRACT_ANNOTATION_CASES: list[Any] = [
    pytest.param(
        "def foo(x: int, y: str | None) -> None: ...",
        "int",
        None,
        id="annotations_extracted",
    ),
    pytest.param(
        "def foo(*args: int) -> None: ...", "int", None, id="vararg_annotation"
    ),
    pytest.param(
        "def foo(**kwargs: str) -> None: ...", "str", None, id="kwarg_annotation"
    ),
]


# ── stub_callable: compare descriptors ──────────────────────────────


# Rows: ``(a, b, expected_failure_substr)``. ``None`` expected means matching.
# Each descriptor is built via the ``_desc`` helper at test-time, kept inline
# in the test function as a small builder closure (no shared state needed).
_COMPARE_DESCRIPTOR_CASES: list[Any] = [
    pytest.param(
        # identical params — both [a, b] PO_OR_KW
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
    pytest.param(
        [
            ("a", inspect.Parameter.POSITIONAL_OR_KEYWORD, False),
            ("b", inspect.Parameter.POSITIONAL_OR_KEYWORD, False),
        ],
        [("a", inspect.Parameter.POSITIONAL_OR_KEYWORD, False)],
        "param_count",
        id="param_count_mismatch",
    ),
    pytest.param(
        [("a", inspect.Parameter.POSITIONAL_OR_KEYWORD, False)],
        [("b", inspect.Parameter.POSITIONAL_OR_KEYWORD, False)],
        "param_name",
        id="param_name_mismatch",
    ),
    pytest.param(
        [("x", inspect.Parameter.POSITIONAL_OR_KEYWORD, False)],
        [("x", inspect.Parameter.KEYWORD_ONLY, False)],
        "param_kind",
        id="param_kind_mismatch",
    ),
    pytest.param(
        [("x", inspect.Parameter.POSITIONAL_OR_KEYWORD, True)],
        [("x", inspect.Parameter.POSITIONAL_OR_KEYWORD, False)],
        "param_default",
        id="default_presence_mismatch",
    ),
    pytest.param([], [], None, id="empty_lists"),
]


# Rows: ``(a_ann, b_ann, expected_mismatch_count, expected_first_arg_name)``.
# ParamDescriptor(name, kind=PO_OR_KW, has_default=False, annotation_normalized=ann).
_COMPARE_ANNOTATION_CASES: list[Any] = [
    pytest.param(["int", "str"], ["int", "str"], 0, None, id="all_match_returns_empty"),
    pytest.param(
        ["int", "str"], ["int", "int"], 1, "y", id="param_annotation_mismatch_detected"
    ),
    pytest.param([None], ["int"], 0, None, id="skips_missing_annotations"),
    pytest.param([None], [None], 0, None, id="skips_no_annotation_on_both"),
]


# Rows: ``(stub_src, impl_src, assert_mode, expected_eq)`` — uses parsed
# "def foo() -> <ann>: ..." returns. ``assert_mode`` selects the postcondition
# branch in the test body:
#   - ``"skip_both_none"``: when at least one side is None the comparison
#     MUST return ``(None, None)`` (the skip path).
#   - ``"compare"``: both sides are non-None — the body asserts both are not
#     None and verifies the ``stub == impl`` outcome against ``expected_eq``.
_COMPARE_RETURN_CASES: list[Any] = [
    pytest.param(None, None, "skip_both_none", True, id="both_none"),
    pytest.param(None, "int", "skip_both_none", True, id="stub_none_skipped"),
    pytest.param("int", None, "skip_both_none", True, id="impl_none_skipped"),
    pytest.param("int", "int", "compare", True, id="matching_returns"),
    pytest.param("str", "int", "compare", False, id="mismatched_returns"),
    pytest.param(
        "typing.List[int]", "list[int]", "compare", True, id="normalized_typing"
    ),
]


# ── stub_class fidelity parametrise: _normalize_bases ───────────────

# Rows: ``(class_src, expected_substrings)`` — exercises ``_normalize_bases``.
_NORMALIZE_BASES_CASES: list[Any] = [
    pytest.param("class Foo(BaseModel): ...\n", ["BaseModel"], id="simple_name"),
    pytest.param(
        "class Foo(pydantic.BaseModel): ...\n", ["BaseModel"], id="attribute_base"
    ),
    pytest.param("class Foo(object): ...\n", ["builtins.object"], id="builtins_object"),
    # multiple bases returned sorted
    pytest.param(
        "class Foo(B, A, C): ...\n", ["A", "B", "C"], id="multiple_bases_sorted"
    ),
    pytest.param("class Foo(Generic[T]): ...\n", ["Generic"], id="subscript_base"),
]


# ``_is_public_method`` rows: ``(name, expected)``.
_IS_PUBLIC_METHOD_CASES: list[Any] = [
    pytest.param("foo", True, id="plain_name"),
    pytest.param("_helper", False, id="private_name"),
    pytest.param("__str__", False, id="dunder_str"),
    pytest.param("__init__", True, id="init"),
    pytest.param("__new__", True, id="new"),
    pytest.param("__repr__", False, id="repr"),
]


# ── stub_class: E97B1 / E97B2 parametrise ────────────────────────────

# ``(py_code, pyi_code, msg_id, expected_count, name_in_args)`` rows.
_STUB_SYMBOL_MISSING_CASES: list[Any] = [
    pytest.param(
        "x: int = 1\n",
        "x: int\nclass Foo: ...\n",
        "stub-symbol-missing",
        1,
        "Foo",
        id="stub_class_missing_from_impl",
    ),
    pytest.param(
        "x: int = 1\n",
        "x: int\ndef foo(): ...\n",
        "stub-symbol-missing",
        1,
        "foo",
        id="stub_func_missing_from_impl",
    ),
    pytest.param(
        "x: int = 1\n",
        "x: int\ny: str\n",
        "stub-symbol-missing",
        1,
        "y",
        id="stub_var_missing_from_impl",
    ),
]
_KIND_MISMATCH_CASES: list[Any] = [
    pytest.param(
        "Foo: int = 1\n",
        "class Foo: ...\n",
        "symbol-kind-mismatch",
        id="stub_class_impl_var",
    ),
    pytest.param(
        "foo: int = 1\n",
        "def foo(): ...\n",
        "symbol-kind-mismatch",
        id="stub_func_impl_var",
    ),
    pytest.param(
        "def Foo(): ...\n",
        "class Foo: ...\n",
        "symbol-kind-mismatch",
        id="stub_class_impl_func",
    ),
    pytest.param(
        "class Foo: ...\n",
        "Foo: int\n",
        "symbol-kind-mismatch",
        id="stub_var_impl_class",
    ),
]


# ── stub docstring checker parametrise ──────────────────────────────

# ``(code, expected_docstring_in_impl_count)`` — exercises cases where NO
# companion .pyi exists (so the checker emits nothing).
_DOCSTRING_NO_COMPANION_CASES: list[Any] = [
    pytest.param(
        'def foo():\n    """My docstring."""\n    pass\n',
        0,
        id="no_companion_plain_func",
    ),
    pytest.param(
        'async def foo():\n    """My docstring."""\n    pass\n',
        0,
        id="no_companion_async_func",
    ),
    # note: triple-quote inside class is split across lines
    pytest.param(
        'class MyClass:\n    def method(self):\n        """Method doc."""\n        pass\n',
        0,
        id="no_companion_method",
    ),
]

# Negative detection rows: ``docstring-in-impl`` must NOT fire.
_DOCSTRING_DOES_NOT_DETECT_CASES: list[Any] = [
    pytest.param("def foo():\n    pass\n", id="no_docstring_no_message"),
    pytest.param("def foo():\n    ...\n", id="empty_body_no_message"),
    pytest.param(
        'class MyClass:\n    """Class-level docs."""\n    pass\n',
        id="class_docstring_no_message",
    ),
    pytest.param("def foo():\n    42\n    pass\n", id="non_string_first_expr"),
]


# Rows: ``(code, expected_count, expected_args1)`` — exercises cases where a
# companion .pyi exists and W9700 emits.
_DOCSTRING_DETECT_CASES: list[Any] = [
    pytest.param(
        'def foo():\n    """Usage docstring."""\n    pass\n',
        1,
        "foo",
        id="function_docstring_detected",
    ),
    pytest.param(
        'async def foo():\n    """Usage docstring."""\n    pass\n',
        1,
        None,
        id="async_function_docstring_detected",
    ),
    pytest.param(
        'class MyClass:\n    def method(self):\n        """Method doc."""\n        pass\n',
        1,
        "method",
        id="method_docstring_detected",
    ),
    pytest.param(
        'def foo():\n    """Doc."""\n    pass\n\ndef bar():\n    pass\n',
        1,
        None,
        id="mixed_docstrings_and_no_docstrings",
    ),
]


# ── stub-fidelity rewrite-table (AnnotationNormalizer._apply_rewrites) ──

# ``(input, expected)`` rows.
_APPLY_REWRITES_CASES: list[Any] = [
    pytest.param("typing.List[str]", "list[str]", id="rewrite_typing_list"),
    pytest.param("typing.Dict[str, int]", "dict[str, int]", id="rewrite_typing_dict"),
    pytest.param("typing.Optional[str]", "str | None", id="rewrite_typing_optional"),
    pytest.param("typing.Union[str, int]", "str | int", id="rewrite_typing_union"),
    pytest.param(
        "typing.Union[list[str], int]",
        "list[str] | int",
        id="rewrite_typing_union_nested_generic",
    ),
    pytest.param(
        "collections.abc.Callable",
        "collections.abc.Callable",
        id="rewrite_no_match_passes_through",
    ),
]


# ``_split_outer_commas`` rows: ``(input, expected_parts)``.
_SPLIT_OUTER_COMMAS_CASES: list[Any] = [
    pytest.param("str, int, float", ["str", "int", "float"], id="simple"),
    pytest.param("list[str], int", ["list[str]", "int"], id="with_brackets"),
]


# ── AnnotationNormalizer._ast_string — rows ────────────────────────

# ``(code, expected, assert_mode)`` — exercises the AST-string walker.
# - ``assert_mode == "not_none"``: body asserts ``result is not None``.
# - ``assert_mode == "equals"``: body asserts ``result == expected[0]``.
# - ``assert_mode == "contains"``: body asserts each substring in ``expected``
#   is present in the result (membership check). ``expected`` is a list.
_AST_STRING_CASES: list[Any] = [
    pytest.param("x: list[str]", ["list"], "contains", id="subscript"),
    pytest.param("x: int | str", ["int | str"], "equals", id="binary_op_union"),
    pytest.param(
        "x: typing.Optional[str]", ["typing.Optional"], "contains", id="attribute"
    ),
    pytest.param("x: tuple[int, str]", None, "not_none", id="tuple"),
    pytest.param("x: Literal['hello']", ["hello"], "contains", id="const"),
    pytest.param(
        "x: dict[str, list[int]]", ["dict", "list"], "contains", id="nested_subscript"
    ),
]


# ── stub_coverage: shared fixture for checker construction ───────────


def make_coverage_checker(**config_kwargs) -> tuple:
    """Build a ``StubChecker`` instance with optional config overrides and call
    ``checker.open()`` to initialize state. Mirrors the previous per-test
    ``_make_checker`` helper.

    Returns ``(checker, tc)`` — the test caller can use the test case to access
    the linter for release_messages, or access the checker's ``_coverage``
    attribute directly.
    """
    from pylint.testutils import CheckerTestCase

    from python_setup_lint.checkers.stub_checker import StubChecker

    tc = CheckerTestCase()
    tc.CHECKER_CLASS = StubChecker
    tc.setup_method()
    for key, value in config_kwargs.items():
        setattr(tc.linter.config, key, value)
    tc.checker.open()
    return tc.checker, tc


# ── stub_import_contract helpers: shared build-and-check runner ─────


def build_import_contract_state(
    *,
    module_index: dict | None = None,
    stub_index: dict | None = None,
    declaration_index: dict | None = None,
    import_usages: list | None = None,
) -> tuple:
    """Build a ``StubChecker`` ``_coverage`` state pre-populated with the
    provided indexes/usages (and synthetic mock nodes for importer modules).
    Returns ``(checker, tc)``.
    """
    from unittest.mock import MagicMock

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
        # Ensure importer modules are in module_index so add_message gets a real node
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


def _stub_checker_class() -> type:
    """Late import of ``StubChecker`` (kept out of module top to avoid
    import-time work for test files that don't need it)."""
    from python_setup_lint.checkers.stub_checker import StubChecker

    return StubChecker


# Lazy import of ``ImportUsage`` — kept off module top to avoid coupling.
def import_usage(*args: Any, **kwargs: Any) -> Any:
    """Build an ``ImportUsage`` instance (late import)."""
    from python_setup_lint.checkers.stub_import_contract import ImportUsage

    return ImportUsage(*args, **kwargs)


# ── stub_docstring: shared walker (StubChecker + StubDocstringChecker) ─


def walk_both_release_for_pyi(
    code: str,
    py_path: Path,
    source_roots: list[str] | None = None,
) -> list:
    """Walk StubChecker + StubDocstringChecker together with a companion ``.pyi``.

    Builds a tiny ``# stub`` ``.pyi`` next to *py_path* so docstring detection
    fires (the companion-stub path is what triggers ``W9700`` emission).
    Returns the list of messages released by the linter.
    """
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


# ── stub_checker: import-usage / contract-violations tables ─────────

# ``ImportUsage`` field-echo rows: ``(field_overrides, expected_attr_checks)``.
# Each row asserts a single attribute equals the override value (the test
# body iterates the dict and asserts each key against the field). Rows
# previously existed as 3 narrow `TestImportUsage::test_*` methods.
_IMPORT_USAGE_FIELD_CASES: list[Any] = [
    pytest.param(
        {
            "importer_module": "mod_a",
            "lineno": 5,
            "target_module": "mod_b",
            "symbol_name": "Foo",
            "alias": None,
            "is_star": False,
        },
        {
            "importer_module": "mod_a",
            "lineno": 5,
            "target_module": "mod_b",
            "symbol_name": "Foo",
            "alias": None,
            "is_star": False,
        },
        id="fields",
    ),
    pytest.param(
        {
            "importer_module": "mod_a",
            "lineno": 3,
            "target_module": "mod_b",
            "symbol_name": None,
            "alias": None,
            "is_star": False,
        },
        {"symbol_name": None},
        id="module_import_symbol_name_none",
    ),
    pytest.param(
        {
            "importer_module": "mod_a",
            "lineno": 7,
            "target_module": "mod_b",
            "symbol_name": "*",
            "alias": None,
            "is_star": True,
        },
        {"is_star": True},
        id="star_import_is_star",
    ),
]


# Import-contract violation rows: each row sets up a checker state and
# asserts the post-emit msg count for a single E97A1/E97A2/E97A3 + the
# default "no violation when symbol declared" success case. Each tuple is:
# ``(target_module, has_stub, declared_symbols, importer, symbol,
#   is_star, star_policy, expected_msg_id, expected_count)``.
#
# The test body builds the ImportUsage + the per-target mock node and the
# importer-module mock, then calls ``emit_import_contract_violations``.
_IMPORT_CONTRACT_CASES: list[Any] = [
    # E97A2 — target stub absent (has_stub=False)
    pytest.param(
        "mod_a",
        False,
        None,
        "mod_a",
        "Foo",
        False,
        None,
        "missing-module-stub-for-import",
        1,
        id="e97a2_when_target_no_stub",
    ),
    # E97A1 — symbol absent from stub declarations
    pytest.param(
        "mod_b",
        True,
        {"Foo"},
        "mod_a",
        "Bar",
        False,
        None,
        "missing-import-declaration",
        1,
        id="e97a1_when_symbol_not_declared",
    ),
    # No violation — symbol IS declared
    pytest.param(
        "mod_b",
        True,
        {"Foo"},
        "mod_a",
        "Foo",
        False,
        None,
        None,
        0,
        id="no_violation_when_symbol_declared",
    ),
    # E97A3 — star import when policy='error'
    pytest.param(
        "mod_b",
        True,
        None,
        "mod_a",
        "*",
        True,
        "error",
        "star-import-unresolvable",
        1,
        id="e97a3_star_import",
    ),
]


# ``TestStarImportPolicy`` rows: ``(star_policy, expected_e97a3_count)``.
_STAR_POLICY_CASES: list[Any] = [
    pytest.param("error", 1, id="star_policy_error"),
    pytest.param("ignore", 0, id="star_policy_ignore"),
]


# Variable annotation fidelity rows: ``(expr_src, expected_bool)`` for
# ``_is_classvar`` plus a single AnnotationNormalizer normalize row.
_VARIABLE_FIDELITY_CASES: list[Any] = [
    pytest.param("ClassVar[int]", True, id="classvar_skipped"),
    pytest.param("int", False, id="non_classvar"),
]


# ── stub_checker: shared walk helpers ───────────────────────────────


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
    """Walk ``StubChecker`` open()/walk()/close() over a single module and
    return the released message list.

    Thin wrapper over the ``_make_tc(StubChecker)`` boilerplate the pre-T14
    ``test_stub_checker.py`` redefined privately as
    ``_walk_close_release_with_config`` (now renamed and shared so other
    checker test files can reuse it without forking the helper).
    """
    from python_setup_lint.checkers.stub_checker import StubChecker

    tc = _make_tc_factory(StubChecker)  # type: ignore[no-untyped-call]
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


# T1-pyi-exemption layout rows: ``(layout_kind, code, file_path_seg,
# source_roots_seg, module_name, expected_log_substring)``.
# The test body materialises the tmp_path layout per ``layout_kind``:
#   - "init"         → src/mypkg/__init__.py
#   - "main"         → src/script.py
#   - "conftest"     → src/conftest.py
#   - "trivial_data" → tests/data/fixture_data.py + source_root src/
# Per ``/memories/repo/T1-pyi-exemptions.md`` these encode proven invariants;
# preserve coverage verbatim across reductions (envelope calls this out).
_PYI_EXEMPT_LOG_LAYOUT_CASES: list[Any] = [
    pytest.param(
        "init",
        "from .sub import Foo\n",
        "Exempt mypkg: __init__.py",
        id="init_exempt_logs_record",
    ),
    pytest.param(
        "main",
        "\ndef run():\n    pass\nif __name__ == '__main__':\n    run()\n",
        "Exempt script: standalone",
        id="main_exempt_logs_record",
    ),
    pytest.param(
        "conftest",
        "import pytest\n",
        "Exempt conftest_root: conftest.py",
        id="conftest_exempt_logs_record",
    ),
    pytest.param(
        "trivial_data",
        "x = 1\ny = 'hello'\n",
        "Exempt tests.data.fixture_data: trivial test data",
        id="trivial_test_data_exempt_logs_record",
    ),
]


def materialize_pyi_exempt_layout(
    tmp_path: Path,
    layout_kind: str,
    code: str,
) -> tuple[str, list[str], str]:
    """Materialise the per-row tmp_path layout for one T1-pyi-exemption test.

    Returns ``(file_path, source_roots, module_name)`` so the caller can pass
    them straight into ``walk_stub_close_release``.
    """
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


# ── stub_checker: shared import-contract / star-policy state builders ─


def _build_star_import_policy_state(star_policy: str, import_usage_factory) -> tuple:
    """Build a ``StubChecker`` state covering the star-import-policy matrix.

    Returns ``(tc, checker)``. The star-import policy is set on the state;
    importer module + target module mock nodes + target stub path are wired.
    """
    from python_setup_lint.checkers.stub_checker import StubChecker

    mock_b = MagicMock()
    mock_b.name = "mod_b"
    mock_b.position = None
    mock_a = MagicMock()
    mock_a.name = "mod_a"
    mock_a.position = None
    tc = _make_tc_factory(StubChecker)  # type: ignore[no-untyped-call]
    tc.checker._coverage.module_index = {
        "mod_a": (Path("/workspace/src/mod_a.py"), mock_a),
        "mod_b": (Path("/workspace/src/mod_b.py"), mock_b),
    }
    tc.checker._coverage.stub_index = {"mod_b": Path("/workspace/src/mod_b.pyi")}
    tc.checker._coverage.star_import_policy = star_policy
    tc.checker._coverage.import_usages = [import_usage_factory()]
    return tc, tc.checker


def _star_usage_factory() -> Any:
    """Build the standard star-import ``ImportUsage`` row (``"*"`` / is_star True)."""
    from python_setup_lint.checkers.stub_import_contract import ImportUsage

    return ImportUsage("mod_a", 1, "mod_b", "*", None, True)


# ── stub_checker: .pyi companion-resolution rows ────────────────────

# ``(layout_kind, code, module_name, expected_e97a0_count)`` — materialises
# the on-disk .py / .pyi layout per ``layout_kind``:
#   - "inline"     → src/<module_name>.py + src/<module_name>.pyi
#   - "package"    → src/mypkg/__init__.py + src/mypkg/__init__.pyi
#   - "stub_root"  → src/<module_name>.py + stubs/<module_name>.pyi
#   - "no_stub"    → src/<module_name>.py only (E97A0 expected)
#   - "empty"     → walk no modules (no E97A0 expected)
_STUB_RESOLUTION_CASES: list[Any] = [
    pytest.param("inline", "x = 1\n", "has_stub", 0, id="inline_stub_detected"),
    pytest.param("package", "x = 1\n", "mypkg", 0, id="package_init_stub_detected"),
    pytest.param("stub_root", "x = 1\n", "foo", 0, id="stub_root_resolution"),
    pytest.param("no_stub", "y = 2\n", "unstubbed", 1, id="missing_stub_emits_e97a0"),
    pytest.param("empty", "", "", 0, id="no_stub_no_error_on_empty"),
]


def walk_stub_resolution_layout(
    tmp_path: Path,
    layout_kind: str,
    code: str,
    module_name: str,
) -> list:
    """Materialise the on-disk ``.py`` / ``.pyi`` layout per ``layout_kind`` and
    walk ``StubChecker`` (open/walk/close) over the resulting module.

    Layout kinds:
      - ``inline``    → src/<module_name>.py + src/<module_name>.pyi
      - ``package``   → src/<module_name>/__init__.py + .pyi
      - ``stub_root`` → src/<module_name>.py + stubs/<module_name>.pyi (with
        ``stub_roots`` set on the linter config)
      - ``no_stub``   → src/<module_name>.py only
      - ``empty``     → walks the checker close() without any module

    Returns the released message list so callers can assert E97A0 counts.
    """
    from python_setup_lint.checkers.stub_checker import StubChecker

    tc = _make_tc_factory(StubChecker)  # type: ignore[no-untyped-call]
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


# ── stub_coverage: _resolve_stub layout rows ────────────────────────

# ``(layout_kind, expected_kind)`` — materialises the .py / .pyi layout per
# ``layout_kind`` (matches the ``_resolve_stub`` test set):
#   - ``"inline"``    → mod.py + mod.pyi (next to each other)
#   - ``"package"``   → mypkg/__init__.py + .pyi
#   - ``"no_stub"``   → mod.py only (returns None)
#   - ``"stub_root"`` → src/mod.py + stubs/mod.pyi
# ``expected_kind`` selects the assertion branch: ``"returns_pyi"``,
# ``"returns_none"``.
_RESOLVE_STUB_CASES: list[Any] = [
    pytest.param("inline", "returns_pyi", id="inline_stub"),
    pytest.param("package", "returns_pyi", id="package_init_stub"),
    pytest.param("no_stub", "returns_none", id="no_stub_returns_none"),
    pytest.param("stub_root", "returns_pyi", id="stub_root_resolution"),
]


def materialize_resolve_stub_layout(tmp_path: Path, layout_kind: str) -> tuple:
    """Build the .py / .pyi layout per ``layout_kind`` and return the tuple
    ``(checker, py_path, expected_pyi_path_or_None)`` for the resolve_stub test."""
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
    # stub_root
    src = tmp_path / "src"
    src.mkdir()
    py_path = src / "mod.py"
    py_path.write_text("x = 1\n")
    stub_root = tmp_path / "stubs"
    stub_root.mkdir()
    stub_path = stub_root / "mod.pyi"
    stub_path.write_text("x: int\n")
    checker, _tc = make_coverage_checker(
        source_roots=[str(src)],
        stub_roots=[str(stub_root)],
    )
    return checker, py_path, stub_path


# ── stub_coverage: emit_coverage_violations rows ────────────────────

# ``(setup_kind, stub_missing_module, expected_msg_count)`` — single parametrise
# entry for each branch of ``emit_coverage_violations``.
#   - ``"in_index"``           — wires module_index["mod_a"] + stub_missing={"mod_a"}
#     ⇒ 1 E97A0 emitted.
#   - ``"no_missing"``          — stub_missing is empty ⇒ 0 emitted.
#   - ``"skip_module_not_in_index"`` — stub_missing={"ghost_module"} (NOT in
#     module_index) ⇒ 0 emitted (skipped).
_EMIT_COVERAGE_CASES: list[Any] = [
    pytest.param("in_index", "mod_a", 1, id="one_missing_module"),
    pytest.param("no_missing", "", 0, id="no_missing_emits_nothing"),
    pytest.param(
        "skip_module_not_in_index", "ghost_module", 0, id="skip_module_not_in_index"
    ),
]


def make_emit_coverage_state(
    tmp_path: Path, setup_kind: str, stub_missing_module: str
) -> tuple:
    """Build a ``CheckerTestCase`` for ``emit_coverage_violations`` tests.

    ``setup_kind`` selects the module-index setup:
      - ``"in_index"`` — wires module_index[``stub_missing_module``] with a
        real mock node + ``stub_missing={stub_missing_module}`` ⇒ emit fires.
      - otherwise — leaves module_index empty; only ``stub_missing={stub_missing_module}``
        (or empty when ``stub_missing_module`` is "") is wired ⇒ skip path.
    Returns ``(tc, mock_node_or_None)``.
    """
    from pylint.testutils import CheckerTestCase

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
        # Skip path: module_index left empty; only stub_missing wired.
        tc.checker._coverage.stub_missing = {stub_missing_module}
    return tc, mock_node


# ── shared subprocess-integration helpers ──────────────────────────


def _run_pylint(
    tmp_path: Path,
    mod_py: str,
    mod_pyi: str,
    enable: str,
    *,
    project_src: Path,
) -> str:
    """Build a tiny project under *tmp_path* with paired mod_a.py / mod_a.pyi
    and run pylint with ``--disable=all --enable=<enable>`` via the
    ``python_setup_lint.checkers.stub_checker`` load-plugin.

    Returns the combined stdout+stderr so callers can assert on message codes.
    """
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
        [
            sys.executable,
            "-m",
            "pylint",
            str(src),
            "--disable=all",
            f"--enable={enable}",
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
        check=False,
    )
    return result.stdout + result.stderr


# Class-fidelity end-to-end rows: ``(mod_py, mod_pyi, enable, expected_code)``.
# Each row corresponds to one of the 5 pre-T14 narrow ``test_integration_*``
# methods (now parametrised). Includes the impl-missing-annotation W97B5 row
# that was previously ``test_integration_impl_missing_annotation``.
_CLASS_FIDELITY_INTEGRATION_CASES: list[Any] = [
    pytest.param(
        "x: int = 1\n",
        "\nx: int\nclass Foo: ...\n",
        "stub-symbol-missing",
        "E97B1",
        id="integration_stub_symbol_missing",
    ),
    pytest.param(
        "Foo: int = 1\n",
        "class Foo: ...\n",
        "symbol-kind-mismatch",
        "E97B2",
        id="integration_kind_mismatch",
    ),
    pytest.param(
        "\nclass Foo:\n    x: int = 1\n",
        "\nclass Foo(BaseModel):\n    x: int\n",
        "annotation-mismatch",
        "E97B4",
        id="integration_base_class_mismatch",
    ),
    pytest.param(
        "x: str = 'hello'\n",
        "x: int\n",
        "annotation-mismatch",
        "E97B4",
        id="integration_variable_annotation_mismatch",
    ),
    pytest.param(
        "x = 1\n",
        "x: int\n",
        "impl-missing-annotation",
        "W97B5",
        id="integration_impl_missing_annotation",
    ),
]


# Callable-fidelity end-to-end rows: ``(mod_py, mod_pyi, enable, expected_code)``.
_CALLABLE_FIDELITY_INTEGRATION_CASES: list[Any] = [
    pytest.param(
        "\ndef foo(x: int, y: str) -> None: ...\n",
        "\ndef foo(x: int) -> None: ...\n",
        "signature-mismatch",
        "E97B3",
        id="signature_mismatch",
    ),
    pytest.param(
        "\ndef foo() -> int: ...\n",
        "\ndef foo() -> str: ...\n",
        "annotation-mismatch",
        "E97B4",
        id="return_annotation_mismatch",
    ),
]


# ── stub_class: shared walk-with-pair helper ───────────────────────


def walk_stub_checker_with_pair(
    tmp_path: Path,
    py_code: str,
    pyi_code: str,
    module_name: str = "mod_a",
) -> list:
    """Walk StubChecker over a paired impl(.py) + stub(.pyi) under
    ``tmp_path/src`` and return the released message list.

    Wires ``source_roots=[<tmp_path>/src]``, parses the impl source, and walks
    ``open()/walk()/close()``. Used by the E97B1/E97B2 fidelity tests.
    """
    from python_setup_lint.checkers.stub_checker import StubChecker

    src = tmp_path / "src"
    src.mkdir()
    (src / f"{module_name}.py").write_text(py_code)
    (src / f"{module_name}.pyi").write_text(pyi_code)
    tc = _make_tc_factory(StubChecker)  # type: ignore[no-untyped-call]
    tc.linter.config.source_roots = [str(src)]
    tc.checker.open()
    module = astroid.parse(py_code, module_name=module_name)
    module.file = str(src / f"{module_name}.py")
    tc.walk(module)
    tc.checker.close()
    return tc.linter.release_messages()


# ── stub_checker: import-contract parametrise setup helper ─────────


def setup_and_emit_import_contract(
    *,
    target_module: str,
    has_stub: bool,
    declared_symbols: set[str] | None,
    importer: str,
    symbol: str | None,
    is_star: bool,
    star_policy: str | None,
) -> tuple:
    """Build a pre-populated ``StubChecker`` state per the row parameters and
    call ``emit_import_contract_violations``. Returns ``(tc, msgs)`` so the
    caller asserts on the emitted msg ids / counts.
    """
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


# ── stub_checker: registered message codes table ───────────────────

# ``(code, expected_symbol)`` — verifies each registered E97A* message id.
_STUB_CHECKER_MSGS_CASES: list[Any] = [
    pytest.param("E97A0", "missing-module-stub", id="E97A0"),
    pytest.param("E97A1", "missing-import-declaration", id="E97A1"),
    pytest.param("E97A2", "missing-module-stub-for-import", id="E97A2"),
    pytest.param("E97A3", "star-import-unresolvable", id="E97A3"),
]
