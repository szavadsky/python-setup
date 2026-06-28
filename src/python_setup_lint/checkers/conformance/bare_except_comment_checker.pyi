"""Pylint checker: require bare except handlers to carry a justification comment.

Every ``except:`` or ``except Exception:`` that does not re-raise must carry
a comment explaining why the exception is suppressed.
"""

from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter

class BareExceptCommentChecker(BaseChecker):
    """AST visitor that flags bare except handlers without justification."""

    name: str = "bare-except-comment"

    def visit_excepthandler(self, node: nodes.ExceptHandler) -> None:
        """Check except handlers for bare except without justification."""

def register(linter: PyLinter) -> None:
    """Register the checker with the linter."""
