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

    @staticmethod
    def _get_string_literal_spans(node: object) -> dict[int, list[tuple[int, int]]]:
        """Return dict mapping 1-indexed line numbers to string literal column spans."""

    @staticmethod
    def _suppression_in_string(line: str, spans: list[tuple[int, int]]) -> bool:
        """Return True if the suppression # on line is inside a string literal."""

    def _check_any_annotation(self, node: nodes.AnnAssign) -> None:
        """Check Any annotations for trailing justification."""

def register(linter: PyLinter) -> None:
    """Register the checker with the linter."""
