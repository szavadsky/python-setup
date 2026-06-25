"""Unit tests for python_setup_lint.checkers.stub_checker.

Exercises Invariant 1 (coverage), Invariant 2 (import contract), and
Invariant 3 (variable fidelity). Includes T1-pyi-exemption behavior
preservation tests (init/main/conftest/trivial-data early returns —
proven invariants per ``/memories/repo/T1-pyi-exemptions.md``).

Fixture-row data lives in ``tests/checkers/_factories.py`` (free LOC).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import astroid
import pytest

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
from python_setup_lint.testing import _make_tc as _make_tc_factory
from tests.checkers._factories import (
    _IMPORT_CONTRACT_CASES,
    _IMPORT_USAGE_FIELD_CASES,
    _IN_TYPE_CHECKING_BLOCK_NEGATIVE_CASES,
    _IN_TYPE_CHECKING_BLOCK_POSITIVE_CASES,
    _IS_TYPE_CHECKING_GUARD_CASES,
    _PYI_EXEMPT_LOG_LAYOUT_CASES,
    _RESOLVE_RELATIVE_CASES,
    _STAR_POLICY_CASES,
    _STUB_CHECKER_MSGS_CASES,
    _STUB_FILE_CLASSIFICATION_CASES,
    _STUB_RESOLUTION_CASES,
    _VARIABLE_FIDELITY_CASES,
    materialize_pyi_exempt_layout,
    walk_stub_close_release,
    walk_stub_resolution_layout,
)

if TYPE_CHECKING:
    from pathlib import Path
    import pytest  # noqa: F401


def _make_tc() -> Any:
    return _make_tc_factory(StubChecker)


# ── TestCheckerRegistration ────────────────────────────────────────


def test_checker_name() -> None:
    assert _make_tc().checker.name == "stub-checker"  # type: ignore[no-untyped-call]


@pytest.mark.parametrize(("code", "expected_symbol"), _STUB_CHECKER_MSGS_CASES)
def test_message_codes(code: str, expected_symbol: str) -> None:
    msgs = _make_tc().checker.msgs  # type: ignore[no-untyped-call]
    assert code in msgs
    assert msgs[code][1] == expected_symbol


def test_register_function() -> None:
    from python_setup_lint.checkers.stub_checker import register

    mock_linter = MagicMock()
    register(mock_linter)
    mock_linter.register_checker.assert_called_once()
    args = mock_linter.register_checker.call_args[0]
    assert isinstance(args[0], StubChecker)


def test_close_logs_counts(tmp_path: Path) -> None:
    msgs = walk_stub_close_release(  # type: ignore[no-untyped-call]
        code="x = 1\n",
        file_path="/workspace/src/mod.py",
        source_roots=["/workspace/src"],
    )
    e97a0 = [m for m in msgs if m.msg_id == "missing-module-stub"]
    assert len(e97a0) > 0


# ── TestConfigurationParsing ────────────────────────────────────────


def test_default_source_roots() -> None:
    tc = _make_tc()  # type: ignore[no-untyped-call]
    tc.checker.open()
    assert len(tc.checker._coverage.source_roots) == 1
    assert str(tc.checker._coverage.source_roots[0]).endswith("/src")


def test_default_test_patterns() -> None:
    tc = _make_tc()  # type: ignore[no-untyped-call]
    tc.checker.open()
    patterns = tc.checker._coverage.test_patterns
    assert "tests/" in patterns
    assert "test_*.py" in patterns


def test_defaults_opt_out_empty_and_custom_source_root() -> None:
    """Combined: default opt_out is empty; custom_source_root is honoured."""
    tc = _make_tc()  # type: ignore[no-untyped-call]
    tc.checker.open()
    assert tc.checker._coverage.opt_out_patterns == []

    tc2 = _make_tc()  # type: ignore[no-untyped-call]
    tc2.linter.config.source_roots = ["custom_src"]
    tc2.checker.open()
    roots = tc2.checker._coverage.source_roots
    assert any("custom_src" in str(r) for r in roots)


# ── TestFileClassification + TestOptOut ────────────────────────────


@pytest.mark.parametrize(
    (
        "file_path",
        "source_roots",
        "test_patterns",
        "stub_opt_out",
        "expected_e97a0_count",
    ),
    _STUB_FILE_CLASSIFICATION_CASES,
)
def test_file_classification_and_optout(
    file_path: str,
    source_roots: list[str],
    test_patterns: list[str] | None,
    stub_opt_out: list[str] | None,
    expected_e97a0_count: int,
) -> None:
    msgs = walk_stub_close_release(  # type: ignore[no-untyped-call]
        code="x = 1\n",
        file_path=file_path,
        source_roots=source_roots,
        test_patterns=test_patterns,
        stub_opt_out=stub_opt_out,
    )
    e97a0 = [m for m in msgs if m.msg_id == "missing-module-stub"]
    assert len(e97a0) == expected_e97a0_count


def test_production_file_under_src(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "some_module.py").write_text("x = 1\n")
    msgs = walk_stub_close_release(  # type: ignore[no-untyped-call]
        code="x = 1\n",
        file_path=str(src / "some_module.py"),
        source_roots=[str(src)],
    )
    assert len([m for m in msgs if m.msg_id == "missing-module-stub"]) > 0


# ── TestStubResolution ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("layout_kind", "code", "module_name", "expected_e97a0_count"),
    _STUB_RESOLUTION_CASES,
)
def test_stub_resolution_layout(
    tmp_path: Path,
    layout_kind: str,
    code: str,
    module_name: str,
    expected_e97a0_count: int,
) -> None:
    msgs = walk_stub_resolution_layout(tmp_path, layout_kind, code, module_name)  # type: ignore[no-untyped-call]
    assert (
        len([m for m in msgs if m.msg_id == "missing-module-stub"])
        == expected_e97a0_count
    )


# ── TestObservability — close produces log records ─────────────────


def test_close_produces_log_record(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    tc = _make_tc()  # type: ignore[no-untyped-call]
    tc.checker.open()
    for mod_name in ("mod_a", "mod_b", "mod_c"):
        mock_node = MagicMock()
        mock_node.name = mod_name
        tc.checker._coverage.module_index[mod_name] = (
            tmp_path / f"{mod_name}.py",
            mock_node,
        )
    tc.checker._coverage.production_count = 10
    tc.checker._coverage.stub_found_count = 7
    tc.checker._coverage.stub_missing = {"mod_a", "mod_b", "mod_c"}
    tc.checker.close()
    assert "StubChecker:" in caplog.text
    assert "10" in caplog.text
    assert "7" in caplog.text
    assert "3" in caplog.text


def test_open_initialises_all_state() -> None:
    tc = _make_tc()  # type: ignore[no-untyped-call]
    tc.checker.open()
    assert tc.checker._coverage.production_count == 0
    assert tc.checker._coverage.stub_found_count == 0
    assert tc.checker._coverage.stub_missing == set()
    assert tc.checker._coverage.module_index == {}
    assert tc.checker._coverage.stub_index == {}
    assert tc.checker._coverage.declaration_index == {}
    assert tc.checker._coverage.import_usages == []


# ── T1-pyi-exemption behavior tests (proven invariants) ────────────
#
# These tests exercise the init/main/conftest/trivial-data early-return
# branches in the checker. Per ``/memories/repo/T1-pyi-exemptions.md``
# they are PROVEN INVARIANTS — preserve coverage verbatim across
# reductions (the envelope calls this out explicitly).


@pytest.mark.parametrize(
    ("layout_kind", "code", "expected_log_substring"),
    _PYI_EXEMPT_LOG_LAYOUT_CASES,
)
def test_pyi_exemption_logs_record(
    tmp_path: Path,
    layout_kind: str,
    code: str,
    expected_log_substring: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    file_path, source_roots, module_name = materialize_pyi_exempt_layout(  # type: ignore[no-untyped-call]
        tmp_path,
        layout_kind,
        code,
    )
    walk_stub_close_release(  # type: ignore[no-untyped-call]
        code=code,
        file_path=file_path,
        source_roots=source_roots,
        module_name=module_name,
    )
    assert expected_log_substring in caplog.text


def test_trivial_test_data_under_source_root_still_flagged(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Non-exempt counterpart to trivial_data row — preserves the boundary."""
    caplog.set_level(logging.INFO)
    src = tmp_path / "src"
    src.mkdir()
    prod_file = src / "constants.py"
    prod_file.write_text("x = 1\ny = 2\n")
    tc = _make_tc()  # type: ignore[no-untyped-call]
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


# ── TestImportUsage ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("field_overrides", "expected_attr_checks"), _IMPORT_USAGE_FIELD_CASES
)
def test_import_usage_fields(
    field_overrides: dict,
    expected_attr_checks: dict,
) -> None:
    u = ImportUsage(**field_overrides)
    for key, expected in expected_attr_checks.items():
        assert getattr(u, key) == expected


# ── TestInTypeCheckingBlock ────────────────────────────────────────


@pytest.mark.parametrize(("code", "accessor"), _IN_TYPE_CHECKING_BLOCK_POSITIVE_CASES)
def test_in_type_checking_block_positive(code: str, accessor) -> None:
    module = astroid.parse(code)
    import_node = accessor(module)
    assert _in_type_checking_block(import_node) is True


@pytest.mark.parametrize(("code", "accessor"), _IN_TYPE_CHECKING_BLOCK_NEGATIVE_CASES)
def test_in_type_checking_block_negative(code: str, accessor) -> None:
    module = astroid.parse(code)
    import_node = accessor(module)
    assert _in_type_checking_block(import_node) is False


# ── TestIsTypeCheckingGuard ────────────────────────────────────────


@pytest.mark.parametrize(("code", "expected"), _IS_TYPE_CHECKING_GUARD_CASES)
def test_is_type_checking_guard(code: str, expected: bool) -> None:
    node = astroid.parse(code).body[0].value
    assert _is_type_checking_guard(node) is expected


# ── TestResolveRelative ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("modname", "level", "name", "is_package", "expected"),
    _RESOLVE_RELATIVE_CASES,
)
def test_resolve_relative(
    modname: str,
    level: int,
    name: str | None,
    is_package: bool,
    expected: str,
) -> None:
    """Each row exercises one relative-import resolution branch."""
    result = _resolve_relative(modname, level, name, is_package=is_package)
    assert result == expected


# ── TestImportContractViolations ──────────────────────────────────


@pytest.mark.parametrize(
    (
        "target_module",
        "has_stub",
        "declared_symbols",
        "importer",
        "symbol",
        "is_star",
        "star_policy",
        "expected_msg_id",
        "expected_count",
    ),
    _IMPORT_CONTRACT_CASES,
)
def test_emit_import_contract_violations(
    target_module: str,
    has_stub: bool,
    declared_symbols: set[str] | None,
    importer: str,
    symbol: str | None,
    is_star: bool,
    star_policy: str | None,
    expected_msg_id: str | None,
    expected_count: int,
) -> None:
    from tests.checkers._factories import setup_and_emit_import_contract

    _tc, msgs = setup_and_emit_import_contract(
        target_module=target_module,
        has_stub=has_stub,
        declared_symbols=declared_symbols,
        importer=importer,
        symbol=symbol,
        is_star=is_star,
        star_policy=star_policy,
    )
    if expected_msg_id is None:
        assert len(msgs) == 0
    else:
        matching = [m for m in msgs if m.msg_id == expected_msg_id]
        assert len(matching) == expected_count


# ── TestStarImportPolicy ──────────────────────────────────────────


@pytest.mark.parametrize(("star_policy", "expected_e97a3_count"), _STAR_POLICY_CASES)
def test_star_import_policy(star_policy: str, expected_e97a3_count: int) -> None:
    from tests.checkers._factories import (
        _build_star_import_policy_state,
        _star_usage_factory,
    )

    tc, checker = _build_star_import_policy_state(star_policy, _star_usage_factory)
    emit_import_contract_violations(checker)
    msgs = tc.linter.release_messages()
    e97a3 = [m for m in msgs if m.msg_id == "star-import-unresolvable"]
    assert len(e97a3) == expected_e97a3_count


# ── TestVariableFidelity ──────────────────────────────────────────


@pytest.mark.parametrize(("expr_src", "expected_bool"), _VARIABLE_FIDELITY_CASES)
def test_is_classvar(expr_src: str, expected_bool: bool) -> None:
    node = astroid.extract_node(expr_src)
    assert _is_classvar(node) is expected_bool


def test_annotation_normalizer_normalize() -> None:
    module = astroid.parse("x: str | None", module_name="test")
    ann = module.body[0].annotation
    assert AnnotationNormalizer.normalize(ann) == "str | None"


# ── TestEndToEnd ──────────────────────────────────────────────────


def test_complete_pipeline(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "__init__.pyi").write_text("")
    (src / "mod_a.py").write_text("x: int = 1\n")
    (src / "mod_a.pyi").write_text("x: int\n")
    (src / "mod_b.py").write_text("from mod_a import x\n")
    tc = _make_tc()  # type: ignore[no-untyped-call]
    tc.linter.config.source_roots = [str(src)]
    tc.checker.open()
    for mod_name, code in [
        ("mod_a", "x: int = 1\n"),
        ("mod_b", "from mod_a import x\n"),
    ]:
        module = astroid.parse(code, module_name=mod_name)
        module.file = str(src / f"{mod_name}.py")
        tc.walk(module)
    tc.checker.close()
    msgs = tc.linter.release_messages()
    # mod_a has a stub → no E97A0. mod_b has no stub → E97A0.
    e97a0 = [m for m in msgs if m.msg_id == "missing-module-stub"]
    assert len(e97a0) == 1
    assert "mod_b" in e97a0[0].args


# ── TestEndToEndSubprocess ────────────────────────────────────────
#
# The pre-T14 ``TestEndToEndSubprocess`` class only declared a ``_run_pylint``
# helper without invoking it — no actual test cases existed there. The
# ``test_complete_pipeline`` above exercises the full open/walk/close flow
# in-process. The ``--disable=all --enable=missing-module-stub`` invocation
# the helper used (a pylint builtin behavior test, not a StubChecker
# behavior test) is the tautology-test pattern T14 deletes per the brief.
