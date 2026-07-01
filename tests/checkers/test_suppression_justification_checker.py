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
        """Checker must NOT flag # type: ignore inside string literals."""  # pylint: disable=unjustified-suppression  # docstring contains suppression pattern; test verifies it's not flagged
        code = 'x = "# type: ignore"\n'
        msgs = _walk_and_release(code, SuppressionJustificationChecker)
        assert "unjustified-suppression" not in _msg_ids(msgs)

    def test_data_string_noqa_not_flagged(self) -> None:
        """Checker must NOT flag # noqa inside string literals."""  # pylint: disable=unjustified-suppression  # docstring contains suppression pattern; test verifies it's not flagged
        code = 'x = "# noqa: E501"\n'
        msgs = _walk_and_release(code, SuppressionJustificationChecker)
        assert "unjustified-suppression" not in _msg_ids(msgs)

    def test_data_string_pylint_disable_not_flagged(self) -> None:
        """Checker must NOT flag # pylint: disable= inside string literals."""  # pylint: disable=unjustified-suppression  # docstring contains suppression pattern; test verifies it's not flagged
        code = 'x = "# pylint: disable=missing-beartype"\n'
        msgs = _walk_and_release(code, SuppressionJustificationChecker)
        assert "unjustified-suppression" not in _msg_ids(msgs)

    def test_fstring_not_flagged(self) -> None:
        """Checker must NOT flag # type: ignore inside f-strings."""  # pylint: disable=unjustified-suppression  # docstring contains suppression pattern; test verifies it's not flagged
        code = 'x = f"# type: ignore {val}"\n'
        msgs = _walk_and_release(code, SuppressionJustificationChecker)
        assert "unjustified-suppression" not in _msg_ids(msgs)

    def test_fstring_noqa_not_flagged(self) -> None:
        """Checker must NOT flag # noqa inside f-strings."""  # pylint: disable=unjustified-suppression  # docstring contains suppression pattern; test verifies it's not flagged
        code = 'x = f"# noqa: E501 {val}"\n'
        msgs = _walk_and_release(code, SuppressionJustificationChecker)
        assert "unjustified-suppression" not in _msg_ids(msgs)

    def test_multiline_string_not_flagged(self) -> None:
        """Checker must NOT flag # type: ignore inside triple-quoted strings."""  # pylint: disable=unjustified-suppression  # docstring contains suppression pattern; test verifies it's not flagged
        code = 'x = """\n# type: ignore\n"""\n'
        msgs = _walk_and_release(code, SuppressionJustificationChecker)
        assert "unjustified-suppression" not in _msg_ids(msgs)

    def test_fstring_multiline_not_flagged(self) -> None:
        """Checker must NOT flag # type: ignore inside multiline f-strings."""  # pylint: disable=unjustified-suppression  # docstring contains suppression pattern; test verifies it's not flagged
        code = 'x = f"""\n# type: ignore {val}\n"""\n'
        msgs = _walk_and_release(code, SuppressionJustificationChecker)
        assert "unjustified-suppression" not in _msg_ids(msgs)



class TestFunctionParamReturnAny:
    # Checker must flag Any in function params/returns without per-line
    # justification, but only under source roots (src/).  Test files are
    # excluded by source-root filtering.

    def test_justified_multiline_param_and_return(self) -> None:
        code = """\
def f(
    x: Any,  # external API returns untyped value
    y: dict[str, Any],  # validated dict, keys are known strings
) -> list[Any]:  # JSON parse result, values accessed by known keys
    pass
"""
        msgs = _walk_and_release(
            code, SuppressionJustificationChecker, file_path="src/python_setup_lint/foo.py"
        )
        assert len(msgs) == 0, f"Expected no messages, got {msgs}"

    def test_unjustified_multiline_param_and_return(self) -> None:
        code = """\
def f(
    x: Any,
    y: dict[str, Any],
) -> list[Any]:
    pass
"""
        msgs = _walk_and_release(
            code, SuppressionJustificationChecker, file_path="src/python_setup_lint/foo.py"
        )
        assert len(msgs) == 3, f"Expected 3 messages (x, y, return), got {len(msgs)}"
        assert "unjustified-suppression" in _msg_ids(msgs)

    def test_unjustified_single_line_def(self) -> None:
        code = "def f(x: Any) -> Any:\n    pass\n"
        msgs = _walk_and_release(
            code, SuppressionJustificationChecker, file_path="src/python_setup_lint/foo.py"
        )
        assert len(msgs) == 2, f"Expected 2 messages (param + return), got {len(msgs)}"

    def test_justified_single_line_def(self) -> None:
        code = "def f(x: Any,  # external API contract\n) -> Any:  # plugin return shape\n    pass\n"
        msgs = _walk_and_release(
            code, SuppressionJustificationChecker, file_path="src/python_setup_lint/foo.py"
        )
        assert len(msgs) == 0, f"Expected no messages, got {msgs}"

    def test_tests_path_excluded_by_source_root(self) -> None:
        code = "def f(x: Any) -> Any:\n    pass\n"
        msgs = _walk_and_release(
            code, SuppressionJustificationChecker, file_path="tests/checkers/test_foo.py"
        )
        assert len(msgs) == 0, f"Tests must be excluded by source-root filtering, got {msgs}"

    def test_no_file_path_excluded(self) -> None:
        code = "def f(x: Any) -> Any:\n    pass\n"
        msgs = _walk_and_release(code, SuppressionJustificationChecker)
        assert len(msgs) == 0, f"No file_path means no source-root match, got {msgs}"

    def test_vararg_kwarg_justified(self) -> None:
        code = """\
def f(
    *args: Any,  # positional catch-all from variadic API
    **kwargs: Any,  # keyword catch-all from variadic API
) -> None:
    pass
"""
        msgs = _walk_and_release(
            code, SuppressionJustificationChecker, file_path="src/python_setup_lint/foo.py"
        )
        assert len(msgs) == 0, f"Expected no messages, got {msgs}"

    def test_vararg_kwarg_unjustified(self) -> None:
        code = "def f(*args: Any, **kwargs: Any) -> None:\n    pass\n"
        msgs = _walk_and_release(
            code, SuppressionJustificationChecker, file_path="src/python_setup_lint/foo.py"
        )
        assert len(msgs) == 2, f"Expected 2 messages (*args + **kwargs), got {len(msgs)}"

    def test_posonlyargs_kwonlyargs_justified(self) -> None:
        code = """\
def f(
    a: int,  # a is int
    /,
    b: Any,  # b is any external
    *,
    c: dict[str, Any],  # c dict any
) -> None:
    pass
"""
        msgs = _walk_and_release(
            code, SuppressionJustificationChecker, file_path="src/python_setup_lint/foo.py"
        )
        assert len(msgs) == 0, f"Expected no messages, got {msgs}"

    def test_posonlyargs_kwonlyargs_unjustified(self) -> None:
        code = """\
def f(
    a: int,
    /,
    b: Any,
    *,
    c: dict[str, Any],
) -> None:
    pass
"""
        msgs = _walk_and_release(
            code, SuppressionJustificationChecker, file_path="src/python_setup_lint/foo.py"
        )
        assert len(msgs) == 2, f"Expected 2 messages (b, c), got {len(msgs)}"

    def test_async_def_unjustified(self) -> None:
        code = "async def f(x: Any) -> Any:\n    pass\n"
        msgs = _walk_and_release(
            code, SuppressionJustificationChecker, file_path="src/python_setup_lint/foo.py"
        )
        assert len(msgs) == 2, f"Expected 2 messages (param + return), got {len(msgs)}"

    def test_def_line_justification_does_not_propagate(self) -> None:
        # Per-line justification only: a comment on the def line does NOT
        # justify params on subsequent lines that lack their own comment.
        code = """\
def f(  # all params are Any because pylint API
    x: Any,
    y: Any,
) -> None:
    pass
"""
        msgs = _walk_and_release(
            code, SuppressionJustificationChecker, file_path="src/python_setup_lint/foo.py"
        )
        # The def-line comment is itself a bare comment (not a suppression),
        # so visit_module won't flag it. The two params lack per-line comments.
        any_msgs = [m for m in msgs if "Any" in str(m.args)]
        assert len(any_msgs) == 2, f"Expected 2 Any messages, got {len(any_msgs)}"

    def test_brushoff_reason_rejected_on_param(self) -> None:
        code = "def f(x: Any,  # ignore\n) -> None:\n    pass\n"
        msgs = _walk_and_release(
            code, SuppressionJustificationChecker, file_path="src/python_setup_lint/foo.py"
        )
        assert len(msgs) == 1, f"'ignore' is brush-off; expected 1, got {len(msgs)}"
        assert "unjustified-suppression" in _msg_ids(msgs)

    def test_no_any_annotations_no_messages(self) -> None:
        code = "def f(x: int, y: str) -> bool:\n    pass\n"
        msgs = _walk_and_release(
            code, SuppressionJustificationChecker, file_path="src/python_setup_lint/foo.py"
        )
        assert len(msgs) == 0, f"Expected no messages, got {msgs}"

    def test_nested_method_justified(self) -> None:
        code = """\
class C:
    def method(self, x: Any,  # external plugin type, unknown at static analysis
    ) -> dict[str, Any]:  # plugin return shape, keys are runtime-determined
        pass
"""
        msgs = _walk_and_release(
            code, SuppressionJustificationChecker, file_path="src/python_setup_lint/foo.py"
        )
        assert len(msgs) == 0, f"Expected no messages, got {msgs}"
