"""Pylint checker: prohibit unnamed-tuple dict values."""

from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter
from pylint.typing import ExtraMessageOptions

from python_setup_lint.checkers._base import LintRuleId, MessageDef

class UnnamedTupleDictChecker(BaseChecker):
    name: str = "unnamed-tuple-dict"
    msgs: dict[str, tuple[str, str, str] | tuple[str, str, str, ExtraMessageOptions]]

    def visit_annassign(self, node: nodes.AnnAssign) -> None:
        """Check annotated assignments for unnamed-tuple dict values.

        Flags ``dict`` literals whose values are bare ``tuple``/``Tuple[...]``
        literals with >1 unnamed positional fields, suggesting they should use
        a ``NamedTuple`` or dataclass instead.
        """
    def visit_assign(self, node: nodes.Assign) -> None:
        """Check assignments with type comments for unnamed-tuple dict values.

        Flags ``dict`` literals whose values are bare ``tuple``/``Tuple[...]``
        literals with >1 unnamed positional fields, suggesting they should use
        a ``NamedTuple`` or dataclass instead.
        """
    def _is_str_key_dict_annotation(self, ann: nodes.NodeNG | None) -> bool: ...
    def _check_dict(self, dict_node: nodes.Dict) -> None: ...
    @staticmethod
    def _is_unnamed_tuple(node: nodes.NodeNG) -> bool: ...
    @staticmethod
    def _get_tuple_elts(node: nodes.Tuple) -> list[nodes.NodeNG]: ...

def register(linter: PyLinter) -> None: ...
