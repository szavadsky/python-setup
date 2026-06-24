"""Pylint checker: @beartype coverage inventory.

Reports W9701 for public functions/methods missing @beartype decorator.
Informational (W-level) only — does not block builds.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from astroid import nodes
from pylint.checkers import BaseChecker

if TYPE_CHECKING:
    from pylint.lint import PyLinter

log = logging.getLogger(__name__)


class BeartypeCoverageChecker(BaseChecker):
    """AST visitor that inventories @beartype coverage on public functions."""

    name = "beartype-coverage"
    msgs = {
        "W9701": (
            "Public function '%s' in '%s' is missing @beartype decorator",
            "missing-beartype",
            "All public functions should have @beartype for runtime type enforcement.",
        ),
    }
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

    def open(self) -> None:
        config = self.linter.config
        raw_roots = getattr(config, "source_roots", None)
        self._source_roots = (
            [Path(r).resolve() for r in raw_roots if r]
            if raw_roots
            else [Path("src").resolve()]
        )

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        self._check_function(node)

    def visit_asyncfunctiondef(self, node: nodes.AsyncFunctionDef) -> None:
        self._check_function(node)

    def _check_function(
        self, node: nodes.FunctionDef | nodes.AsyncFunctionDef
    ) -> None:
        # Skip modules outside source roots
        file_path = self._get_file_path(node)
        if file_path is None or not self._is_under_source_root(file_path):
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
            if isinstance(dec, nodes.Name) and dec.name in {"beartype", "no_type_check"}:
                return True
            if isinstance(dec, nodes.Attribute) and dec.attrname == "no_type_check":
                return True
        return False

    @staticmethod
    def _get_file_path(node: nodes.FunctionDef | nodes.AsyncFunctionDef) -> Path | None:
        try:
            file_val = node.root().file
            if file_val is None:
                return None
            return Path(file_val)
        except (AttributeError, TypeError):
            return None

    def _is_under_source_root(self, path: Path) -> bool:
        resolved = path.resolve()
        for root in self._source_roots:
            try:
                resolved.relative_to(root)
                return True
            except ValueError:
                continue
        return False


def register(linter: PyLinter) -> None:
    linter.register_checker(BeartypeCoverageChecker(linter))
