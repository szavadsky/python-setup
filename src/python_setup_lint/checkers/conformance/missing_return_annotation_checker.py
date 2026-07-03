from __future__ import annotations

from typing import TYPE_CHECKING

from astroid import nodes
from pylint.checkers import BaseChecker

from python_setup_lint.checkers._base import (
    FunctionVisitMixin,
    MessageDef,
    _msgs,
)

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class MissingReturnAnnotationChecker(FunctionVisitMixin, BaseChecker):  # type: ignore[misc]  # SourceRootMixin.options conflicts with BaseChecker.options; both define the same pylint options tuple

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
        if self._skip_if_outside_source_roots(node):
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
