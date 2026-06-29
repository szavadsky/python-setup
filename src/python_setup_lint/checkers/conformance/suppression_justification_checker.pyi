"""Pylint checker: flag unjustified suppression comments."""


from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter
from pylint.typing import MessageDefinitionTuple

from python_setup_lint.checkers._base import SourceRootMixin

class SuppressionJustificationChecker(SourceRootMixin, BaseChecker):  # type: ignore[misc]  # SourceRootMixin.options conflicts with BaseChecker.options; both define the same pylint options tuple
    """AST visitor that flags unjustified suppression comments."""

    name: str = "suppression-justification"
    msgs: dict[str, MessageDefinitionTuple]

    def __init__(self, linter: PyLinter) -> None: ...
    def open(self) -> None: ...
    def visit_module(self, node: object) -> None:
        """Walk the module's source lines looking for bare suppressions."""

    def visit_annassign(self, node: nodes.AnnAssign) -> None:
        """Visit annotated assignments and check for unjustified Any annotations."""

    def visit_functiondef(self, node: nodes.FunctionDef) -> None: ...
    def visit_asyncfunctiondef(self, node: nodes.AsyncFunctionDef) -> None: ...

    def _check_function(self, node: nodes.FunctionDef | nodes.AsyncFunctionDef) -> None: ...

    @staticmethod
    def _annotation_contains_any(annotation: nodes.NodeNG) -> bool: ...

    def _emit_if_unjustified(self, annotation: nodes.NodeNG, lineno: int) -> None: ...

    @staticmethod
    def _get_string_literal_spans(node: object) -> dict[int, list[tuple[int, int]]]:
        """Return dict mapping 1-indexed line numbers to string literal column spans."""

    @staticmethod
    def _suppression_in_string(line: str, spans: list[tuple[int, int]]) -> bool:
        """Return True if the suppression # on line is inside a string literal."""

    def _check_any_annotation(self, node: nodes.AnnAssign) -> None:
        """Check Any annotations for trailing justification."""

    @staticmethod
    def _subscript_contains_any(node: nodes.Subscript) -> bool: ...

    @staticmethod
    def _is_suppression_line(line: str) -> bool: ...

    @staticmethod
    def _has_justification(lines: list[str], idx: int) -> bool: ...

def register(linter: PyLinter) -> None:
    """Register the checker with the linter."""
