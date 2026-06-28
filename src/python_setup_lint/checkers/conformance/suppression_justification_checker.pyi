"""Pylint checker: flag unjustified suppression comments."""


from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter
from pylint.typing import MessageDefinitionTuple

class SuppressionJustificationChecker(BaseChecker):
    """AST visitor that flags unjustified suppression comments."""

    name: str = "suppression-justification"
    msgs: dict[str, MessageDefinitionTuple]

    def visit_module(self, node: object) -> None:
        """Walk the module's source lines looking for bare suppressions."""

    def visit_annassign(self, node: nodes.AnnAssign) -> None:
        """Visit annotated assignments and check for unjustified Any annotations."""


    def _check_any_annotation(self, node: nodes.AnnAssign) -> None:
        """Check Any annotations for trailing justification."""

def register(linter: PyLinter) -> None:
    """Register the checker with the linter."""
