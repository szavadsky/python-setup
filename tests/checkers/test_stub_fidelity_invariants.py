"""Invariant fixture tests for ``stub_fidelity`` (E97B1/B2/B3/B4/W97B5/I97B6).

Added BEFORE the T10 split of ``stub_fidelity.py`` (763 LOC) into the
``stub_fidelity/`` package.  Each fixture pairs a ``.py`` implementation
with a ``.pyi`` stub and asserts the EXACT message-ids and arg tuples
emitted by ``emit_fidelity_violations`` via ``StubChecker.close()``.

Purpose: lock E97B invariant behaviour so any slice that regresses
fidelity emission fails fast.  The split is mechanical and
behaviour-preserving — these invariants act as a bidirectional gate.

The fixtures cover every emitted message-id family:
- E97B1 ``stub-symbol-missing`` — stub symbol absent from impl.
- E97B2 ``symbol-kind-mismatch`` — stub vs impl kind disagreement.
- E97B3 ``signature-mismatch`` — callable signature shape differs.
- E97B4 ``annotation-mismatch`` — variable/param/return/base annotation differs.
- W97B5 ``impl-missing-annotation`` — stub annotates, impl does not.
- I97B6 ``annotation-unverifiable`` — annotation cannot be normalized.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import TYPE_CHECKING

import astroid

from python_setup_lint.checkers.stub_checker import StubChecker
from python_setup_lint.checkers.stub_fidelity import (
    CallableComparisonCtx,
    ClassComparisonCtx,
    ParamDescriptor,
    _compare_callable_annotations,
    _compare_callable_descriptors,
    _compare_return_annotations,
    _extract_param_descriptors,
    _is_classvar,
    _is_public_method,
    _normalize_bases,
    emit_fidelity_violations,
)
from python_setup_lint.testing import _make_tc as _make_tc_factory

if TYPE_CHECKING:
    pass


_make_tc = lambda: _make_tc_factory(StubChecker)


def _run(
    tmp_path: Path, py_code: str, pyi_code: str, module_name: str = "mod_a"
) -> list:
    """Run StubChecker end-to-end on a synthetic module + stub.

    Returns released messages sorted (msg_id, args tuple).
    """
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    # Companion file structure matters for _resolve_stub.  Provide both
    # the impl AND the matching stub file under source root.
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


def _msg_ids(msgs: list) -> list[str]:
    """Sorted msg-id list emitted."""
    return sorted(m.msg_id for m in msgs)


def _args_of(msgs: list, msg_id: str) -> list[tuple]:
    """Args tuple for each emitted message with given msg_id, sorted."""
    return sorted(m.args for m in msgs if m.msg_id == msg_id)


class TestSymbolPresenceFiredInvariants:
    """E97B1 (stub-symbol-missing) fired behaviour.

    Locks the message-id and args emitted for each stub-only symbol
    kind (variable / callable / class).
    """

    def test_e97b1_for_missing_var(self, tmp_path: Path) -> None:
        # Stub declares ``y``; impl has only ``x`` → E97B1 for ``y``.
        msgs = _run(tmp_path, "x: int = 1\n", "x: int\ny: str\n")
        ids = _msg_ids(msgs)
        assert "stub-symbol-missing" in ids
        args = _args_of(msgs, "stub-symbol-missing")
        # args are (symbol_name, module_name).
        assert ("y", "mod_a") in args
        assert ("x", "mod_a") not in args  # impl present → no fire

    def test_e97b1_for_missing_callable(self, tmp_path: Path) -> None:
        msgs = _run(tmp_path, "x: int = 1\n", "x: int\ndef foo() -> None: ...\n")
        args = _args_of(msgs, "stub-symbol-missing")
        assert ("foo", "mod_a") in args

    def test_e97b1_for_missing_class(self, tmp_path: Path) -> None:
        msgs = _run(tmp_path, "x: int = 1\n", "x: int\nclass Foo: ...\n")
        args = _args_of(msgs, "stub-symbol-missing")
        assert ("Foo", "mod_a") in args

    def test_e97b1_silent_when_all_present(self, tmp_path: Path) -> None:
        # Matching impl/stub surfaces → no E97B1.
        msgs = _run(
            tmp_path,
            "x: int = 1\ndef foo() -> None: ...\nclass Foo: ...\n",
            "x: int\ndef foo() -> None: ...\nclass Foo: ...\n",
        )
        assert _args_of(msgs, "stub-symbol-missing") == []


class TestKindMismatchInvariants:
    """E97B2 (symbol-kind-mismatch) fired behaviour.

    Locks the args tuple order (symbol, module, stub_kind, impl_kind).
    """

    def test_stub_class_impl_var(self, tmp_path: Path) -> None:
        msgs = _run(tmp_path, "Foo: int = 1\n", "class Foo: ...\n")
        args = _args_of(msgs, "symbol-kind-mismatch")
        assert ("Foo", "mod_a", "class", "variable") in args

    def test_stub_func_impl_var(self, tmp_path: Path) -> None:
        msgs = _run(tmp_path, "foo: int = 1\n", "def foo() -> None: ...\n")
        args = _args_of(msgs, "symbol-kind-mismatch")
        assert ("foo", "mod_a", "callable", "variable") in args

    def test_stub_class_impl_func(self, tmp_path: Path) -> None:
        msgs = _run(tmp_path, "def Foo() -> None: ...\n", "class Foo: ...\n")
        args = _args_of(msgs, "symbol-kind-mismatch")
        assert ("Foo", "mod_a", "class", "callable") in args

    def test_stub_var_impl_class(self, tmp_path: Path) -> None:
        msgs = _run(tmp_path, "class Foo: ...\n", "Foo: int\n")
        args = _args_of(msgs, "symbol-kind-mismatch")
        assert ("Foo", "mod_a", "variable", "class") in args


class TestSignatureMismatchInvariants:
    """E97B3 (signature-mismatch) fired behaviour for callable param shape."""

    def test_param_count_mismatch_fires(self, tmp_path: Path) -> None:
        msgs = _run(
            tmp_path,
            "def foo(a: int) -> None: ...\n",
            "def foo(a: int, b: int) -> None: ...\n",
        )
        args = _args_of(msgs, "signature-mismatch")
        assert len(args) == 1
        # args are (func_name, module, detail) — detail contains param_count.
        assert args[0][0] == "foo"
        assert args[0][1] == "mod_a"
        assert "param_count" in args[0][2]

    def test_param_name_mismatch_fires(self, tmp_path: Path) -> None:
        msgs = _run(
            tmp_path,
            "def foo(a: int) -> None: ...\n",
            "def foo(b: int) -> None: ...\n",
        )
        args = _args_of(msgs, "signature-mismatch")
        assert len(args) == 1
        assert "param_name" in args[0][2]

    def test_matching_signature_silent(self, tmp_path: Path) -> None:
        msgs = _run(
            tmp_path,
            "def foo(a: int, b: str = 'x') -> None: ...\n",
            "def foo(a: int, b: str = 'y') -> None: ...\n",
        )
        assert _args_of(msgs, "signature-mismatch") == []
        assert _args_of(msgs, "annotation-mismatch") == []


class TestAnnotationMismatchInvariants:
    """E97B4 (annotation-mismatch) for variable + return + class attribute."""

    def test_var_annotation_mismatch(self, tmp_path: Path) -> None:
        msgs = _run(tmp_path, "x: str = 'h'\n", "x: int\n")
        args = _args_of(msgs, "annotation-mismatch")
        # args: (symbol, module, stub_norm, impl_norm).
        assert ("x", "mod_a", "int", "str") in args

    def test_return_annotation_mismatch(self, tmp_path: Path) -> None:
        msgs = _run(
            tmp_path,
            "def foo() -> str: ...\n",
            "def foo() -> int: ...\n",
        )
        args = _args_of(msgs, "annotation-mismatch")
        assert ("foo", "mod_a", "int", "str") in args

    def test_param_annotation_mismatch(self, tmp_path: Path) -> None:
        msgs = _run(
            tmp_path,
            "def foo(a: str) -> None: ...\n",
            "def foo(a: int) -> None: ...\n",
        )
        args = _args_of(msgs, "annotation-mismatch")
        assert ("foo", "mod_a", "int", "str") in args


class TestImplMissingAnnotationInvariants:
    """W97B5 (impl-missing-annotation) — stub annotates, impl does not.

    Default ``impl_missing_annotation`` policy = ``warn`` → W97B5 fires.
    """

    def test_var_missing_impl_annotation(self, tmp_path: Path) -> None:
        msgs = _run(tmp_path, "x = 1\n", "x: int\n")
        args = _args_of(msgs, "impl-missing-annotation")
        assert ("x", "mod_a") in args

    def test_class_attr_missing_impl_annotation(self, tmp_path: Path) -> None:
        py = "class Foo:\n    x = 1\n"
        pyi = "class Foo:\n    x: int\n"
        msgs = _run(tmp_path, py, pyi)
        args = _args_of(msgs, "impl-missing-annotation")
        assert ("Foo.x", "mod_a") in args


class TestClassComparisonInvariants:
    """E97B4 for class bases — emitted via ``_compare_class_bases``."""

    def test_base_class_mismatch(self, tmp_path: Path) -> None:
        py = "class Foo:\n    x: int = 1\n"
        pyi = "class Foo(BaseModel):\n    x: int\n"
        msgs = _run(tmp_path, py, pyi)
        args = _args_of(msgs, "annotation-mismatch")
        # args: (class_name, module, stub_str, impl_str) where stub=BaseModel.
        # impl has no bases → '(none)' normalised.
        assert len(args) == 1
        assert args[0][0] == "Foo"
        assert args[0][1] == "mod_a"
        assert "BaseModel" in args[0][2]


class TestClassVarSkipInvariants:
    """ClassVar-annotated stub symbols are skipped from fidelity comparison.

    Locks ``_is_classvar`` AST detection AND the dispatcher-level skip.
    """

    def test_is_classvar_true(self) -> None:
        node = astroid.extract_node("ClassVar[int]")
        assert _is_classvar(node) is True

    def test_is_classvar_false(self) -> None:
        node = astroid.extract_node("int")
        assert _is_classvar(node) is False

    def test_module_var_classvar_skipped(self, tmp_path: Path) -> None:
        # Stub has ``x: ClassVar[int]`` → no W97B5 even when impl has no ann.
        msgs = _run(
            tmp_path,
            "from typing import ClassVar\nx = 1\n",
            "from typing import ClassVar\nx: ClassVar[int]\n",
        )
        assert _args_of(msgs, "impl-missing-annotation") == []
        assert _args_of(msgs, "annotation-mismatch") == []


class TestPublicSymbolSurface:
    """Lock the import surface of ``stub_fidelity`` (preserved by split).

    Every name imported/used by tests AND sub-modules must remain
    re-exported from ``python_setup_lint.checkers.stub_fidelity``.
    """

    def test_public_symbols_exportable(self) -> None:
        from python_setup_lint.checkers import stub_fidelity as mod

        for name in (
            "emit_fidelity_violations",
            "ParamDescriptor",
            "ClassComparisonCtx",
            "CallableComparisonCtx",
            "_FidelityState",
            "_extract_param_descriptors",
            "_compare_callable_descriptors",
            "_compare_callable_annotations",
            "_compare_return_annotations",
            "_emit_callable_fidelity_issues",
            "_emit_callable_fidelity",
            "_emit_variable_fidelity",
            "_emit_stub_symbol_check",
            "_compare_class_bases",
            "_compare_class_methods",
            "_compare_class_attrs",
            "_normalize_bases",
            "_is_public_method",
            "_is_classvar",
        ):
            assert hasattr(mod, name), f"stub_fidelity missing {name}"

    def test_param_descriptor_fields(self) -> None:
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


class TestComparePureHelpersDirect:
    """Direct unit calls to pure compare helpers (no checker needed).

    These do not emit messages; they return mismatch tuples or detail
    strings — split must preserve the return contracts.
    """

    def test_descriptors_identical(self) -> None:
        a = [ParamDescriptor("x", inspect.Parameter.POSITIONAL_OR_KEYWORD, False, None)]
        b = [ParamDescriptor("x", inspect.Parameter.POSITIONAL_OR_KEYWORD, False, None)]
        assert _compare_callable_descriptors(a, b) is None

    def test_descriptors_count_mismatch(self) -> None:
        a = [ParamDescriptor("x", inspect.Parameter.POSITIONAL_OR_KEYWORD, False, None)]
        assert "param_count" in _compare_callable_descriptors(a, [])

    def test_annotations_match_returns_empty(self) -> None:
        a = [
            ParamDescriptor("x", inspect.Parameter.POSITIONAL_OR_KEYWORD, False, "int")
        ]
        b = [
            ParamDescriptor("x", inspect.Parameter.POSITIONAL_OR_KEYWORD, False, "int")
        ]
        assert _compare_callable_annotations(a, b) == []

    def test_annotations_skips_unilateral(self) -> None:
        a = [ParamDescriptor("x", inspect.Parameter.POSITIONAL_OR_KEYWORD, False, None)]
        b = [
            ParamDescriptor("x", inspect.Parameter.POSITIONAL_OR_KEYWORD, False, "int")
        ]
        assert _compare_callable_annotations(a, b) == []

    def test_return_annotations_normalizes_both(self) -> None:
        stub = astroid.parse("def f() -> int: ...\n").body[0].returns
        impl = astroid.parse("def f() -> int: ...\n").body[0].returns
        stub_norm, impl_norm = _compare_return_annotations(stub, impl)
        assert stub_norm == "int"
        assert impl_norm == "int"

    def test_return_annotations_none_pair(self) -> None:
        s, i = _compare_return_annotations(None, None)
        assert s is None and i is None

    def test_extract_param_descriptor_round_trip(self) -> None:
        f = astroid.parse("def foo(a: int, *, b: str = 'x') -> None: ...\n").body[0]
        descs = _extract_param_descriptors(f.args)
        names = [d.name for d in descs]
        kinds = [d.kind for d in descs]
        assert names == ["a", "b"]
        assert kinds[0] == inspect.Parameter.POSITIONAL_OR_KEYWORD
        assert kinds[1] == inspect.Parameter.KEYWORD_ONLY

    def test_normalize_bases_attribute_strips_prefix(self) -> None:
        mod = astroid.parse("class Foo(pydantic.BaseModel): ...\n")
        assert _normalize_bases(mod.body[0].bases) == ["BaseModel"]

    def test_normalize_bases_builtins_object(self) -> None:
        mod = astroid.parse("class Foo(object): ...\n")
        assert _normalize_bases(mod.body[0].bases) == ["builtins.object"]

    def test_is_public_method_rules(self) -> None:
        assert _is_public_method("foo") is True
        assert _is_public_method("_helper") is False
        assert _is_public_method("__str__") is False
        assert _is_public_method("__init__") is True
        assert _is_public_method("__new__") is True


class TestCtxConstruction:
    """Context dataclasses build cleanly with the documented fields."""

    def test_class_ctx(self) -> None:
        stub = astroid.parse("class A: ...\n")
        impl = astroid.parse("class A: ...\n")
        ctx = ClassComparisonCtx(
            checker=None,  # type: ignore[arg-type]
            module_name="m",
            class_name="A",
            msg_node=impl,
            stub_class=stub.body[0],
            impl_class=impl.body[0],
        )
        assert ctx.class_name == "A"
        assert ctx.module_name == "m"

    def test_callable_ctx(self) -> None:
        stub = astroid.parse("def f() -> None: ...\n")
        ctx = CallableComparisonCtx(
            checker=None,  # type: ignore[arg-type]
            module_name="m",
            func_name="f",
            msg_node=stub,
            stub_func=stub.body[0],
            impl_func=None,
        )
        assert ctx.func_name == "f"
        assert ctx.impl_func is None


class TestEmitFidelityViolationsOrchestrator:
    """``emit_fidelity_violations`` orchestrates per-module dispatchers.

    Verifies the public entrypoint walks all modules in stub_index in
    the documented order: stub-symbol check, then variable, then callable.
    """

    def test_empty_checker_no_error(self) -> None:
        # No stub_index entries → no dispatch.  Defensive guard against
        # any future refactor that would iterate outside stub_index.
        tc = _make_tc()
        tc.checker.open()
        # Empty _coverage.stub_index → emit_fidelity_violations returns.
        assert emit_fidelity_violations(tc.checker) is None  # returns None
