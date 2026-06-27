"""Pylint checker: @beartype coverage inventory.

Reports W9701 for public functions/methods missing @beartype decorator.
Informational (W-level) only — does not block builds.
"""

from __future__ import annotations

import structlog
from pathlib import Path

from astroid import nodes
from beartype import beartype
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter  # noqa: TCH002  # TYPE_CHECKING-only import; pylint is a dev dependency

from python_setup_lint.checkers._base import (
    LintRuleId,
    MessageDef,
    _get_file_path,
    _is_under_source_root,
    _msgs,
)

log = structlog.get_logger(__name__)


class BeartypeCoverageChecker(BaseChecker):
    """AST visitor that inventories @beartype coverage on public functions."""

    name: str = "beartype-coverage"
    msgs = _msgs(
        W9701=MessageDef(
            message="Public function '%s' in '%s' is missing @beartype decorator",
            symbol="missing-beartype",
            description="All public functions should have @beartype for runtime type enforcement.",
        ),
    )
    options = (
        (
            "source-roots",
            {
                "type": "csv",
                "metavar": "<dirs>",
                "default": ["src"],
                "help": "Source root directories for production code.",
            },
        ),
    )

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._source_roots: list[Path] = []

    @beartype
    def open(self) -> None:
        config = self.linter.config
        raw_roots = getattr(config, "source_roots", None)
        self._source_roots = (
            [Path(r).resolve() for r in raw_roots if r]
            if raw_roots
            else [Path("src").resolve()]
        )

    @beartype
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        self._check_function(node)

    def visit_asyncfunctiondef(  # pylint: disable=missing-beartype  # circular import — AsyncFunctionDef not available at runtime
        self, node: nodes.AsyncFunctionDef
    ) -> None:
        self._check_function(node)

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
            if isinstance(dec, nodes.Attribute) and dec.attrname == "no_type_check":
                return True
        return False


def register(  # pylint: disable=missing-beartype  # circular import — PyLinter not available at runtime
    linter: PyLinter,
) -> None:
    linter.register_checker(BeartypeCoverageChecker(linter))
