"""Unit tests for python_setup_lint.checkers.generic_key_dict_checker.

Verifies the AST checker detects (and does not detect) ``dict[str, X]``
annotations where X is a domain type.
"""

from __future__ import annotations

from typing import Any

import pytest

from python_setup_lint.checkers.conformance.generic_key_dict_checker import (
    GenericKeyDictChecker,
)
from python_setup_lint.testing import _walk_and_release

_DETECT_CASES: list[Any] = [  # pylint: disable=W9704  # list[Any] is a test factory return type; Any needed for heterogeneous test cases
    pytest.param(
        "x: dict[str, MessageDef]",
        "MessageDef",
        id="dict_str_MessageDef",
    ),
    pytest.param(
        "x: dict[str, Record]",
        "Record",
        id="dict_str_Record",
    ),
    pytest.param(
        "x: dict[str, RuleEntry]",
        "RuleEntry",
        id="dict_str_RuleEntry",
    ),
    pytest.param(
        "x: dict[str, LintResult]",
        "LintResult",
        id="dict_str_LintResult",
    ),
    pytest.param(
        "x: dict[str, ToolSpec]",
        "ToolSpec",
        id="dict_str_ToolSpec",
    ),
    pytest.param(
        "x: dict[str, RunnerConfig]",
        "RunnerConfig",
        id="dict_str_RunnerConfig",
    ),
]

_DO_NOT_DETECT_CASES: list[Any] = [  # pylint: disable=W9704  # list[Any] is a test factory return type; Any needed for heterogeneous test cases
    pytest.param(
        "x: dict[LintRuleId, MessageDef]",
        id="dict_LintRuleId_MessageDef",
    ),
    pytest.param(
        "x: dict[str, Path]",
        id="dict_str_Path_allowed_as_path",
    ),
    pytest.param(
        "x: dict[str, str]",
        id="dict_str_str_not_domain",
    ),
    pytest.param(
        "x: dict[str, int]",
        id="dict_str_int_not_domain",
    ),
    pytest.param(
        "x: dict[str, Any]",
        id="dict_str_Any_not_domain",
    ),
    pytest.param(
        "x: dict[str, object]",
        id="dict_str_object_not_domain",
    ),
    pytest.param(
        "x: dict[str, tuple[str, str, str]]",
        id="dict_str_tuple_not_domain",
    ),
    pytest.param(
        "x: dict[str, set[str]]",
        id="dict_str_set_not_domain",
    ),
    pytest.param(
        "x: dict[str, list[str]]",
        id="dict_str_list_not_domain",
    ),
    pytest.param(
        "x: dict[str, dict[str, Any]]",
        id="dict_str_dict_not_domain",
    ),
    pytest.param(
        "x: dict[str, frozenset[str]]",
        id="dict_str_frozenset_not_domain",
    ),
    pytest.param(
        "x: dict[str, nodes.AnnAssign]",
        id="dict_str_astroid_node_not_domain",
    ),
]


@pytest.mark.parametrize(("code", "expected_type"), _DETECT_CASES)
def test_detects_generic_key_dict(code: str, expected_type: str) -> None:
    """Checker must flag dict[str, X] where X is a domain type."""
    msgs = _walk_and_release(code, GenericKeyDictChecker)
    assert len(msgs) == 1
    assert msgs[0].msg_id == "generic-key-dict"
    assert expected_type in msgs[0].args[0]


@pytest.mark.parametrize("code", _DO_NOT_DETECT_CASES)
def test_does_not_detect(code: str) -> None:
    """Checker must NOT flag dict[str, X] where X is not a domain type."""
    msgs = _walk_and_release(code, GenericKeyDictChecker)
    assert len(msgs) == 0
