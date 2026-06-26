"""Pylint checker: prohibit unnamed-tuple dict values.

Flags ``dict`` literals whose values are bare ``tuple``/``Tuple[...]``
literals with >1 unnamed positional fields, suggesting they should use
a ``NamedTuple`` or dataclass instead.

Checker logic
-------------
- Walks AST for ``AnnAssign`` and ``Assign`` (with type comment) nodes.
- Checks if the annotation is ``dict[str, ...]`` or ``ClassVar[dict[str, ...]]``.
- For matching dict literals, flags any value that is a bare ``tuple``
  literal with >= 2 simple literal elements.
"""

from typing import TYPE_CHECKING

from astroid import nodes
from pylint.checkers import BaseChecker

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class UnnamedTupleDictChecker(BaseChecker):
    """AST visitor that flags dict values that should be NamedTuples."""

    name: str = "unnamed-tuple-dict"

    def __init__(self, linter: PyLinter) -> None: ...
    def visit_annassign(self, node: nodes.AnnAssign) -> None: ...
    def visit_assign(self, node: nodes.Assign) -> None: ...


def register(linter: PyLinter) -> None: ...
