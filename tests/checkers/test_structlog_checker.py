"""Unit tests for python_setup_lint.checkers.structlog_checker.

Tests W9710 (use-structlog) and W9711 (use-structured-logging) detection.
"""

from __future__ import annotations

from typing import Any

import astroid
import pytest

from python_setup_lint.checkers.conformance.structlog_checker import StructlogChecker
from python_setup_lint.testing import _make_tc as _make_tc_factory

pytestmark = pytest.mark.no_external_api


def _make_tc() -> Any:  # pylint: disable=W9728  # test helper: type-specific alias for _make_tc_factory, avoids repeated imports
    return _make_tc_factory(StructlogChecker)


def _walk_and_release(
    code: str,
    *,
    file_path: str = "src/test_mod.py",
    source_roots: list[str] | None = None,
) -> list[Any]:
    tc = _make_tc()
    tc.linter.config.source_roots = source_roots or ["src"]
    tc.checker.open()
    module = astroid.parse(code)
    module.file = file_path
    tc.walk(module)
    return tc.linter.release_messages()  # type: ignore[no-any-return]  # test fixture builds typed list from Any checker introspection


def _msg_count(msgs: list[Any], msg_id: str) -> int:  # pylint: disable=W9728  # test helper: counts messages by msg_id
    return sum(1 for m in msgs if m.msg_id == msg_id)


# ── W9710: logging.getLogger detection ──────────────────────────────


class TestUseStructlog:
    """Tests for W9710 — ``use-structlog``."""

    def test_use_structlog_given_logging_getlogger_in_source_root_then_flagged(self) -> None:
        """``logging.getLogger(...)`` in source root is flagged."""
        msgs = _walk_and_release(
            "import logging\nlogger = logging.getLogger(__name__)\n"
        )
        assert _msg_count(msgs, "use-structlog") == 1

    def test_use_structlog_given_logging_getlogger_with_name_then_flagged(self) -> None:
        """``logging.getLogger("name")`` is flagged."""
        msgs = _walk_and_release(
            'import logging\nlogger = logging.getLogger("my_logger")\n'
        )
        assert _msg_count(msgs, "use-structlog") == 1

    def test_use_structlog_given_structlog_get_logger_then_not_flagged(self) -> None:
        """``structlog.get_logger`` is NOT flagged."""
        msgs = _walk_and_release(
            "import structlog\nlogger = structlog.get_logger(__name__)\n"
        )
        assert _msg_count(msgs, "use-structlog") == 0

    def test_use_structlog_given_logging_getlogger_outside_source_root_then_not_flagged(self) -> None:
        """``logging.getLogger`` outside source roots is NOT flagged."""
        msgs = _walk_and_release(
            "import logging\nlogger = logging.getLogger(__name__)\n",
            file_path="tests/test_mod.py",
            source_roots=["src"],
        )
        assert _msg_count(msgs, "use-structlog") == 0

    def test_use_structlog_given_other_module_getlogger_then_not_flagged(self) -> None:
        """``other.getLogger`` is NOT flagged."""
        msgs = _walk_and_release(
            "import other\nlogger = other.getLogger(__name__)\n"
        )
        assert _msg_count(msgs, "use-structlog") == 0


# ── W9711: printf-style / f-string detection ────────────────────────


class TestUseStructuredLogging:
    """Tests for W9711 — ``use-structured-logging``."""

    def test_use_structured_logging_given_printf_style_format_then_flagged(self) -> None:
        """``log.info("fmt %s", arg)`` is flagged."""
        msgs = _walk_and_release(
            'import structlog\nlog = structlog.get_logger(__name__)\n'
            'log.info("hello %s", "world")\n'
        )
        assert _msg_count(msgs, "use-structured-logging") == 1

    def test_use_structured_logging_given_fstring_then_flagged(self) -> None:
        """``log.info(f"msg {var}")`` is flagged."""
        msgs = _walk_and_release(
            'import structlog\nlog = structlog.get_logger(__name__)\n'
            'name = "world"\n'
            'log.info(f"hello {name}")\n'
        )
        assert _msg_count(msgs, "use-structured-logging") == 1

    def test_use_structured_logging_given_kwargs_only_then_not_flagged(self) -> None:
        """``log.info("msg", key=val)`` is NOT flagged."""
        msgs = _walk_and_release(
            'import structlog\nlog = structlog.get_logger(__name__)\n'
            'log.info("hello", name="world")\n'
        )
        assert _msg_count(msgs, "use-structured-logging") == 0

    def test_use_structured_logging_given_single_string_arg_then_not_flagged(self) -> None:
        """``log.info("plain message")`` is NOT flagged."""
        msgs = _walk_and_release(
            'import structlog\nlog = structlog.get_logger(__name__)\n'
            'log.info("hello world")\n'
        )
        assert _msg_count(msgs, "use-structured-logging") == 0

    def test_use_structured_logging_given_all_log_levels_then_flagged(self) -> None:
        """All log levels are checked for printf-style."""
        code = (
            'import structlog\nlog = structlog.get_logger(__name__)\n'
            'log.debug("fmt %s", "a")\n'
            'log.info("fmt %s", "b")\n'
            'log.warning("fmt %s", "c")\n'
            'log.error("fmt %s", "d")\n'
            'log.critical("fmt %s", "e")\n'
        )
        msgs = _walk_and_release(code)
        assert _msg_count(msgs, "use-structured-logging") == 5

    def test_use_structured_logging_given_outside_source_root_then_not_flagged(self) -> None:
        """Logger calls outside source roots are NOT flagged."""
        msgs = _walk_and_release(
            'import structlog\nlog = structlog.get_logger(__name__)\n'
            'log.info("fmt %s", "world")\n',
            file_path="tests/test_mod.py",
            source_roots=["src"],
        )
        assert _msg_count(msgs, "use-structured-logging") == 0

    def test_use_structured_logging_given_printf_on_logger_then_flagged(self) -> None:
        """``log.info("fmt %s", "arg")`` is flagged (conservative lint)."""
        msgs = _walk_and_release(
            'import structlog\nlog = structlog.get_logger(__name__)\n'
            'log.info("fmt %s", "arg")\n'
        )
        assert _msg_count(msgs, "use-structured-logging") == 1
    def test_use_structured_logging_given_non_logger_object_then_not_flagged(self) -> None:
        """``obj.info("fmt %s", "arg")`` is NOT flagged (not a logger)."""
        msgs = _walk_and_release(
            'obj = SomeClass()\nobj.info("fmt %s", "arg")\n'
        )
        assert _msg_count(msgs, "use-structured-logging") == 0

    def test_use_structured_logging_given_percent_literal_then_not_flagged(self) -> None:
        """``log.info("100% done")`` with literal %% is NOT flagged."""
        msgs = _walk_and_release(
            'import structlog\nlog = structlog.get_logger(__name__)\n'
            'log.info("100% done")\n'
        )
        assert _msg_count(msgs, "use-structured-logging") == 0
