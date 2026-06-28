"""Pylint checker: missing return type annotations on _-prefixed functions.

Reports W9741 for module-private functions (``_``-prefixed, not ``__`` dunders)
that lack a return type annotation.  Public functions are covered by the
beartype checker; this fills the gap for private helpers.

W-level only — does not affect build exit codes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes
from pylint.checkers import BaseChecker

from python_setup_lint.checkers._base import (
    MessageDef,
    SourceRootMixin,
    _get_file_path,
    _is_under_source_root,
    _msgs,
)

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class MissingReturnAnnotationChecker(SourceRootMixin, BaseChecker):  # type: ignore[misc]  # SourceRootMixin.options conflicts with BaseChecker.options; both define the same pylint options tuple
    """AST visitor that flags _-prefixed functions missing return annotations."""

    name: str = "missing-return-annotation"

    msgs = _msgs(
        W9741=MessageDef(
            message="_-prefixed function %s() is missing a return type annotation",
            symbol="missing-return-annotation",
            description="Module-private functions must declare return types (CodingRules: precise types; beartype precision).",
        ),
    )

    def _check_function(self, node: nodes.FunctionDef | nodes.AsyncFunctionDef) -> None:
        # Skip modules outside source roots
        file_path = _get_file_path(node)
        if file_path is None or not _is_under_source_root(
            file_path, self._source_roots
        ):
            return

        # Skip public functions (no _ prefix) — beartype checker covers those
        if not node.name.startswith("_"):
            return

        # Skip dunder methods (__init__, __post_init__, __str__, etc.)
        if node.name.startswith("__"):
            return

        # Skip if already has a return annotation
        if node.returns is not None:
            return

        self.add_message("missing-return-annotation", node=node, args=(node.name,))


def register(  # pylint: disable=missing-beartype  # circular import — PyLinter not available at runtime
    linter: PyLinter,
) -> None:
    linter.register_checker(MissingReturnAnnotationChecker(linter))
