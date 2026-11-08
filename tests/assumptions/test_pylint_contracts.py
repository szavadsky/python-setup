"""Pin the pylint behaviors that python_setup_lint checkers and their tests rely on.

Observed with pylint 4.0.6 (pinned in ``pyproject.toml``).  The product never
registers checkers itself; these tests pin the third-party contract that the
checker test harness (``CheckerTestCase``/``UnittestLinter``) and the shipped
plugin entry points assume.
"""

from __future__ import annotations

from pathlib import Path
from typing import get_args

import astroid
import pytest
from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter
from pylint.testutils import CheckerTestCase, MessageTest, UnittestLinter
from pylint.typing import ExtraMessageOptions, MessageDefinitionTuple

pytestmark = pytest.mark.no_external_api

_LIFECYCLE_EVENTS: list[str] = []


class _LifecycleChecker(BaseChecker):
    name = "lifecycle"
    msgs = {"W9801": ("observed %s", "observed-lifecycle", "Lifecycle observation.")}

    def open(self) -> None:
        self._record("open")

    def close(self) -> None:
        self._record("close")

    def visit_module(self, node: nodes.Module) -> None:
        self._record("visit")

    def _record(self, hook: str) -> None:
        entry = f"{hook}:{self.name}"
        _LIFECYCLE_EVENTS.append(entry)


class _ZuluChecker(_LifecycleChecker):
    name = "zulu"
    msgs = {"W9802": ("observed %s", "observed-zulu", "Lifecycle observation.")}


class _AlphaChecker(_LifecycleChecker):
    name = "alpha"
    msgs = {"W9803": ("observed %s", "observed-alpha", "Lifecycle observation.")}


class _CaptureChecker(BaseChecker):
    name = "capture"
    msgs = {"W9804": ("captured %s", "captured-msg", "Capture observation.")}

    def visit_const(self, node: nodes.Const) -> None:
        if isinstance(node.value, int):
            self.add_message("captured-msg", node=node, args=(node.value,))


class _DefinitionChecker(BaseChecker):
    name = "definition-shape"
    msgs = {
        "W9821": ("three fields: %s", "three-field-symbol", "Three-field description."),
        "W9822": (
            "four fields: %s",
            "four-field-symbol",
            "Four-field description.",
            {"scope": "module"},
        ),
    }


class TestPylintContracts:
    """Contracts from pylint that the checker plugins and test harness depend on."""

    def test_pylinter_register_checker_given_two_checkers_then_open_close_wrap_check_in_name_order(self, tmp_path: Path) -> None:
        """OBSERVED at pylint 4.0.6: registration itself calls neither hook.

        ``PyLinter.check()`` calls ``open()`` on each prepared checker in
        checker-name order, walks modules, then calls ``close()`` in reverse
        name order (LIFO).  Registration order does not determine hook order.
        """
        _LIFECYCLE_EVENTS.clear()
        module_path = tmp_path / "sample.py"
        module_path.write_text("VALUE = 1\n")
        linter = PyLinter()
        linter.config.persistent = False  # do not write pylint cache outside the test workspace

        linter.register_checker(_ZuluChecker(linter))
        linter.register_checker(_AlphaChecker(linter))
        assert _LIFECYCLE_EVENTS == []

        linter.check([str(module_path)])

        assert _LIFECYCLE_EVENTS == [
            "open:alpha",
            "open:zulu",
            "visit:alpha",
            "visit:zulu",
            "close:zulu",
            "close:alpha",
        ]

    def test_checker_test_case_given_emitted_message_then_release_messages_returns_message_test_shape(
        self,
    ) -> None:
        """OBSERVED at pylint 4.0.6: ``release_messages`` drains a list of ``MessageTest``."""
        test_case = CheckerTestCase()
        test_case.CHECKER_CLASS = _CaptureChecker
        test_case.setup_method()

        assert isinstance(test_case.linter, UnittestLinter)
        test_case.walk(astroid.parse("VALUE = 42\n"))
        messages = test_case.linter.release_messages()

        assert MessageTest._fields == (
            "msg_id",
            "line",
            "node",
            "args",
            "confidence",
            "col_offset",
            "end_line",
            "end_col_offset",
        )
        assert len(messages) == 1
        message = messages[0]
        assert isinstance(message, MessageTest)
        # msg_id is the message symbol; node.position supplies the location fields.
        assert (
            message.msg_id,
            message.line,
            message.col_offset,
            message.end_line,
            message.end_col_offset,
        ) == ("captured-msg", 1, 8, 1, 10)
        assert message.args == (42,)
        assert isinstance(message.node, nodes.Const)
        assert message.node.value == 42
        assert message.confidence.name == "UNDEFINED"
        assert test_case.linter.release_messages() == []

    def test_message_definition_tuple_given_registered_checker_then_leading_fields_are_msgid_symbol_description(
        self,
    ) -> None:
        """OBSERVED at pylint 4.0.6: the tuple type is a 3-or-4 element union.

        The first three positions are ``msgid``, ``symbol`` and ``description``;
        the optional fourth is ``ExtraMessageOptions``.  Both arities are accepted
        by ``register_checker``.
        """
        union_arms = get_args(MessageDefinitionTuple)

        assert len(union_arms) == 2
        assert [len(get_args(arm)) for arm in union_arms] == [3, 4]
        assert [get_args(arm)[:3] for arm in union_arms] == [
            (str, str, str),
            (str, str, str),
        ]
        assert get_args(union_arms[1])[3] is ExtraMessageOptions

        linter = PyLinter()
        checker = _DefinitionChecker(linter)
        linter.register_checker(checker)

        assert [(message.msgid, message.symbol, message.description) for message in checker.messages] == [
            ("W9821", "three-field-symbol", "Three-field description."),
            ("W9822", "four-field-symbol", "Four-field description."),
        ]
        assert [len(definition) for definition in checker.msgs.values()] == [3, 4]
        assert checker.messages[1].scope == "module"
