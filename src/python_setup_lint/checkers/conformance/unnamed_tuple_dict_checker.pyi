"""Pylint checker: flag unnamed-tuple dict values."""

from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter
from pylint.typing import MessageDefinitionTuple

class UnnamedTupleDictChecker(BaseChecker):
    name: str = "unnamed-tuple-dict"
    msgs: dict[str, MessageDefinitionTuple]

    def visit_annassign(self, node: nodes.AnnAssign) -> None:
        """Check annotated assignments for unnamed-tuple dict values."""

def register(linter: PyLinter) -> None:
    """Register the checker with the linter."""
