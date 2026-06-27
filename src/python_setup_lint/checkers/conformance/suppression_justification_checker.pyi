"""Pylint checker: require suppression comments to carry technical justification.

Flags any ``# pylint: disable=...``, ``# noqa: <code>``, ``# type: ignore``
whose line lacks a meaningful technical reason.  The reason may appear as a
trailing comment on the same line, or as a comment on the preceding line.
"""

from typing import TYPE_CHECKING

from pylint.checkers import BaseChecker

if TYPE_CHECKING:
    from pylint.lint import PyLinter

from python_setup_lint.checkers._base import LintRuleId, MessageDef

class SuppressionJustificationChecker(BaseChecker):
    """AST visitor that flags unjustified suppression comments."""

    name: str = "suppression-justification"
    msgs: dict[LintRuleId, MessageDef]

    def visit_module(self, node: object) -> None: ...

def register(linter: PyLinter) -> None: ...
