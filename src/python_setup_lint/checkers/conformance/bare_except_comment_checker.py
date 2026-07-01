from __future__ import annotations

import re
from typing import TYPE_CHECKING

from astroid import nodes
from beartype import beartype
from pylint.checkers import BaseChecker

from python_setup_lint.checkers._base import (
    MessageDef,
    _msgs,
    check_if_meaningful,
)

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class BareExceptCommentChecker(BaseChecker):

    name: str = "bare-except-comment"
    msgs = _msgs(
        W9738=MessageDef(
            message="Bare except without justification: 'except%s' must carry a comment explaining why the exception is suppressed",
            symbol="bare-except-comment",
            description="except without re-raise must comment why. Every bare except or except Exception "
            "that doesn't re-raise needs a justifying comment.",
        ),
    )

    @beartype
    def visit_excepthandler(self, node: nodes.ExceptHandler) -> None:
        # Only flag bare except or except Exception
        if not self._is_bare_or_exception(node):
            return

        # Skip if the handler re-raises
        if self._has_bare_raise(node):
            return

        # Check for justifying comment
        if self._has_justifying_comment(node):
            return

        # Emit warning
        except_str = self._get_except_str(node)
        self.add_message(
            "bare-except-comment",
            node=node,
            args=(except_str,),
        )

    @staticmethod
    def _is_bare_or_exception(node: nodes.ExceptHandler) -> bool:  # pylint: disable=W9705  # private helper; return semantics evident from type + name
        """Return True if the handler catches bare except or Exception."""
        if node.type is None:
            return True
        return isinstance(node.type, nodes.Name) and node.type.name == "Exception"

    @staticmethod
    def _has_bare_raise(node: nodes.ExceptHandler) -> bool:  # pylint: disable=W9705,W9728  # private helper; return semantics evident from type + name; semantic helper: wraps any() with a specific predicate for bare-raise detection
        """Return True if the handler body contains a bare raise (re-raise)."""
        return any(child.exc is None for child in node.nodes_of_class(nodes.Raise))

    def _has_justifying_comment(self, node: nodes.ExceptHandler) -> bool:  # pylint: disable=W9705  # private helper; return semantics evident from type + name
        """Check if the except handler has a justifying comment."""
        try:
            stream = node.root().stream()  # type: ignore[union-attr]  # ModuleNode has stream() at runtime
        except AttributeError, OSError:  # pylint: disable=W9740  # best-effort stream access fallback; logging would noise unavoidable attribute/IO degrade
            return False

        if stream is None:
            return False
        try:
            raw = stream.read()
        except OSError:  # pylint: disable=W9740  # best-effort stream read fallback; logging would noise unavoidable IO degrade
            return False
        source = raw.decode("utf-8") if isinstance(raw, bytes) else raw

        lines = source.splitlines(keepends=True)

        lineno = node.fromlineno
        if lineno is None:
            return False

        # Check trailing comment on the except line
        line = lines[lineno - 1] if lineno <= len(lines) else ""
        trailing_match = re.search(r"#\s+(.+)", line)
        if trailing_match:
            comment_text = trailing_match.group(1).strip()
            if check_if_meaningful(
                text=comment_text,
                rule="bare-except-comment",
                code_context=line.strip(),
                comment=comment_text,
            ):
                return True

        # Check preceding line for a comment
        if lineno > 1:
            prev_line = lines[lineno - 2].strip()
            if prev_line.startswith("#"):
                comment_text = prev_line.lstrip("#").strip()
                if check_if_meaningful(
                    text=comment_text,
                    rule="bare-except-comment",
                    code_context=line.strip(),
                    comment=comment_text,
                ):
                    return True

        return False

    @staticmethod
    def _get_except_str(node: nodes.ExceptHandler) -> str:  # pylint: disable=W9705  # private helper; return semantics evident from type + name
        """Get the string representation of the except clause."""
        if node.type is None:
            return ":"
        if isinstance(node.type, nodes.Name):
            return f" {node.type.name}:"
        return ":"


def register(linter: PyLinter) -> None:  # pylint: disable=missing-beartype  # pylint entry point, signature fixed by pylint API; @beartype cannot resolve PyLinter forward ref
    linter.register_checker(BareExceptCommentChecker(linter))
