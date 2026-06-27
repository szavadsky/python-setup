"""Unit tests for python_setup_lint.checkers.tmp_path_checker.

Uses synthetic code strings parsed via astroid, with module.file patched to
simulate test-file paths.
"""

from __future__ import annotations

from typing import Any

from python_setup_lint.checkers.conformance.tmp_path_checker import TempFileChecker
from python_setup_lint.testing import _make_tc as _make_tc_factory


def _make_tc() -> Any:
    return _make_tc_factory(TempFileChecker)


def _walk_and_release(code: str, *, file_path: str = "tests/test_mod.py") -> list[Any]:
    tc = _make_tc()
    tc.checker.open()
    module = __import__("astroid").parse(code)
    module.file = file_path
    tc.walk(module)
    return tc.linter.release_messages()


def _msg_ids(msgs: list[Any]) -> set[str]:
    return {m.msg_id for m in msgs}


class TestDetectsTempfileInTests:
    """Checker must emit W9702 for tempfile calls in test files."""

    def test_mkdtemp_in_test(self) -> None:
        msgs = _walk_and_release("import tempfile\n\nd = tempfile.mkdtemp()")
        assert len(msgs) == 1
        assert msgs[0].msg_id == "tempfile-mkdtemp-in-test"
        assert msgs[0].args == ("tempfile.mkdtemp",)

    def test_mkstemp_in_test(self) -> None:
        msgs = _walk_and_release("import tempfile\n\nfd, p = tempfile.mkstemp()")
        assert len(msgs) == 1
        assert msgs[0].msg_id == "tempfile-mkdtemp-in-test"

    def test_named_temporary_file_in_test(self) -> None:
        msgs = _walk_and_release("import tempfile\n\nf = tempfile.NamedTemporaryFile()")
        assert len(msgs) == 1
        assert msgs[0].msg_id == "tempfile-mkdtemp-in-test"

    def test_named_temporary_file_as_context_manager(self) -> None:
        """NamedTemporaryFile used as context manager is OK."""
        msgs = _walk_and_release(
            "import tempfile\n\nwith tempfile.NamedTemporaryFile() as f: pass"
        )
        assert len(msgs) == 0

    def test_multiple_calls(self) -> None:
        msgs = _walk_and_release(
            "import tempfile\n\na = tempfile.mkdtemp()\nb = tempfile.mkdtemp()"
        )
        assert len(msgs) == 2

    def test_mkdtemp_with_args(self) -> None:
        msgs = _walk_and_release(
            'import tempfile\n\nd = tempfile.mkdtemp(prefix="t15-test-")'
        )
        assert len(msgs) == 1
        assert msgs[0].args == ("tempfile.mkdtemp",)


class TestSkipsNonTestFiles:
    """Checker must NOT flag tempfile calls in non-test files."""

    def test_production_file(self) -> None:
        msgs = _walk_and_release(
            "import tempfile\n\nd = tempfile.mkdtemp()",
            file_path="src/prod.py",
        )
        assert len(msgs) == 0

    def test_other_source_file(self) -> None:
        msgs = _walk_and_release(
            "import tempfile\n\nd = tempfile.mkdtemp()",
            file_path="consultant_mcp/config/tokens.py",
        )
        assert len(msgs) == 0


class TestSkipsNonTempfileCalls:
    """Checker must NOT flag non-tempfile calls."""

    def test_regular_function(self) -> None:
        msgs = _walk_and_release("x = os.path.join('a', 'b')")
        assert len(msgs) == 0

    def test_other_tempfile_function(self) -> None:
        """tempfile.gettempdir() is not a leakage function."""
        msgs = _walk_and_release("import tempfile\n\nd = tempfile.gettempdir()")
        assert len(msgs) == 0

    def test_empty_module(self) -> None:
        msgs = _walk_and_release("")
        assert len(msgs) == 0

    def test_import_only(self) -> None:
        msgs = _walk_and_release("import tempfile")
        assert len(msgs) == 0


class TestSkipsContextManagerNamedTemp:
    """NamedTemporaryFile used as context manager is OK."""

    def test_with_statement(self) -> None:
        msgs = _walk_and_release(
            "import tempfile\n\nwith tempfile.NamedTemporaryFile() as f:\n    f.write(b'x')"
        )
        assert len(msgs) == 0

    def test_mkdtemp_not_context_manager(self) -> None:
        """mkdtemp is never a context manager — always flagged."""
        msgs = _walk_and_release(
            "import tempfile\n\nwith tempfile.mkdtemp() as d: pass"
        )
        assert len(msgs) == 1


class TestFilePatterns:
    """Checker must match various test-file patterns."""

    def test_conftest_py(self) -> None:
        msgs = _walk_and_release(
            "import tempfile\n\nd = tempfile.mkdtemp()",
            file_path="tests/conftest.py",
        )
        assert len(msgs) == 1

    def test_asterisk_test_py(self) -> None:
        msgs = _walk_and_release(
            "import tempfile\n\nd = tempfile.mkdtemp()",
            file_path="src/foo_test.py",
        )
        assert len(msgs) == 1

    def test_test_asterisk_py(self) -> None:
        msgs = _walk_and_release(
            "import tempfile\n\nd = tempfile.mkdtemp()",
            file_path="test_foo_bar.py",
        )
        assert len(msgs) == 1

    def test_tests_subdir(self) -> None:
        msgs = _walk_and_release(
            "import tempfile\n\nd = tempfile.mkdtemp()",
            file_path="tests/unit/subdir/test_mod.py",
        )
        assert len(msgs) == 1


class TestImportVariants:
    """Checker must handle various import styles (or document limitations)."""

    def test_from_import_mkdtemp(self) -> None:
        """from tempfile import mkdtemp — checker currently does NOT catch this form."""
        msgs = _walk_and_release("from tempfile import mkdtemp\n\nd = mkdtemp()")
        # Known gap: the checker only catches tempfile.attr() calls.
        # A follow-up could extend _is_tempfile_call to handle Name nodes from
        # from-imports.
        assert len(msgs) == 0

    def test_import_as_alias(self) -> None:
        """import tempfile as tf — checker currently does NOT catch this form."""
        msgs = _walk_and_release("import tempfile as tf\n\nd = tf.mkdtemp()")
        # Known gap: the checker only checks for `tempfile` as the module name.
        # A follow-up could resolve aliases.
        assert len(msgs) == 0


class TestEdgeCases:
    """Edge cases for internal checker logic."""

    def test_no_file_path_returns_false(self) -> None:
        """_is_test_file returns False when node.root().file is None."""
        tc = _make_tc()
        tc.checker.open()
        module = __import__("astroid").parse(
            "import tempfile\n\nd = tempfile.mkdtemp()"
        )
        module.file = None
        tc.walk(module)
        msgs = tc.linter.release_messages()
        assert len(msgs) == 0

    def test_non_attribute_call_not_flagged(self) -> None:
        """A bare mkdtemp() call (not tempfile.mkdtemp) is not flagged."""
        msgs = _walk_and_release("mkdtemp()")
        assert len(msgs) == 0

    def test_wrong_module_not_flagged(self) -> None:
        """os.mkdtemp() is not flagged (wrong module)."""
        msgs = _walk_and_release("import os\n\nos.mkdtemp()")
        assert len(msgs) == 0

    def test_wrong_attribute_not_flagged(self) -> None:
        """tempfile.something_else() is not flagged."""
        msgs = _walk_and_release("import tempfile\n\ntempfile.something_else()")
        assert len(msgs) == 0

    def test_named_temporary_in_with_multi_expr(self) -> None:
        """NamedTemporaryFile in a with-statement with multiple expressions is exempt."""
        msgs = _walk_and_release(
            "import tempfile\n\nwith tempfile.NamedTemporaryFile() as f, open('x') as g:\n    pass"
        )
        assert len(msgs) == 0

    def test_non_test_path_not_matched(self) -> None:
        """A path that doesn't match any test pattern is not flagged."""
        msgs = _walk_and_release(
            "import tempfile\n\nd = tempfile.mkdtemp()",
            file_path="src/util/helper.py",
        )
        assert len(msgs) == 0

    def test_matches_path_with_backslash_pattern(self) -> None:
        """_matches_path handles backslash-containing patterns (Windows compat)."""
        from python_setup_lint.checkers._base import _matches_path

        assert _matches_path("tests\\foo\\test_mod.py", ["tests\\"])
        assert not _matches_path("src\\prod.py", ["tests\\"])
