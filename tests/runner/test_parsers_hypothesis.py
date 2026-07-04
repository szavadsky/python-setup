"""Hypothesis property tests for record and statistics parsers.

Tests invariants:
1. Parse idempotency: parsing same input twice yields identical sorted list
2. Sort order: result is sorted by _compare_records_key
3. Empty/garbage safety: empty string, whitespace, random garbage never raises
4. Statistics parsers: all counts >= 0
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from python_setup_lint.runner import Record
from python_setup_lint.runner._record_parsers import (
    _parse_mypy_records,
    _parse_pylint_records,
    _parse_pyright_records,
    _parse_ruff_records,
    _parse_rumdl_records,
    _parse_ty_records,
    _parse_yamllint_records,
)
from python_setup_lint.runner._record_types import _compare_records_key
from python_setup_lint.runner.parsers import (
    _parse_detect_secrets_json,
    _parse_mypy_stderr,
    _parse_pylint_json2,
    _parse_pyright_outputjson,
    _parse_pyright_verify_types,
    _parse_ruff_statistics,
    _parse_rumdl_statistics,
    _parse_stubtest_stderr,
    _parse_tach_json,
    _parse_ty_concise,
    _parse_yamllint_parsable,
)

pytestmark = pytest.mark.no_external_api

# ── Strategies ──────────────────────────────────────────────────────

# Text strategies for record parsers
_ascii_text = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
    min_size=0,
    max_size=200,
)

# JSON strategies for pyright and other JSON-based parsers
_json_value = st.recursive(
    st.none() | st.booleans() | st.floats(allow_nan=False, allow_infinity=False) | st.integers() | st.text(max_size=50),
    lambda children: st.lists(children, max_size=5) | st.dictionaries(st.text(max_size=20), children, max_size=5),
    max_leaves=10,
)


# ── Record parser invariants ────────────────────────────────────────


def _check_record_invariants(records: list[Record], parser: Callable[[str], list[Record]], text: str) -> None:
    """Check common invariants for record parsers."""
    # 1. Idempotency: parsing same input twice yields identical sorted list
    records2 = parser(text)
    assert len(records) == len(records2)
    for r1, r2 in zip(records, records2, strict=True):
        assert r1 == r2

    # 2. Sort order: result is sorted by _compare_records_key
    for i in range(1, len(records)):
        assert _compare_records_key(records[i - 1]) <= _compare_records_key(records[i])

    # 3. All records have valid types
    for r in records:
        assert isinstance(r.file, (str, type(None)))
        assert isinstance(r.line, (int, type(None)))
        assert isinstance(r.col, (int, type(None)))
        assert isinstance(r.rule, str)
        assert isinstance(r.msg, str)


# ── Ruff ────────────────────────────────────────────────────────────


class TestRuffRecords:
    @given(text=_ascii_text)
    def test_ruff_records_given_any_text_then_never_raises(self, text: str) -> None:  # pylint: disable=trivial-wrapper  # hypothesis test wrapper; delegation pattern required by framework
        _parse_ruff_records(text)

    @given(text=_ascii_text)
    def test_ruff_records_given_any_text_then_invariants_hold(self, text: str) -> None:
        records = _parse_ruff_records(text)
        _check_record_invariants(records, _parse_ruff_records, text)

    def test_ruff_records_given_empty_string_then_empty_list(self) -> None:
        assert _parse_ruff_records("") == []

    def test_ruff_records_given_whitespace_then_empty_list(self) -> None:
        assert _parse_ruff_records("   \n  \t  \n  ") == []


# ── Mypy ────────────────────────────────────────────────────────────


class TestMypyRecords:
    @given(text=_ascii_text)
    def test_mypy_records_given_any_text_then_never_raises(self, text: str) -> None:  # pylint: disable=trivial-wrapper  # hypothesis test wrapper; delegation pattern required by framework
        _parse_mypy_records(text)

    @given(text=_ascii_text)
    def test_mypy_records_given_any_text_then_invariants_hold(self, text: str) -> None:
        records = _parse_mypy_records(text)
        _check_record_invariants(records, _parse_mypy_records, text)

    def test_mypy_records_given_empty_string_then_empty_list(self) -> None:
        assert _parse_mypy_records("") == []

    def test_mypy_records_given_whitespace_then_empty_list(self) -> None:
        assert _parse_mypy_records("   \n  \t  \n  ") == []


# ── Pylint ──────────────────────────────────────────────────────────


class TestPylintRecords:
    @given(text=_ascii_text)
    def test_pylint_records_given_any_text_then_never_raises(self, text: str) -> None:  # pylint: disable=trivial-wrapper  # hypothesis test wrapper; delegation pattern required by framework
        _parse_pylint_records(text)

    @given(text=_ascii_text)
    def test_pylint_records_given_any_text_then_invariants_hold(self, text: str) -> None:
        records = _parse_pylint_records(text)
        _check_record_invariants(records, _parse_pylint_records, text)

    def test_pylint_records_given_empty_string_then_empty_list(self) -> None:
        assert _parse_pylint_records("") == []

    def test_pylint_records_given_whitespace_then_empty_list(self) -> None:
        assert _parse_pylint_records("   \n  \t  \n  ") == []


# ── Ty ──────────────────────────────────────────────────────────────


class TestTyRecords:
    @given(text=_ascii_text)
    def test_ty_records_given_any_text_then_never_raises(self, text: str) -> None:  # pylint: disable=trivial-wrapper  # hypothesis test wrapper; delegation pattern required by framework
        _parse_ty_records(text)

    @given(text=_ascii_text)
    def test_ty_records_given_any_text_then_invariants_hold(self, text: str) -> None:
        records = _parse_ty_records(text)
        _check_record_invariants(records, _parse_ty_records, text)

    def test_ty_records_given_empty_string_then_empty_list(self) -> None:
        assert _parse_ty_records("") == []

    def test_ty_records_given_whitespace_then_empty_list(self) -> None:
        assert _parse_ty_records("   \n  \t  \n  ") == []


# ── Yamllint ────────────────────────────────────────────────────────


class TestYamllintRecords:
    @given(text=_ascii_text)
    def test_yamllint_records_given_any_text_then_never_raises(self, text: str) -> None:  # pylint: disable=trivial-wrapper  # hypothesis test wrapper; delegation pattern required by framework
        _parse_yamllint_records(text)

    @given(text=_ascii_text)
    def test_yamllint_records_given_any_text_then_invariants_hold(self, text: str) -> None:
        records = _parse_yamllint_records(text)
        _check_record_invariants(records, _parse_yamllint_records, text)

    def test_yamllint_records_given_empty_string_then_empty_list(self) -> None:
        assert _parse_yamllint_records("") == []

    def test_yamllint_records_given_whitespace_then_empty_list(self) -> None:
        assert _parse_yamllint_records("   \n  \t  \n  ") == []


# ── Rumdl ───────────────────────────────────────────────────────────


class TestRumdlRecords:
    @given(text=_ascii_text)
    def test_rumdl_records_given_any_text_then_never_raises(self, text: str) -> None:  # pylint: disable=trivial-wrapper  # hypothesis test wrapper; delegation pattern required by framework
        _parse_rumdl_records(text)

    @given(text=_ascii_text)
    def test_rumdl_records_given_any_text_then_invariants_hold(self, text: str) -> None:
        records = _parse_rumdl_records(text)
        _check_record_invariants(records, _parse_rumdl_records, text)

    def test_rumdl_records_given_empty_string_then_empty_list(self) -> None:
        assert _parse_rumdl_records("") == []

    def test_rumdl_records_given_whitespace_then_empty_list(self) -> None:
        assert _parse_rumdl_records("   \n  \t  \n  ") == []


# ── Pyright ─────────────────────────────────────────────────────────


class TestPyrightRecords:
    @given(
        data=st.none()
        | st.booleans()
        | st.floats(allow_nan=False, allow_infinity=False)
        | st.integers()
        | st.text(max_size=50)
        | st.lists(_json_value, max_size=5)
        | st.dictionaries(st.text(max_size=20), _json_value, max_size=5)
    )
    def test_pyright_records_given_any_input_then_never_raises(self, data: object) -> None:  # pylint: disable=trivial-wrapper  # hypothesis test wrapper; delegation pattern required by framework
        _parse_pyright_records(data)

    @given(data=st.dictionaries(st.text(max_size=20), _json_value, max_size=5))
    def test_pyright_records_given_any_input_then_invariants_hold(self, data: dict[str, Any]) -> None:
        records = _parse_pyright_records(data)
        # Sort order
        for i in range(1, len(records)):
            assert _compare_records_key(records[i - 1]) <= _compare_records_key(records[i])
        # All records have valid types
        for r in records:
            assert isinstance(r.file, (str, type(None)))
            assert isinstance(r.line, (int, type(None)))
            assert isinstance(r.col, (int, type(None)))
            assert isinstance(r.rule, str)
            assert isinstance(r.msg, str)

    def test_pyright_records_given_empty_dict_then_empty_list(self) -> None:
        assert _parse_pyright_records({}) == []

    def test_pyright_records_given_none_then_empty_list(self) -> None:
        assert _parse_pyright_records(None) == []


# ── Statistics parsers ──────────────────────────────────────────────


def _check_statistics_invariants(
    result: list[tuple[str, int]], parser: Callable[[str, str], list[tuple[str, int]]], stdout: str, stderr: str = ""
) -> None:
    """Check common invariants for statistics parsers."""
    # 1. Idempotency
    result2 = parser(stdout, stderr)
    assert result == result2

    # 2. All counts >= 0
    for rule, count in result:
        assert isinstance(rule, str)
        assert isinstance(count, int)
        assert count >= 0

    # 3. No duplicate rules
    rules = [r for r, _ in result]
    assert len(rules) == len(set(rules))


class TestRuffStatistics:
    @given(text=_ascii_text)
    def test_ruff_statistics_given_any_text_then_never_raises(self, text: str) -> None:  # pylint: disable=trivial-wrapper  # hypothesis test wrapper; delegation pattern required by framework
        _parse_ruff_statistics(text, "")

    @given(text=_ascii_text)
    def test_ruff_statistics_given_any_text_then_invariants_hold(self, text: str) -> None:
        result = _parse_ruff_statistics(text, "")
        _check_statistics_invariants(result, _parse_ruff_statistics, text, "")

    def test_ruff_statistics_given_empty_string_then_empty_list(self) -> None:
        assert _parse_ruff_statistics("", "") == []


class TestRumdlStatistics:
    @given(text=_ascii_text)
    def test_rumdl_statistics_given_any_text_then_never_raises(self, text: str) -> None:  # pylint: disable=trivial-wrapper  # hypothesis test wrapper; delegation pattern required by framework
        _parse_rumdl_statistics(text, "")

    @given(text=_ascii_text)
    def test_rumdl_statistics_given_any_text_then_invariants_hold(self, text: str) -> None:
        result = _parse_rumdl_statistics(text, "")
        _check_statistics_invariants(result, _parse_rumdl_statistics, text, "")

    def test_rumdl_statistics_given_empty_string_then_empty_list(self) -> None:
        assert _parse_rumdl_statistics("", "") == []


class TestPylintJson2:
    @given(text=_ascii_text)
    def test_pylint_json2_given_any_text_then_never_raises(self, text: str) -> None:  # pylint: disable=trivial-wrapper  # hypothesis test wrapper; delegation pattern required by framework
        _parse_pylint_json2(text, "")

    @given(text=_ascii_text)
    def test_pylint_json2_given_any_text_then_invariants_hold(self, text: str) -> None:
        result = _parse_pylint_json2(text, "")
        _check_statistics_invariants(result, _parse_pylint_json2, text, "")

    def test_pylint_json2_given_empty_string_then_empty_list(self) -> None:
        assert _parse_pylint_json2("", "") == []

    def test_pylint_json2_given_valid_json_no_messages_then_empty_list(self) -> None:
        assert _parse_pylint_json2('{"messages": []}', "") == []


class TestPyrightOutputjson:
    @given(text=_ascii_text)
    def test_pyright_outputjson_given_any_text_then_never_raises(self, text: str) -> None:  # pylint: disable=trivial-wrapper  # hypothesis test wrapper; delegation pattern required by framework
        _parse_pyright_outputjson(text, "")

    @given(text=_ascii_text)
    def test_pyright_outputjson_given_any_text_then_invariants_hold(self, text: str) -> None:
        result = _parse_pyright_outputjson(text, "")
        _check_statistics_invariants(result, _parse_pyright_outputjson, text, "")

    def test_pyright_outputjson_given_empty_string_then_empty_list(self) -> None:
        assert _parse_pyright_outputjson("", "") == []

    def test_pyright_outputjson_given_valid_json_no_diagnostics_then_empty_list(self) -> None:
        assert _parse_pyright_outputjson('{"generalDiagnostics": []}', "") == []


class TestPyrightVerifyTypes:
    @given(text=_ascii_text)
    def test_pyright_verify_types_given_any_text_then_never_raises(self, text: str) -> None:  # pylint: disable=trivial-wrapper  # hypothesis test wrapper; delegation pattern required by framework
        _parse_pyright_verify_types(text, "")

    @given(text=_ascii_text)
    def test_pyright_verify_types_given_any_text_then_invariants_hold(self, text: str) -> None:
        result = _parse_pyright_verify_types(text, "")
        _check_statistics_invariants(result, _parse_pyright_verify_types, text, "")

    def test_pyright_verify_types_given_empty_string_then_empty_list(self) -> None:
        assert _parse_pyright_verify_types("", "") == []

    def test_pyright_verify_types_given_valid_json_no_type_completeness_then_empty_list(self) -> None:
        assert _parse_pyright_verify_types("{}", "") == []


class TestMypyStderr:
    @given(text=_ascii_text)
    def test_mypy_stderr_given_any_text_then_never_raises(self, text: str) -> None:  # pylint: disable=trivial-wrapper  # hypothesis test wrapper; delegation pattern required by framework
        _parse_mypy_stderr("", text)

    @given(text=_ascii_text)
    def test_mypy_stderr_given_any_text_then_invariants_hold(self, text: str) -> None:
        result = _parse_mypy_stderr("", text)
        _check_statistics_invariants(result, _parse_mypy_stderr, "", text)

    def test_mypy_stderr_given_empty_string_then_empty_list(self) -> None:
        assert _parse_mypy_stderr("", "") == []


class TestTyConcise:
    @given(text=_ascii_text)
    def test_ty_concise_given_any_text_then_never_raises(self, text: str) -> None:  # pylint: disable=trivial-wrapper  # hypothesis test wrapper; delegation pattern required by framework
        _parse_ty_concise(text, "")

    @given(text=_ascii_text)
    def test_ty_concise_given_any_text_then_invariants_hold(self, text: str) -> None:
        result = _parse_ty_concise(text, "")
        _check_statistics_invariants(result, _parse_ty_concise, text, "")

    def test_ty_concise_given_empty_string_then_empty_list(self) -> None:
        assert _parse_ty_concise("", "") == []


class TestTachJson:
    @given(text=_ascii_text)
    def test_tach_json_given_any_text_then_never_raises(self, text: str) -> None:  # pylint: disable=trivial-wrapper  # hypothesis test wrapper; delegation pattern required by framework
        _parse_tach_json(text, "")

    @given(text=_ascii_text)
    def test_tach_json_given_any_text_then_invariants_hold(self, text: str) -> None:
        result = _parse_tach_json(text, "")
        _check_statistics_invariants(result, _parse_tach_json, text, "")

    def test_tach_json_given_empty_string_then_empty_list(self) -> None:
        assert _parse_tach_json("", "") == []

    def test_tach_json_given_valid_json_no_errors_then_empty_list(self) -> None:
        assert _parse_tach_json('{"errors": []}', "") == []


class TestYamllintParsable:
    @given(text=_ascii_text)
    def test_yamllint_parsable_given_any_text_then_never_raises(self, text: str) -> None:  # pylint: disable=trivial-wrapper  # hypothesis test wrapper; delegation pattern required by framework
        _parse_yamllint_parsable(text, "")

    @given(text=_ascii_text)
    def test_yamllint_parsable_given_any_text_then_invariants_hold(self, text: str) -> None:
        result = _parse_yamllint_parsable(text, "")
        _check_statistics_invariants(result, _parse_yamllint_parsable, text, "")

    def test_yamllint_parsable_given_empty_string_then_empty_list(self) -> None:
        assert _parse_yamllint_parsable("", "") == []


class TestStubtestStderr:
    @given(text=_ascii_text)
    def test_stubtest_stderr_given_any_text_then_never_raises(self, text: str) -> None:  # pylint: disable=trivial-wrapper  # hypothesis test wrapper; delegation pattern required by framework
        _parse_stubtest_stderr("", text)

    @given(text=_ascii_text)
    def test_stubtest_stderr_given_any_text_then_invariants_hold(self, text: str) -> None:
        result = _parse_stubtest_stderr("", text)
        _check_statistics_invariants(result, _parse_stubtest_stderr, "", text)

    def test_stubtest_stderr_given_empty_string_then_empty_list(self) -> None:
        assert _parse_stubtest_stderr("", "") == []


class TestDetectSecretsJson:
    @given(text=_ascii_text)
    def test_detect_secrets_json_given_any_text_then_never_raises(self, text: str) -> None:  # pylint: disable=trivial-wrapper  # hypothesis test wrapper; delegation pattern required by framework
        _parse_detect_secrets_json(text, "")

    @given(text=_ascii_text)
    def test_detect_secrets_json_given_any_text_then_invariants_hold(self, text: str) -> None:
        result = _parse_detect_secrets_json(text, "")
        _check_statistics_invariants(result, _parse_detect_secrets_json, text, "")

    def test_detect_secrets_json_given_empty_string_then_empty_list(self) -> None:
        assert _parse_detect_secrets_json("", "") == []

    def test_detect_secrets_json_given_valid_json_no_results_then_empty_list(self) -> None:
        assert _parse_detect_secrets_json('{"results": {}}', "") == []
