"""Unit tests for python_setup_lint.checkers.conformance.suppression_justification_checker.

Tests that the checker correctly flags unjustified suppression comments
and passes justified ones.
"""

from __future__ import annotations

from typing import Any

from python_setup_lint.checkers.conformance.suppression_justification_checker import (
    SuppressionJustificationChecker,
)
from python_setup_lint.testing import _walk_and_release


def _msg_ids(msgs: list[Any]) -> set[str]:
    return {m.msg_id for m in msgs}


class TestJustifiedSuppressions:
    """Checker must NOT flag suppressions with a technical reason."""

    def test_justified_noqa_with_trailing_reason(self) -> None:
        code = """\
x = 1  # noqa: E501  # trailing comment with reason
"""
        msgs = _walk_and_release(code, SuppressionJustificationChecker)
        assert len(msgs) == 0, f"Expected no messages, got {msgs}"

    def test_justified_pylint_disable_with_reason(self) -> None:
        code = """\
def foo():  # pylint: disable=missing-beartype  # circular import — PyLinter not available at runtime
    pass
"""
        msgs = _walk_and_release(code, SuppressionJustificationChecker)
        assert len(msgs) == 0, f"Expected no messages, got {msgs}"

    def test_justified_type_ignore_with_reason(self) -> None:
        code = """\
x: int = 1  # type: ignore  # mypy 1.4 does not understand this pattern
"""
        msgs = _walk_and_release(code, SuppressionJustificationChecker)
        assert len(msgs) == 0, f"Expected no messages, got {msgs}"

    def test_justified_ty_ignore_with_reason(self) -> None:
        code = "x = 1  # ty:ignore[invalid-argument-type]  # ty cannot infer literal-int narrowing here\n"
        msgs = _walk_and_release(code, SuppressionJustificationChecker)
        assert len(msgs) == 0

    def test_justified_preceding_comment(self) -> None:
        code = """\
# StubChecker is TYPE_CHECKING-only; beartype can't resolve at runtime
# pylint: disable=missing-beartype
def foo() -> None:
    pass
"""
        msgs = _walk_and_release(code, SuppressionJustificationChecker)
        assert len(msgs) == 0, f"Expected no messages, got {msgs}"


class TestUnjustifiedSuppressions:
    """Checker MUST flag suppressions without a technical reason."""

    def test_bare_noqa(self) -> None:
        code = """\
x = 1  # noqa: E501
"""
        msgs = _walk_and_release(code, SuppressionJustificationChecker)
        assert len(msgs) == 1, f"Expected 1 message, got {len(msgs)}"
        assert "unjustified-suppression" in _msg_ids(msgs)

    def test_bare_pylint_disable(self) -> None:
        code = """\
def foo():  # pylint: disable=missing-beartype
    pass
"""
        msgs = _walk_and_release(code, SuppressionJustificationChecker)
        assert len(msgs) == 1, f"Expected 1 message, got {len(msgs)}"
        assert "unjustified-suppression" in _msg_ids(msgs)

    def test_bare_type_ignore(self) -> None:
        code = """\
x: int = 1  # type: ignore
"""
        msgs = _walk_and_release(code, SuppressionJustificationChecker)
        assert len(msgs) == 1, f"Expected 1 message, got {len(msgs)}"
        assert "unjustified-suppression" in _msg_ids(msgs)

    def test_boilerplate_reason_not_meaningful(self) -> None:
        code = """\
x = 1  # noqa: E501  # ignore
"""
        msgs = _walk_and_release(code, SuppressionJustificationChecker)
        assert len(msgs) == 1, f"Expected 1 message, got {len(msgs)}"
        assert "unjustified-suppression" in _msg_ids(msgs)

    def test_bare_ty_ignore(self) -> None:
        code = "x = 1  # ty:ignore[invalid-argument-type]\n"
        msgs = _walk_and_release(code, SuppressionJustificationChecker)
        assert len(msgs) == 1
        assert "unjustified-suppression" in _msg_ids(msgs)

    def test_ty_ignore_brushoff_reason_not_meaningful(self) -> None:
        # The exact brush-off planted in the integration sample — "# ty" is <5 chars
        code = '_ = int("1")  # ty:ignore[invalid-argument-type]  # ty\n'
        msgs = _walk_and_release(code, SuppressionJustificationChecker)
        assert len(msgs) == 1
        assert "unjustified-suppression" in _msg_ids(msgs)

    def test_too_short_reason_not_meaningful(self) -> None:
        code = """\
x = 1  # noqa: E501  # ok
"""
        msgs = _walk_and_release(code, SuppressionJustificationChecker)
        assert len(msgs) == 1, f"Expected 1 message, got {len(msgs)}"
        assert "unjustified-suppression" in _msg_ids(msgs)

class TestDataStrings:
    """Checker must NOT flag suppression patterns inside string literals."""

    def test_data_string_not_flagged(self) -> None:
        """Checker must NOT flag # type: ignore inside string literals."""
        code = 'x = "# type: ignore"\n'
        msgs = _walk_and_release(code, SuppressionJustificationChecker)
        assert "unjustified-suppression" not in _msg_ids(msgs)

    def test_data_string_noqa_not_flagged(self) -> None:
        """Checker must NOT flag # noqa inside string literals."""
        code = 'x = "# noqa: E501"\n'
        msgs = _walk_and_release(code, SuppressionJustificationChecker)
        assert "unjustified-suppression" not in _msg_ids(msgs)

    def test_data_string_pylint_disable_not_flagged(self) -> None:
        """Checker must NOT flag # pylint: disable= inside string literals."""
        code = 'x = "# pylint: disable=missing-beartype"\n'
        msgs = _walk_and_release(code, SuppressionJustificationChecker)
        assert "unjustified-suppression" not in _msg_ids(msgs)
