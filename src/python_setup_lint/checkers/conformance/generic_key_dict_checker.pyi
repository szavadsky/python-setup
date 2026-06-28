"""Pylint checker: prohibit generic-key ``dict[str, X]`` annotations."""

from typing import Any

from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter
from pylint.typing import MessageDefinitionTuple

class GenericKeyDictChecker(BaseChecker):
    name: str = "generic-key-dict"
    msgs: dict[str, MessageDefinitionTuple]
    options: tuple[tuple[str, dict[str, Any]], ...]  # pylint option dict values are Any by API contract

    def __init__(self, linter: PyLinter) -> None: ...
    def open(self) -> None: ...
    def visit_subscript(self, node: nodes.Subscript) -> None: ...
    def _check_dict_str_key(self, node: nodes.Subscript) -> None: ...
    @staticmethod
    def _extract_type_name(node: nodes.NodeNG) -> str | None: ...
    @staticmethod
    def _infer_var_name(node: nodes.Subscript) -> str | None: ...
    def _is_allowed_category(self, var_name: str) -> bool: ...

def register(linter: PyLinter) -> None:
    """Register the checker with the linter."""
