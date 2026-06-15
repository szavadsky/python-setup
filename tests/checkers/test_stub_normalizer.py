"""Unit tests for python_setup_lint.checkers.stub_normalizer — AnnotationNormalizer.

Two-phase normalization: infer() → AST-string walking fallback.
Exercises Phase 1 (inference), Phase 2 (AST walking), and rewrite rules.
"""

from __future__ import annotations

import astroid

from python_setup_lint.checkers.stub_normalizer import AnnotationNormalizer


class TestAnnotationNormalizer:
    """Two-phase normalization: infer → string-walking fallback."""

    # ── Phase 1: infer() ──────────────────────────────────────────────────────

    def test_infer_simple_name(self):
        module = astroid.parse("x: str", module_name="test_mod")
        ann = module.body[0].annotation
        result = AnnotationNormalizer.normalize(ann)
        assert result == "str"

    def test_infer_builtin_list(self):
        module = astroid.parse("x: list[int]", module_name="test_mod")
        ann = module.body[0].annotation
        result = AnnotationNormalizer.normalize(ann)
        assert result == "list[int]"

    def test_infer_native_union(self):
        module = astroid.parse("x: str | None", module_name="test_mod")
        ann = module.body[0].annotation
        result = AnnotationNormalizer.normalize(ann)
        assert result == "str | None"

    def test_infer_returns_none_for_uninferable(self):
        module = astroid.parse("x: 'SomeFutureType'", module_name="test_mod")
        ann = module.body[0].annotation
        result = AnnotationNormalizer.normalize(ann)
        assert result is not None

    # ── Phase 2: AST-string walking ───────────────────────────────────────────

    def test_ast_string_subscript(self):
        module = astroid.parse("x: list[str]", module_name="test_mod")
        ann = module.body[0].annotation
        result = AnnotationNormalizer._ast_string(ann)
        assert result is not None
        assert "list" in result

    def test_ast_string_binary_op_union(self):
        module = astroid.parse("x: int | str", module_name="test_mod")
        ann = module.body[0].annotation
        result = AnnotationNormalizer._ast_string(ann)
        assert result == "int | str"

    def test_ast_string_attribute(self):
        node = astroid.extract_node("x: typing.Optional[str]")
        ann = node.annotation
        result = AnnotationNormalizer._ast_string(ann)
        assert result is not None
        assert "typing.Optional" in result

    def test_ast_string_tuple(self):
        module = astroid.parse("x: tuple[int, str]", module_name="test_mod")
        ann = module.body[0].annotation
        result = AnnotationNormalizer._ast_string(ann)
        assert result is not None

    def test_ast_string_const(self):
        module = astroid.parse("x: Literal['hello']", module_name="test_mod")
        ann = module.body[0].annotation
        result = AnnotationNormalizer._ast_string(ann)
        assert result is not None
        assert "hello" in result

    def test_ast_string_nested_subscript(self):
        module = astroid.parse("x: dict[str, list[int]]", module_name="test_mod")
        ann = module.body[0].annotation
        result = AnnotationNormalizer._ast_string(ann)
        assert result is not None
        assert "dict" in result
        assert "list" in result

    # ── Rewrite rules ─────────────────────────────────────────────────────────

    def test_rewrite_typing_list(self):
        result = AnnotationNormalizer._apply_rewrites("typing.List[str]")
        assert result == "list[str]"

    def test_rewrite_typing_dict(self):
        result = AnnotationNormalizer._apply_rewrites("typing.Dict[str, int]")
        assert result == "dict[str, int]"

    def test_rewrite_typing_optional(self):
        result = AnnotationNormalizer._apply_rewrites("typing.Optional[str]")
        assert result == "str | None"

    def test_rewrite_typing_union(self):
        result = AnnotationNormalizer._apply_rewrites("typing.Union[str, int]")
        assert result == "str | int"

    def test_rewrite_typing_union_nested_generic(self):
        result = AnnotationNormalizer._apply_rewrites("typing.Union[list[str], int]")
        assert result == "list[str] | int"

    def test_rewrite_no_match_passes_through(self):
        result = AnnotationNormalizer._apply_rewrites("collections.abc.Callable")
        assert result == "collections.abc.Callable"

    def test_split_outer_commas_simple(self):
        parts = AnnotationNormalizer._split_outer_commas("str, int, float")
        assert parts == ["str", "int", "float"]

    def test_split_outer_commas_with_brackets(self):
        parts = AnnotationNormalizer._split_outer_commas("list[str], int")
        assert parts == ["list[str]", "int"]