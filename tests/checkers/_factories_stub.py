"""Parametrize rows and state builders for ``StubChecker`` tests.

Split by checker domain out of the former 1393-line ``_factories.py`` (pylint
C0302). Paired with ``tests/checkers/test_stub_checker.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import astroid
import pytest
from pylint.testutils import CheckerTestCase

from python_setup_lint.testing import _make_tc as _make_tc_factory

if TYPE_CHECKING:
    from _pytest.mark.structures import ParameterSet

    from python_setup_lint.checkers.stub.checker import StubChecker
    from python_setup_lint.checkers.stub.import_contract import ImportUsage

_p = pytest.param


# ── stub checker ──

_STUB_FILE_CLASSIFICATION_CASES: list[ParameterSet] = [
    _p(
        "/workspace/tests/test_foo.py",
        ["/workspace/src"],
        None,
        None,
        0,
        id="test_file_in_tests_dir",
    ),
    _p(
        "/workspace/src/test_example.py",
        ["/workspace/src"],
        ["test_*.py", "tests/"],
        None,
        0,
        id="test_file_named_test_prefixed",
    ),
    _p(
        "/workspace/other/foo.py",
        ["/workspace/src"],
        None,
        None,
        0,
        id="file_outside_source_root_skipped",
    ),
    _p(
        "/workspace/src/generated/foo.py",
        ["/workspace/src"],
        None,
        ["src/generated/"],
        0,
        id="opted_out_by_directory",
    ),
    _p(
        "/workspace/src/vendor/external.py",
        ["/workspace/src"],
        None,
        ["src/vendor/"],
        0,
        id="opted_out_by_filename",
    ),
]

_RESOLVE_RELATIVE_CASES: list[ParameterSet] = [
    _p("mod_a", 0, "os", False, "os", id="absolute_import"),
    _p("mod_a", 0, None, False, "", id="absolute_no_modname"),
    _p("mypkg", 1, None, True, "mypkg", id="same_package_init"),
    _p("mypkg", 1, "mod_a", True, "mypkg.mod_a", id="same_package_init_with_name"),
    _p("mypkg.mod_a", 2, "sibling", False, "sibling", id="parent_package"),
    _p("pkg.sub.mod_a", 3, "other", False, "other", id="grandparent_package"),
    _p("mod_a", 3, "other", True, "other", id="level_exceeds_depth"),
]

_IS_TYPE_CHECKING_GUARD_CASES: list[ParameterSet] = [
    _p("TYPE_CHECKING", True, id="name_form"),
    _p("typing.TYPE_CHECKING", True, id="typing_dot_name"),
    _p("SOME_FLAG", False, id="other_name"),
    _p("os.name", False, id="other_attribute"),
]

_IN_TYPE_CHECKING_BLOCK_POSITIVE_CASES: list[ParameterSet] = [
    _p(
        "if TYPE_CHECKING:\n    from foo import Bar\n",
        lambda m: m.body[0].body[0],
        id="under_type_checking",
    ),
    _p(
        "if TYPE_CHECKING:\n    if True:\n        from foo import Bar\n",
        lambda m: m.body[0].body[0].body[0],
        id="nested_inside_type_checking",
    ),
]

_IN_TYPE_CHECKING_BLOCK_NEGATIVE_CASES: list[ParameterSet] = [
    _p("from foo import Bar\n", lambda m: m.body[0], id="not_under_type_checking"),
]


# ── stub_import_contract helpers ──


def build_import_contract_state(
    *,
    module_index: dict[str, tuple[Path, Any]] | None = None,
    stub_index: dict[str, Path] | None = None,
    declaration_index: dict[str, set[str]] | None = None,
    import_usages: list[ImportUsage] | None = None,
) -> tuple[StubChecker, CheckerTestCase]:

    tc = _make_tc_factory(_stub_checker_class())
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
    from python_setup_lint.checkers.stub.checker import StubChecker

    return StubChecker


# ── stub_checker: import-usage / contract-violations tables ──

_IMPORT_USAGE_FIELD_CASES: list[ParameterSet] = [
    _p(
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
    _p(
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
    _p(
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

_IMPORT_CONTRACT_CASES: list[ParameterSet] = [
    _p(
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
    _p(
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
    _p(
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
    _p(
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

_STAR_POLICY_CASES: list[ParameterSet] = [
    _p("error", 1, id="star_policy_error"),
    _p("ignore", 0, id="star_policy_ignore"),
]

_VARIABLE_FIDELITY_CASES: list[ParameterSet] = [
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
) -> list[Any]:
    from python_setup_lint.checkers.stub.checker import StubChecker

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

_PYI_EXEMPT_LOG_LAYOUT_CASES: list[ParameterSet] = [
    _p(
        "init",
        "from .sub import Foo\n",
        "Exempt __init__.py",
        id="init_exempt_logs_record",
    ),
    _p(
        "main",
        "\ndef run():\n    pass\nif __name__ == '__main__':\n    run()\n",
        "Exempt standalone script",
        id="main_exempt_logs_record",
    ),
    _p(
        "conftest",
        "import pytest\n",
        "Exempt conftest.py",
        id="conftest_exempt_logs_record",
    ),
    _p(
        "trivial_data",
        "x = 1\ny = 'hello'\n",
        "Exempt trivial test data module",
        id="trivial_test_data_exempt_logs_record",
    ),
]


def materialize_pyi_exempt_layout(
    tmp_path: Path,
    layout_kind: str,
    code: str,
    /,
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


def _build_star_import_policy_state(star_policy: str, import_usage_factory: Any, /) -> tuple[CheckerTestCase, StubChecker]:
    from python_setup_lint.checkers.stub.checker import StubChecker

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
    from python_setup_lint.checkers.stub.import_contract import ImportUsage

    return ImportUsage("mod_a", 1, "mod_b", "*", None, True)


# ── stub_checker: .pyi companion-resolution ──

_STUB_RESOLUTION_CASES: list[ParameterSet] = [
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
    /,
) -> list[Any]:
    from python_setup_lint.checkers.stub.checker import StubChecker

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
) -> tuple[CheckerTestCase, list[Any]]:
    from python_setup_lint.checkers.stub.import_contract import (
        ImportUsage,
        emit_import_contract_violations,
    )

    target_path_str = f"/workspace/src/{target_module}.py"
    target_node = MagicMock()
    target_node.name = target_module
    module_index = {target_module: (Path(target_path_str), target_node)}
    stub_index = {target_module: Path(f"/workspace/src/{target_module}.pyi")} if has_stub else {}
    declaration_index = {target_module: declared_symbols} if declared_symbols is not None else {}
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

_STUB_CHECKER_MSGS_CASES: list[ParameterSet] = [
    _p("E97A0", "missing-module-stub", id="E97A0"),
    _p("E97A1", "missing-import-declaration", id="E97A1"),
    _p("E97A2", "missing-module-stub-for-import", id="E97A2"),
    _p("E97A3", "star-import-unresolvable", id="E97A3"),
]
