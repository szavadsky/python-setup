"""Pylint checker: missing return type annotations on _-prefixed functions.

Reports W9741 for module-private functions (``_``-prefixed, not ``__`` dunders)
that lack a return type annotation.  Public functions are covered by the
beartype checker; this fills the gap for private helpers.

W-level only — does not affect build exit codes.
"""

from __future__ import annotations

from pathlib import Path
from beartype import beartype

from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter  # noqa: TCH002  # TYPE_CHECKING-only import; pylint is a dev dependency

from python_setup_lint.checkers._base import (
    LintRuleId,
    MessageDef,
    _get_file_path,
    _is_under_source_root,
    _msgs,
)


class MissingReturnAnnotationChecker(BaseChecker):
    """AST visitor that flags _-prefixed functions missing return annotations."""

    name: str = "missing-return-annotation"

    msgs = _msgs(
        W9741=MessageDef(
            message="_-prefixed function %s() is missing a return type annotation",
            symbol="missing-return-annotation",
            description="Module-private functions must declare return types (CodingRules: precise types; beartype precision).",
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
