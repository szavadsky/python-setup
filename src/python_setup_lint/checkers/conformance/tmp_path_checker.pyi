"""Pylint checker: ban tempfile.mkdtemp/mkstemp/NamedTemporaryFile in tests.

Test files should use pytest's built-in ``tmp_path`` fixture instead of
manual ``tempfile`` calls that leak directories.
"""


from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter

class TempFileChecker(BaseChecker):
    """AST visitor that flags tempfile leakage in test files."""

    name: str = "tempfile-mkdtemp-in-test"

    def __init__(self, linter: PyLinter) -> None: ...
    def open(self) -> None: ...
    def visit_call(self, node: nodes.Call) -> None: ...


def register(linter: PyLinter) -> None: ...
