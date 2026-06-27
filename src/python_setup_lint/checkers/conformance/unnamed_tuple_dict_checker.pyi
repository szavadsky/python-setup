"""Pylint checker: prohibit unnamed-tuple dict values."""

from __future__ import annotations

from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter

from python_setup_lint.checkers._base import LintRuleId, MessageDef

class UnnamedTupleDictChecker(BaseChecker):
    name: str = "unnamed-tuple-dict"
    msgs: dict[LintRuleId, MessageDef]

    def visit_annassign(self, node: nodes.AnnAssign) -> None: ...
    def visit_assign(self, node: nodes.Assign) -> None: ...
    def _is_str_key_dict_annotation(self, ann: nodes.NodeNG | None) -> bool: ...
    def _check_dict(self, dict_node: nodes.Dict) -> None: ...
    @staticmethod
    def _is_unnamed_tuple(node: nodes.NodeNG) -> bool: ...
    @staticmethod
    def _get_tuple_elts(node: nodes.Tuple) -> list: ...

def register(linter: PyLinter) -> None: ...
