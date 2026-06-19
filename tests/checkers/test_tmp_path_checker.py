"""Unit tests for python_setup_lint.checkers.tmp_path_checker.

Uses synthetic code strings parsed via astroid, with module.file patched to
simulate test-file paths.
"""

from __future__ import annotations

from python_setup_lint.checkers.tmp_path_checker import TempFileChecker
from python_setup_lint.testing import _make_tc as _make_tc_factory, _walk_and_release as _walk_shared


_make_tc = lambda: _make_tc_factory(TempFileChecker)


def _walk_and_release(code: str, *, file_path: str = "tests/test_mod.py") -> list:
    tc = _make_tc()
    tc.checker.open()
    module = __import__("astroid").parse(code)
    module.file = file_path
    tc.walk(module)
    return tc.linter.release_messages()


def _msg_ids(msgs: list) -> set[str]:
    return {m.msg_id for m in msgs}


class TestDetectsTempfileInTests:
    """Checker must emit W9702 for tempfile calls in test files."""

    def test_mkdtemp_in_test(self):
        msgs = _walk_and_release("import tempfile\n\nd = tempfile.mkdtemp()")
        assert len(msgs) == 1
        assert msgs[0].msg_id == "tempfile-mkdtemp-in-test"
        assert msgs[0].args == ("tempfile.mkdtemp",)

    def test_mkstemp_in_test(self):
        msgs = _walk_and_release("import tempfile\n\nfd, p = tempfile.mkstemp()")
        assert len(msgs) == 1
        assert msgs[0].msg_id == "tempfile-mkdtemp-in-test"

    def test_named_temporary_file_in_test(self):
        msgs = _walk_and_release("import tempfile\n\nf = tempfile.NamedTemporaryFile()")
        assert len(msgs) == 1
        assert msgs[0].msg_id == "tempfile-mkdtemp-in-test"

    def test_named_temporary_file_as_context_manager(self):
        """NamedTemporaryFile used as context manager is OK."""
        msgs = _walk_and_release(
            "import tempfile\n\nwith tempfile.NamedTemporaryFile() as f: pass"
        )
        assert len(msgs) == 0

    def test_multiple_calls(self):
        msgs = _walk_and_release(
            "import tempfile\n\na = tempfile.mkdtemp()\nb = tempfile.mkdtemp()"
        )
        assert len(msgs) == 2

    def test_mkdtemp_with_args(self):
        msgs = _walk_and_release(
            'import tempfile\n\nd = tempfile.mkdtemp(prefix="t15-test-")'
        )
        assert len(msgs) == 1
        assert msgs[0].args == ("tempfile.mkdtemp",)


class TestSkipsNonTestFiles:
    """Checker must NOT flag tempfile calls in non-test files."""

    def test_production_file(self):
        msgs = _walk_and_release(
            "import tempfile\n\nd = tempfile.mkdtemp()",
            file_path="src/prod.py",
        )
        assert len(msgs) == 0

    def test_other_source_file(self):
        msgs = _walk_and_release(
            "import tempfile\n\nd = tempfile.mkdtemp()",
            file_path="consultant_mcp/config/tokens.py",
        )
        assert len(msgs) == 0


class TestSkipsNonTempfileCalls:
    """Checker must NOT flag non-tempfile calls."""

    def test_regular_function(self):
        msgs = _walk_and_release("x = os.path.join('a', 'b')")
        assert len(msgs) == 0

    def test_other_tempfile_function(self):
        """tempfile.gettempdir() is not a leakage function."""
        msgs = _walk_and_release("import tempfile\n\nd = tempfile.gettempdir()")
        assert len(msgs) == 0

    def test_empty_module(self):
        msgs = _walk_and_release("")
        assert len(msgs) == 0

    def test_import_only(self):
        msgs = _walk_and_release("import tempfile")
        assert len(msgs) == 0


class TestSkipsContextManagerNamedTemp:
    """NamedTemporaryFile used as context manager is OK."""

    def test_with_statement(self):
        msgs = _walk_and_release(
            "import tempfile\n\nwith tempfile.NamedTemporaryFile() as f:\n    f.write(b'x')"
        )
        assert len(msgs) == 0

    def test_mkdtemp_not_context_manager(self):
        """mkdtemp is never a context manager — always flagged."""
        msgs = _walk_and_release(
            "import tempfile\n\nwith tempfile.mkdtemp() as d: pass"
        )
        assert len(msgs) == 1
