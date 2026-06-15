"""Unit tests for python_setup_lint.checkers.stub_checker — Invariant 1 (coverage) + Invariant 2 (import contract) + Invariant 3 (variable fidelity).

Uses pylint.testutils.CheckerTestCase pattern. Exercises checker registration,
configuration parsing, test-vs-production classification, .pyi companion
resolution, opt-out handling, import-contract enforcement, annotation
normalization, and variable annotation fidelity.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import astroid
from astroid import nodes
from pylint.testutils import CheckerTestCase

from python_setup_lint.checkers.stub_checker import StubChecker
from python_setup_lint.checkers.stub_fidelity import _is_classvar
from python_setup_lint.checkers.stub_import_contract import (
    ImportUsage,
    _in_type_checking_block,
    _is_type_checking_guard,
    _resolve_relative,
    emit_import_contract_violations,
)
from python_setup_lint.checkers.stub_normalizer import AnnotationNormalizer

if TYPE_CHECKING:
    import pytest

PROJECT_SRC = Path(__file__).resolve().parents[3] / "src"


def _make_tc() -> CheckerTestCase:
    tc = CheckerTestCase()
    tc.CHECKER_CLASS = StubChecker
    tc.setup_method()
    return tc


def _walk_and_release(code: str, file_path: str | None = None, module_name: str = ""):
    tc = _make_tc()
    module = astroid.parse(code, module_name=module_name)
    if file_path is not None:
        module.file = file_path
    tc.walk(module)
    return tc.linter.release_messages()


def _walk_and_release_with_config(
    code: str,
    file_path: str,
    source_roots: list[str] | None = None,
    test_patterns: list[str] | None = None,
    stub_opt_out: list[str] | None = None,
    stub_roots: list[str] | None = None,
    module_name: str = "test_module",
):
    tc = _make_tc()
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
    tc.walk(module)
    return tc.linter.release_messages()


def _walk_close_release_with_config(
    code: str,
    file_path: str,
    source_roots: list[str] | None = None,
    test_patterns: list[str] | None = None,
    stub_opt_out: list[str] | None = None,
    stub_roots: list[str] | None = None,
    module_name: str = "test_module",
):
    tc = _make_tc()
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


def _multi_walk_close(
    modules: list[tuple[str, str, str]],
    *,
    source_roots: list[str] | None = None,
    test_patterns: list[str] | None = None,
    stub_opt_out: list[str] | None = None,
    star_import_policy: str | None = None,
):
    tc = _make_tc()
    if source_roots is not None:
        tc.linter.config.source_roots = source_roots
    if test_patterns is not None:
        tc.linter.config.test_patterns = test_patterns
    if stub_opt_out is not None:
        tc.linter.config.stub_opt_out = stub_opt_out
    if star_import_policy is not None:
        tc.linter.config.star_import_policy = star_import_policy
    tc.checker.open()
    for code, file_path, module_name in modules:
        module = astroid.parse(code, module_name=module_name)
        module.file = file_path
        tc.walk(module)
    tc.checker.close()
    return tc.linter.release_messages()


class TestCheckerRegistration:
    """StubChecker registers with correct name and message codes."""

    def test_checker_name(self):
        tc = _make_tc()
        assert tc.checker.name == "stub-checker"

    def test_message_codes(self):
        tc = _make_tc()
        msgs = tc.checker.msgs
        assert "E97A0" in msgs
        assert msgs["E97A0"][1] == "missing-module-stub"
        assert "E97A1" in msgs
        assert msgs["E97A1"][1] == "missing-import-declaration"
        assert "E97A2" in msgs
        assert msgs["E97A2"][1] == "missing-module-stub-for-import"
        assert "E97A3" in msgs
        assert msgs["E97A3"][1] == "star-import-unresolvable"

    def test_register_function(self):
        from python_setup_lint.checkers.stub_checker import register

        mock_linter = MagicMock()
        register(mock_linter)
        mock_linter.register_checker.assert_called_once()
        args = mock_linter.register_checker.call_args[0]
        assert isinstance(args[0], StubChecker)

    def test_close_logs_counts(self):
        msgs = _walk_close_release_with_config(
            code="x = 1\n",
            file_path="/workspace/src/mod.py",
            source_roots=["/workspace/src"],
        )
        stub_msgs = [m for m in msgs if m.msg_id == "missing-module-stub"]
        assert len(stub_msgs) > 0, f"Expected at least 1 E97A0, got {len(stub_msgs)}"


class TestConfigurationParsing:
    """Checker reads configuration from linter.config correctly."""

    def test_default_source_roots(self):
        tc = _make_tc()
        tc.checker.open()
        assert len(tc.checker._coverage.source_roots) == 1
        assert str(tc.checker._coverage.source_roots[0]).endswith("/src")

    def test_default_test_patterns(self):
        tc = _make_tc()
        tc.checker.open()
        patterns = tc.checker._coverage.test_patterns
        assert "tests/" in patterns
        assert "test_*.py" in patterns

    def test_default_opt_out(self):
        tc = _make_tc()
        tc.checker.open()
        assert tc.checker._coverage.opt_out_patterns == []

    def test_custom_source_root(self):
        tc = _make_tc()
        tc.linter.config.source_roots = ["custom_src"]
        tc.checker.open()
        roots = tc.checker._coverage.source_roots
        assert any("custom_src" in str(r) for r in roots)


class TestFileClassification:
    """Checker correctly classifies test vs production files."""

    def test_test_file_in_tests_dir(self):
        msgs = _walk_close_release_with_config(
            code="x = 1\n",
            file_path="/workspace/tests/test_foo.py",
            source_roots=["/workspace/src"],
        )
        stub_msgs = [m for m in msgs if m.msg_id == "missing-module-stub"]
        assert len(stub_msgs) == 0

    def test_test_file_named_test_prefixed(self):
        msgs = _walk_close_release_with_config(
            code="x = 1\n",
            file_path="/workspace/src/test_example.py",
            source_roots=["/workspace/src"],
            test_patterns=["test_*.py", "tests/"],
        )
        stub_msgs = [m for m in msgs if m.msg_id == "missing-module-stub"]
        assert len(stub_msgs) == 0

    def test_production_file_under_src(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        prod_file = src / "some_module.py"
        prod_file.write_text("x = 1\n")
        msgs = _walk_close_release_with_config(
            code="x = 1\n",
            file_path=str(prod_file),
            source_roots=[str(src)],
        )
        stub_msgs = [m for m in msgs if m.msg_id == "missing-module-stub"]
        assert len(stub_msgs) > 0

    def test_file_outside_source_root_skipped(self):
        msgs = _walk_close_release_with_config(
            code="x = 1\n",
            file_path="/workspace/other/foo.py",
            source_roots=["/workspace/src"],
        )
        stub_msgs = [m for m in msgs if m.msg_id == "missing-module-stub"]
        assert len(stub_msgs) == 0


class TestOptOut:
    """Checker respects stub-opt-out patterns."""

    def test_opted_out_by_directory(self):
        msgs = _walk_close_release_with_config(
            code="x = 1\n",
            file_path="/workspace/src/generated/foo.py",
            source_roots=["/workspace/src"],
            stub_opt_out=["src/generated/"],
        )
        stub_msgs = [m for m in msgs if m.msg_id == "missing-module-stub"]
        assert len(stub_msgs) == 0

    def test_opted_out_by_filename(self):
        msgs = _walk_close_release_with_config(
            code="x = 1\n",
            file_path="/workspace/src/vendor/external.py",
            source_roots=["/workspace/src"],
            stub_opt_out=["src/vendor/"],
        )
        stub_msgs = [m for m in msgs if m.msg_id == "missing-module-stub"]
        assert len(stub_msgs) == 0


class TestStubResolution:
    """Checker resolves .pyi companions correctly."""

    def test_no_stub_no_error_on_empty(self):
        tc = _make_tc()
        tc.checker.open()
        tc.checker.close()
        msgs = tc.linter.release_messages()
        stub_msgs = [m for m in msgs if m.msg_id == "missing-module-stub"]
        assert len(stub_msgs) == 0

    def test_inline_stub_detected(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "has_stub.py").write_text("x = 1\n")
        (src / "has_stub.pyi").write_text("x: int\n")
        tc = _make_tc()
        tc.checker.open()
        module = astroid.parse("x = 1\n", module_name="has_stub")
        module.file = str(src / "has_stub.py")
        tc.walk(module)
        tc.checker.close()
        msgs = tc.linter.release_messages()
        stub_msgs = [m for m in msgs if m.msg_id == "missing-module-stub"]
        assert len(stub_msgs) == 0

    def test_package_init_stub_detected(self, tmp_path: Path):
        pkg = tmp_path / "src" / "mypkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("x = 1\n")
        (pkg / "__init__.pyi").write_text("x: int\n")
        tc = _make_tc()
        tc.checker.open()
        module = astroid.parse("x = 1\n", module_name="mypkg")
        module.file = str(pkg / "__init__.py")
        tc.walk(module)
        tc.checker.close()
        msgs = tc.linter.release_messages()
        stub_msgs = [m for m in msgs if m.msg_id == "missing-module-stub"]
        assert len(stub_msgs) == 0

    def test_stub_root_resolution(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "foo.py").write_text("x = 1\n")
        stub_root = tmp_path / "stubs"
        stub_root.mkdir()
        (stub_root / "foo.pyi").write_text("x: int\n")
        tc = _make_tc()
        tc.linter.config.stub_roots = [str(stub_root)]
        tc.checker.open()
        module = astroid.parse("x = 1\n", module_name="foo")
        module.file = str(src / "foo.py")
        tc.walk(module)
        tc.checker.close()
        msgs = tc.linter.release_messages()
        stub_msgs = [m for m in msgs if m.msg_id == "missing-module-stub"]
        assert len(stub_msgs) == 0

    def test_missing_stub_emits_e97a0(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "unstubbed.py").write_text("y = 2\n")
        tc = _make_tc()
        tc.linter.config.source_roots = [str(src)]
        tc.checker.open()
        module = astroid.parse("y = 2\n", module_name="unstubbed")
        module.file = str(src / "unstubbed.py")
        tc.walk(module)
        tc.checker.close()
        msgs = tc.linter.release_messages()
        stub_msgs = [m for m in msgs if m.msg_id == "missing-module-stub"]
        assert len(stub_msgs) > 0


class TestObservability:
    """Checker produces observable evidence of its decisions."""

    def test_close_produces_log_record(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        import logging
        caplog.set_level(logging.INFO)
        tc = _make_tc()
        tc.checker.open()
        mock_node = MagicMock()
        mock_node.name = "mod_a"
        tc.checker._coverage.module_index["mod_a"] = (tmp_path / "mod_a.py", mock_node)
        mock_node_b = MagicMock()
        mock_node_b.name = "mod_b"
        tc.checker._coverage.module_index["mod_b"] = (tmp_path / "mod_b.py", mock_node_b)
        mock_node_c = MagicMock()
        mock_node_c.name = "mod_c"
        tc.checker._coverage.module_index["mod_c"] = (tmp_path / "mod_c.py", mock_node_c)
        tc.checker._coverage.production_count = 10
        tc.checker._coverage.stub_found_count = 7
        tc.checker._coverage.stub_missing = {"mod_a", "mod_b", "mod_c"}
        tc.checker.close()
        assert "StubChecker:" in caplog.text
        assert "10" in caplog.text
        assert "7" in caplog.text
        assert "3" in caplog.text

    def test_init_exempt_logs_record(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        import logging
        caplog.set_level(logging.INFO)
        src = tmp_path / "src"
        pkg = src / "mypkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("from .sub import Foo\n")
        _walk_close_release_with_config(
            code="from .sub import Foo\n",
            file_path=str(pkg / "__init__.py"),
            source_roots=[str(src)],
            module_name="mypkg",
        )
        assert "Exempt mypkg: __init__.py" in caplog.text

    def test_main_exempt_logs_record(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        import logging
        caplog.set_level(logging.INFO)
        src = tmp_path / "src"
        src.mkdir()
        (src / "script.py").write_text("""
def run():
    pass
if __name__ == '__main__':
    run()
""")
        _walk_close_release_with_config(
            code="""
def run():
    pass
if __name__ == '__main__':
    run()
""",
            file_path=str(src / "script.py"),
            source_roots=[str(src)],
            module_name="script",
        )
        assert "Exempt script: standalone" in caplog.text

    def test_open_initialises_all_state(self):
        tc = _make_tc()
        tc.checker.open()
        assert tc.checker._coverage.production_count == 0
        assert tc.checker._coverage.stub_found_count == 0
        assert tc.checker._coverage.stub_missing == set()
        assert tc.checker._coverage.module_index == {}
        assert tc.checker._coverage.stub_index == {}
        assert tc.checker._coverage.declaration_index == {}
        assert tc.checker._coverage.import_usages == []

    def test_conftest_exempt_logs_record(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        import logging
        caplog.set_level(logging.INFO)
        src = tmp_path / "src"
        src.mkdir()
        cf = src / "conftest.py"
        cf.write_text("import pytest\n")
        _walk_close_release_with_config(
            code="import pytest\n",
            file_path=str(cf),
            source_roots=[str(src)],
            module_name="conftest_root",
        )
        assert "Exempt conftest_root: conftest.py" in caplog.text

    def test_trivial_test_data_exempt_logs_record(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        import logging
        caplog.set_level(logging.INFO)
        data_dir = tmp_path / "tests" / "data"
        data_dir.mkdir(parents=True)
        data_file = data_dir / "fixture_data.py"
        data_file.write_text("x = 1\ny = 'hello'\n")
        _walk_close_release_with_config(
            code="x = 1\ny = 'hello'\n",
            file_path=str(data_file),
            source_roots=[str(tmp_path / "src")],
            module_name="tests.data.fixture_data",
        )
        assert "Exempt tests.data.fixture_data: trivial test data" in caplog.text

    def test_trivial_test_data_under_source_root_still_flagged(self, tmp_path: Path, caplog: pytest.LogCaptureFixture):
        import logging
        caplog.set_level(logging.INFO)
        src = tmp_path / "src"
        src.mkdir()
        prod_file = src / "constants.py"
        prod_file.write_text("x = 1\ny = 2\n")
        tc = _make_tc()
        tc.linter.config.source_roots = [str(src)]
        tc.checker.open()
        module = astroid.parse("x = 1\ny = 2\n", module_name="constants")
        module.file = str(prod_file)
        tc.walk(module)
        tc.checker.close()
        msgs = tc.linter.release_messages()
        e97a0 = [m for m in msgs if m.msg_id == "missing-module-stub"]
        assert len(e97a0) > 0
        assert "trivial test data" not in caplog.text


class TestImportUsage:
    """ImportUsage dataclass fields."""

    def test_import_usage_fields(self):
        u = ImportUsage(
            importer_module="mod_a",
            lineno=5,
            target_module="mod_b",
            symbol_name="Foo",
            alias=None,
            is_star=False,
        )
        assert u.importer_module == "mod_a"
        assert u.lineno == 5
        assert u.target_module == "mod_b"
        assert u.symbol_name == "Foo"
        assert u.alias is None
        assert not u.is_star

    def test_import_usage_module_import(self):
        u = ImportUsage(
            importer_module="mod_a",
            lineno=3,
            target_module="mod_b",
            symbol_name=None,
            alias=None,
            is_star=False,
        )
        assert u.symbol_name is None

    def test_import_usage_star_import(self):
        u = ImportUsage(
            importer_module="mod_a",
            lineno=7,
            target_module="mod_b",
            symbol_name="*",
            alias=None,
            is_star=True,
        )
        assert u.is_star


class TestInTypeCheckingBlock:
    """_in_type_checking_block detects TYPE_CHECKING guards."""

    def test_under_type_checking(self):
        code = """
if TYPE_CHECKING:
    from foo import Bar
"""
        module = astroid.parse(code)
        import_node = module.body[0].orelse[0] if hasattr(module.body[0], 'orelse') and module.body[0].orelse else None
        if import_node is None:
            # Try different AST structure
            pass
        # Direct test: parse and check body
        if_node = module.body[0]
        import_node = if_node.body[0]
        assert _in_type_checking_block(import_node) is True

    def test_not_under_type_checking(self):
        code = "from foo import Bar\n"
        module = astroid.parse(code)
        import_node = module.body[0]
        assert _in_type_checking_block(import_node) is False

    def test_nested_inside_type_checking(self):
        code = """
if TYPE_CHECKING:
    if True:
        from foo import Bar
"""
        module = astroid.parse(code)
        outer_if = module.body[0]
        inner_if = outer_if.body[0]
        import_node = inner_if.body[0]
        assert _in_type_checking_block(import_node) is True


class TestIsTypeCheckingGuard:
    """_is_type_checking_guard detects TYPE_CHECKING name/attribute."""

    def test_name_form(self):
        node = astroid.parse("TYPE_CHECKING").body[0].value
        assert _is_type_checking_guard(node) is True

    def test_typing_dot_name(self):
        # This is an Attribute form
        code = "typing.TYPE_CHECKING"
        module = astroid.parse(code)
        expr = module.body[0].value
        assert _is_type_checking_guard(expr) is True

    def test_other_name(self):
        module = astroid.parse("SOME_FLAG")
        name = module.body[0].value
        assert _is_type_checking_guard(name) is False

    def test_other_attribute(self):
        module = astroid.parse("os.name")
        attr = module.body[0].value
        assert _is_type_checking_guard(attr) is False


class TestResolveRelative:
    """_resolve_relative resolves relative imports correctly."""

    def test_absolute_import(self):
        result = _resolve_relative("mod_a", 0, "os")
        assert result == "os"

    def test_absolute_no_modname(self):
        result = _resolve_relative("mod_a", 0, None)
        assert result == ""

    def test_same_package_init(self):
        result = _resolve_relative("mypkg", 1, None, is_package=True)
        assert result == "mypkg"

    def test_same_package_init_with_name(self):
        result = _resolve_relative("mypkg", 1, "mod_a", is_package=True)
        assert result == "mypkg.mod_a"

    def test_parent_package(self):
        result = _resolve_relative("mypkg.mod_a", 2, "sibling", is_package=False)
        assert result == "sibling"

    def test_grandparent_package(self):
        result = _resolve_relative("pkg.sub.mod_a", 3, "other", is_package=False)
        assert result == "other"

    def test_level_exceeds_depth(self):
        result = _resolve_relative("mod_a", 3, "other", is_package=True)
        assert result == "other"


class TestImportContractViolations:
    """emit_import_contract_violations emits E97A1/E97A2/E97A3."""

    def _setup_checker(self, module_index=None, stub_index=None, declaration_index=None, import_usages=None):
        tc = _make_tc()
        c = tc.checker._coverage
        if module_index:
            c.module_index = module_index
        if stub_index:
            c.stub_index = stub_index
        if declaration_index:
            c.declaration_index = declaration_index
        if import_usages:
            c.import_usages = import_usages
        # Ensure importer modules are in module_index so add_message gets a real node
        for usage in (import_usages or []):
            if usage.importer_module not in c.module_index:
                mock_node = MagicMock()
                mock_node.name = usage.importer_module
                mock_node.position = None
                c.module_index[usage.importer_module] = (Path(f"/workspace/src/{usage.importer_module}.py"), mock_node)
        return tc

    def test_e97a2_when_target_no_stub(self):
        mock_node = MagicMock()
        mock_node.name = "mod_a"
        tc = self._setup_checker(
            module_index={"mod_a": (Path("/workspace/src/mod_a.py"), mock_node)},
            stub_index={},
            import_usages=[
                ImportUsage("mod_a", 1, "mod_a", "Foo", None, False),
            ],
        )
        emit_import_contract_violations(tc.checker)
        msgs = tc.linter.release_messages()
        e97a2 = [m for m in msgs if m.msg_id == "missing-module-stub-for-import"]
        assert len(e97a2) == 1

    def test_e97a1_when_symbol_not_declared(self):
        mock_node = MagicMock()
        mock_node.name = "mod_b"
        tc = self._setup_checker(
            module_index={"mod_b": (Path("/workspace/src/mod_b.py"), mock_node)},
            stub_index={"mod_b": Path("/workspace/src/mod_b.pyi")},
            declaration_index={"mod_b": {"Foo"}},
            import_usages=[
                ImportUsage("mod_a", 1, "mod_b", "Bar", None, False),
            ],
        )
        emit_import_contract_violations(tc.checker)
        msgs = tc.linter.release_messages()
        e97a1 = [m for m in msgs if m.msg_id == "missing-import-declaration"]
        assert len(e97a1) == 1

    def test_no_violation_when_symbol_declared(self):
        mock_node = MagicMock()
        mock_node.name = "mod_b"
        tc = self._setup_checker(
            module_index={"mod_b": (Path("/workspace/src/mod_b.py"), mock_node)},
            stub_index={"mod_b": Path("/workspace/src/mod_b.pyi")},
            declaration_index={"mod_b": {"Foo"}},
            import_usages=[
                ImportUsage("mod_a", 1, "mod_b", "Foo", None, False),
            ],
        )
        emit_import_contract_violations(tc.checker)
        msgs = tc.linter.release_messages()
        assert len(msgs) == 0

    def test_e97a3_star_import(self):
        mock_node = MagicMock()
        mock_node.name = "mod_b"
        tc = self._setup_checker(
            module_index={"mod_b": (Path("/workspace/src/mod_b.py"), mock_node)},
            stub_index={"mod_b": Path("/workspace/src/mod_b.pyi")},
            import_usages=[
                ImportUsage("mod_a", 1, "mod_b", "*", None, True),
            ],
        )
        tc.checker._coverage.star_import_policy = "error"
        emit_import_contract_violations(tc.checker)
        msgs = tc.linter.release_messages()
        e97a3 = [m for m in msgs if m.msg_id == "star-import-unresolvable"]
        assert len(e97a3) == 1


class TestVariableFidelity:
    """Variable annotation fidelity between stub and impl."""

    def test_classvar_skipped(self):
        node = astroid.extract_node("ClassVar[int]")
        assert _is_classvar(node) is True

    def test_non_classvar(self):
        node = astroid.extract_node("int")
        assert _is_classvar(node) is False

    def test_annotation_normalizer(self):
        module = astroid.parse("x: str | None", module_name="test")
        ann = module.body[0].annotation
        result = AnnotationNormalizer.normalize(ann)
        assert result == "str | None"


class TestStarImportPolicy:
    """Star import policy config affects E97A3 emission."""

    def test_star_policy_error(self):
        mock_b = MagicMock()
        mock_b.name = "mod_b"
        mock_b.position = None
        mock_a = MagicMock()
        mock_a.name = "mod_a"
        mock_a.position = None
        tc = _make_tc()
        tc.checker._coverage.module_index = {
            "mod_a": (Path("/workspace/src/mod_a.py"), mock_a),
            "mod_b": (Path("/workspace/src/mod_b.py"), mock_b),
        }
        tc.checker._coverage.stub_index = {"mod_b": Path("/workspace/src/mod_b.pyi")}
        tc.checker._coverage.star_import_policy = "error"
        tc.checker._coverage.import_usages = [
            ImportUsage("mod_a", 1, "mod_b", "*", None, True),
        ]
        emit_import_contract_violations(tc.checker)
        msgs = tc.linter.release_messages()
        e97a3 = [m for m in msgs if m.msg_id == "star-import-unresolvable"]
        assert len(e97a3) == 1

    def test_star_policy_ignore(self):
        mock_b = MagicMock()
        mock_b.name = "mod_b"
        mock_b.position = None
        mock_a = MagicMock()
        mock_a.name = "mod_a"
        mock_a.position = None
        tc = _make_tc()
        tc.checker._coverage.module_index = {
            "mod_a": (Path("/workspace/src/mod_a.py"), mock_a),
            "mod_b": (Path("/workspace/src/mod_b.py"), mock_b),
        }
        tc.checker._coverage.stub_index = {"mod_b": Path("/workspace/src/mod_b.pyi")}
        tc.checker._coverage.star_import_policy = "ignore"
        tc.checker._coverage.import_usages = [
            ImportUsage("mod_a", 1, "mod_b", "*", None, True),
        ]
        emit_import_contract_violations(tc.checker)
        msgs = tc.linter.release_messages()
        e97a3 = [m for m in msgs if m.msg_id == "star-import-unresolvable"]
        assert len(e97a3) == 0


class TestEndToEnd:
    """End-to-end tests exercising the full StubChecker pipeline."""

    def test_complete_pipeline(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "__init__.pyi").write_text("")
        (src / "mod_a.py").write_text("x: int = 1\n")
        (src / "mod_a.pyi").write_text("x: int\n")
        (src / "mod_b.py").write_text("from mod_a import x\n")
        tc = _make_tc()
        tc.linter.config.source_roots = [str(src)]
        tc.checker.open()

        for mod_name, code in [("mod_a", "x: int = 1\n"), ("mod_b", "from mod_a import x\n")]:
            module = astroid.parse(code, module_name=mod_name)
            module.file = str(src / f"{mod_name}.py")
            tc.walk(module)

        tc.checker.close()
        msgs = tc.linter.release_messages()
        # mod_a has a stub → no E97A0. mod_b has no stub → E97A0.
        e97a0 = [m for m in msgs if m.msg_id == "missing-module-stub"]
        assert len(e97a0) == 1
        assert "mod_b" in e97a0[0].args


class TestEndToEndSubprocess:
    """Integration tests running pylint as a subprocess."""

    SKIP_REASON = "run only in python-setup venv with pylint installed"

    def _run_pylint(self, tmp_path: Path, src_name: str, enable: str):
        src = tmp_path / "src"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "__init__.pyi").write_text("")
        (src / "mod_a.py").write_text("x: int = 1\n")
        (src / "mod_a.pyi").write_text("x: int\n")
        (tmp_path / "pyproject.toml").write_text(
            f"""\
[tool.pylint.MASTER]
load-plugins = "python_setup_lint.checkers.stub_checker"

[tool.pylint.stub-checker]
source-roots = ["{src}"]
"""
        )
        result = subprocess.run(
            [sys.executable, "-m", "pylint", str(src), "--disable=all", f"--enable={enable}"],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env={**__import__("os").environ, "PYTHONPATH": str(PROJECT_SRC)},
        )
        return result.stdout + result.stderr