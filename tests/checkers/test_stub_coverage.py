"""Unit tests for python_setup_lint.checkers.stub_coverage helpers.

Exercises the private helpers directly (private-complex-unit category):
``_matches_path``, ``_is_test_file``, ``_is_opted_out``, ``_is_init_exempt``,
``_is_trivial_test_data``, ``_has_main_block``, ``_is_under_source_root``,
``_resolve_stub``, ``_index_stub_declarations``, ``emit_coverage_violations``.

Fixture-row data lives in ``tests/checkers/_factories.py`` (free LOC).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import astroid
import pytest

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
from tests.checkers._factories import (
    _EMIT_COVERAGE_CASES,
    _HAS_MAIN_BLOCK_CASES,
    _IS_INIT_EXEMPT_CASES,
    _IS_OPTED_OUT_CASES,
    _IS_TEST_FILE_CASES,
    _IS_TEST_FILE_CUSTOM_CASES,
    _IS_TRIVIAL_TEST_DATA_CASES,
    _IS_UNDER_SOURCE_ROOT_CASES,
    _MATCHES_PATH_CASES,
    _RESOLVE_STUB_CASES,
    make_coverage_checker,
    make_emit_coverage_state,
    materialize_resolve_stub_layout,
)

if TYPE_CHECKING:
    import pytest as _pytest  # noqa: F401


def _parse(code: str, module_name: str = "") -> astroid.Module:
    return astroid.parse(code, module_name=module_name)


# ── _matches_path ──────────────────────────────────────────────────


@pytest.mark.parametrize("path, patterns, expected", _MATCHES_PATH_CASES)
def test_matches_path(path: str, patterns: list[str], expected: bool) -> None:
    assert _matches_path(path, patterns) is expected


# ── _is_test_file ──────────────────────────────────────────────────


@pytest.mark.parametrize("path, test_patterns, expected", _IS_TEST_FILE_CASES)
def test_is_test_file(path: str, test_patterns: list[str], expected: bool) -> None:
    checker, _tc = make_coverage_checker(test_patterns=test_patterns)
    assert _is_test_file(checker, Path(path)) is expected


@pytest.mark.parametrize("path, test_patterns, expected", _IS_TEST_FILE_CUSTOM_CASES)
def test_is_test_file_custom(
    path: str, test_patterns: list[str], expected: bool,
) -> None:
    """Custom test_patterns=['specs/'] matches specs/ but NOT tests/."""
    checker, _tc = make_coverage_checker(test_patterns=test_patterns)
    assert _is_test_file(checker, Path(path)) is expected


# ── _is_opted_out ──────────────────────────────────────────────────


@pytest.mark.parametrize("path, opt_out_patterns, expected", _IS_OPTED_OUT_CASES)
def test_is_opted_out(path: str, opt_out_patterns: list[str], expected: bool) -> None:
    checker, _tc = make_coverage_checker(stub_opt_out=opt_out_patterns)
    assert _is_opted_out(checker, Path(path)) is expected


# ── _is_init_exempt ────────────────────────────────────────────────


@pytest.mark.parametrize("code, expected", _IS_INIT_EXEMPT_CASES)
def test_is_init_exempt(code: str, expected: bool) -> None:
    assert _is_init_exempt(_parse(code)) is expected


# ── _is_trivial_test_data ──────────────────────────────────────────


@pytest.mark.parametrize("code, expected", _IS_TRIVIAL_TEST_DATA_CASES)
def test_is_trivial_test_data(code: str, expected: bool) -> None:
    assert _is_trivial_test_data(_parse(code)) is expected


# ── _has_main_block ────────────────────────────────────────────────


@pytest.mark.parametrize("code, expected", _HAS_MAIN_BLOCK_CASES)
def test_has_main_block(code: str, expected: bool) -> None:
    assert _has_main_block(_parse(code)) is expected


# ── _is_under_source_root ──────────────────────────────────────────


@pytest.mark.parametrize("path, source_roots, expected", _IS_UNDER_SOURCE_ROOT_CASES)
def test_is_under_source_root(
    path: str, source_roots: list[str], expected: bool,
) -> None:
    checker, _tc = make_coverage_checker(source_roots=source_roots)
    assert _is_under_source_root(checker, Path(path)) is expected


# ── _resolve_stub ──────────────────────────────────────────────────


@pytest.mark.parametrize("layout_kind, expected_kind", _RESOLVE_STUB_CASES)
def test_resolve_stub(
    tmp_path: Path, layout_kind: str, expected_kind: str,
) -> None:
    """Each row exercises one .pyi companion-resolution layout; ``returns_pyi``
    rows assert the resolved path equals the .pyi path; ``returns_none`` rows
    assert ``None`` is returned (no companion).
    """
    checker, py_path, expected_pyi = materialize_resolve_stub_layout(tmp_path, layout_kind)
    result = _resolve_stub(checker, py_path)
    if expected_kind == "returns_pyi":
        assert result == expected_pyi
    elif expected_kind == "returns_none":
        assert result is None
    else:  # pragma: no cover - defensive
        raise AssertionError(f"unknown expected_kind {expected_kind!r}")


# ── _index_stub_declarations ──────────────────────────────────────


def test_index_stub_declarations(tmp_path: Path) -> None:
    """Symbol/class/func declarations are all indexed from a .pyi file."""
    stub_path = tmp_path / "mod.pyi"
    stub_path.write_text("\nx: int\ndef foo(): ...\nclass Bar: ...\n")
    checker, _tc = make_coverage_checker()
    checker._fidelity.stub_variable_nodes["mod"] = {}
    checker._fidelity.stub_callable_nodes["mod"] = {}
    checker._fidelity.stub_class_nodes["mod"] = {}
    _index_stub_declarations(checker, "mod", stub_path)
    decls = checker._coverage.declaration_index.get("mod", set())
    for s in ("x", "foo", "Bar"):
        assert s in decls


# ── emit_coverage_violations ───────────────────────────────────────


@pytest.mark.parametrize(
    "setup_kind, stub_missing_module, expected_msg_count", _EMIT_COVERAGE_CASES,
)
def test_emit_coverage_violations(
    tmp_path: Path,
    setup_kind: str,
    stub_missing_module: str,
    expected_msg_count: int,
) -> None:
    """Each row exercises one branch of ``emit_coverage_violations`` (emit /
    no-missing / skip-not-in-index)."""
    tc, _ = make_emit_coverage_state(tmp_path, setup_kind, stub_missing_module)
    emit_coverage_violations(tc.checker)
    msgs = tc.linter.release_messages()
    assert len(msgs) == expected_msg_count
    if expected_msg_count == 1:
        assert msgs[0].msg_id == "missing-module-stub"
