from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
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

log = structlog.get_logger(__name__)


class BeartypeCoverageChecker(SourceRootMixin, BaseChecker):  # type: ignore[misc]  # SourceRootMixin.options conflicts with BaseChecker.options; both define the same pylint options tuple

    name: str = "beartype-coverage"
    msgs = _msgs(
        W9701=MessageDef(
            message="Public function '%s' in '%s' is missing @beartype decorator",
            symbol="missing-beartype",
            description="All public functions should have @beartype for runtime type enforcement.",
        ),
    )

    def _check_function(self, node: nodes.FunctionDef | nodes.AsyncFunctionDef) -> None:
        # Skip modules outside source roots
        file_path = _get_file_path(node)
        if file_path is None or not _is_under_source_root(
            file_path, self._source_roots
        ):
            return

        # Skip __init__ — constructor beartype is an anti-pattern
        if node.name == "__init__":
            return

        # Skip dunder methods (__str__, __repr__, etc.)
        if node.name.startswith("__") and node.name.endswith("__"):
            return

        # Skip _-prefixed (private) functions
        if node.name.startswith("_"):
            return

        # Skip if already decorated with @beartype, @no_type_check
        if self._has_protection_decorator(node):
            return

        module_name = node.root().name
        self.add_message("missing-beartype", node=node, args=(node.name, module_name))

    @staticmethod
    def _has_protection_decorator(
        node: nodes.FunctionDef | nodes.AsyncFunctionDef,
    ) -> bool:
        if node.decorators is None:
            return False
        for dec in node.decorators.nodes:
            if isinstance(dec, nodes.Name) and dec.name in {
                "beartype",
                "no_type_check",
            }:
                return True
            if isinstance(dec, nodes.Attribute) and dec.attrname in {
                "no_type_check",
                "beartype",
            }:
                return True
        return False


def register(  # pylint: disable=missing-beartype  # circular import — PyLinter not available at runtime
    linter: PyLinter,
) -> None:
    linter.register_checker(BeartypeCoverageChecker(linter))
