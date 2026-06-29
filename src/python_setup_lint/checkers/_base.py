"""Shared utilities for pylint checkers.

Consolidates duplicate code across checker modules:
- ``MessageDef`` — named representation for checker message definitions.
- ``_matches_path`` — glob/directory path matching (was in stub_coverage.py and tmp_path_checker.py).
- ``_is_under_source_root`` — source-root containment check (was in beartype_checker.py and stub_coverage.py).
- ``_get_file_path`` — resolve a node's file path (was in beartype_checker.py).
"""

from __future__ import annotations

import fnmatch
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import structlog
from astroid import nodes  # astroid is a pylint dependency, only used for type checking in this module
from beartype import beartype
from pylint.typing import MessageDefinitionTuple

# Configure structlog at import time to suppress debug/info noise from all checkers.
# This runs when pylint loads the first checker plugin (pylint subprocess).
# The wrapper_class filters at the bound-logger level, before events reach
# the processor chain. Tests that use structlog.testing.capture_logs() must
# save/restore the wrapper_class around their test.
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
)

if TYPE_CHECKING:
    from pylint.lint import PyLinter


class MessageDef(NamedTuple):
    """Named representation for a pylint checker message definition.

    Replaces bare ``(message, symbol, description)`` tuples in checker
    ``msgs`` dicts with a typed, self-documenting record.
    """

    message: str
    symbol: str
    description: str


def _msgs(**definitions: MessageDef) -> dict[str, MessageDefinitionTuple]:  # pylint: disable=trivial-wrapper  # typed factory: provides message-ID-keyed dict with MessageDef values, not a raw dict
    """Build a checker msgs dict with domain-typed keys.

    Returns:
        A dict mapping message IDs (e.g. ``W9700``) to ``MessageDefinitionTuple``
        records, suitable for assignment to a ``BaseChecker.msgs`` class attribute.
    """
    return dict(definitions.items())


def _matches_path(str_path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if "/" in pattern or "\\" in pattern:
            # Directory prefix pattern
            if str_path.startswith(pattern) or f"/{pattern.lstrip('/')}" in str_path:
                return True
        elif fnmatch.fnmatch(str_path, pattern) or fnmatch.fnmatch(
            Path(str_path).name, pattern
        ):
            return True
    return False


def _is_under_source_root(path: Path, source_roots: list[Path]) -> bool:
    resolved = path.resolve()
    for root in source_roots:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:  # pylint: disable=W9740  # best-effort path relative-to fallback; logging would noise unavoidable path-mismatch degrade
            continue
    return False


def _get_file_path(node: nodes.FunctionDef | nodes.AsyncFunctionDef) -> Path | None:
    try:
        file_val = node.root().file
        if file_val is None:
            return None
        return Path(file_val)
    except AttributeError, TypeError:  # pylint: disable=W9740  # best-effort file path extraction fallback; logging would noise unavoidable attribute/type degrade
        return None


class SourceRootMixin:
    """Mixin for checkers that filter by source root directories.

    Provides shared ``options`` (``source-roots``), ``__init__``, ``open``,
    ``visit_functiondef``, and ``visit_asyncfunctiondef`` boilerplate that
    is structurally identical across multiple checkers by pylint API design.
    """

    _source_roots: list[Path] = []

    options: tuple[tuple[str, dict[str, object]], ...] = (
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

    def __init__(self, linter: PyLinter) -> None:  # type: ignore[reportCallIssue]  # mixin: super().__init__ called with linter arg; BaseChecker.__init__ accepts it via MRO
        super().__init__(linter)  # type: ignore[reportCallIssue]  # ty: ignore[too-many-positional-arguments]  # mixin: BaseChecker.__init__ accepts linter arg via MRO
        self._source_roots: list[Path] = []

    # pylint: disable=missing-beartype  # mixin: self.linter resolved at runtime via MRO; @beartype cannot resolve forward ref
    def open(self) -> None:  # type: ignore[reportAttributeAccessIssue]  # mixin: self.linter exists when mixed with BaseChecker
        config = self.linter.config  # type: ignore[reportAttributeAccessIssue]  # mixin: linter attr from BaseChecker
        raw_roots = getattr(config, "source_roots", None)
        self._source_roots = (
            [Path(r).resolve() for r in raw_roots if r]
            if raw_roots
            else [Path("src").resolve()]
        )

    # pylint: disable=missing-beartype  # mixin: _check_function defined in subclass; @beartype cannot resolve forward ref
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:  # type: ignore[reportAttributeAccessIssue]  # mixin: _check_function defined in subclass
        self._check_function(node)  # type: ignore[reportAttributeAccessIssue]  # mixin: _check_function defined in subclass

    def visit_asyncfunctiondef(  # type: ignore[reportAttributeAccessIssue]  # mixin: _check_function defined in subclass  # pylint: disable=missing-beartype  # circular import — AsyncFunctionDef not available at runtime
        self, node: nodes.AsyncFunctionDef
    ) -> None:
        self._check_function(node)  # type: ignore[reportAttributeAccessIssue]  # mixin: _check_function defined in subclass


@beartype
def check_if_meaningful(
    text: str,
    *,
    rule: str | None = None,
    code_context: str | None = None,
    comment: str | None = None,
) -> bool:
    # Try the semantic NLP pipeline when enabled.
    if os.environ.get("PYTHON_SETUP_LINT_SEMANTIC", "1") == "1":
        from python_setup_lint.checkers._semantic import (
            semantic_check_if_meaningful as _semantic_check,
        )

        result = _semantic_check(
            text, rule=rule, code_context=code_context, comment=comment
        )
        if result is not None:
            return result

    # Heuristic fallback.
    primary = (comment or text).strip()
    if not primary or len(primary) < 5:
        return False
    primary_lower = primary.lower()
    boilerplate = {
        "noqa",
        "ignore",
        "suppress",
        "disable",
        "skip",
        "todo",
        "fixme",
        "hack",
        "fixed",
        "works",
        "broken",
        "check",
        "update",
        "remove",
        "change",
        "improve",
        "refactor",
        "done",
        "test",
        "blank",
        "empty",
        # Brush-off / deferral patterns
        "pre-existing",
        "preexisting",
        "baseline",
        "base-line",
        "wip",
        "tbd",
        "temp",
        "temporary",
        "existing",
        "as-is",
        "legacy",
        "will fix",
        "later",
        "eventually",
        "someday",
        "placeholder",
        "stub here",
        "for now",
        "to do",
        "fixme later",
        "carryover",
    }
    if primary_lower in boilerplate:
        return False
    # Reject multi-word meaningless phrases.
    meaningless_phrases = {
        "fix this",
        "need to check",
        "maybe later",
        "not sure",
        # Brush-off / deferral multi-word patterns
        "pre existing",
        "in baseline",
        "was already",
        "not my code",
        "carry over",
        "from before",
        "carry from",
        # Compound brush-off phrases
        "pre-existing issue",
        "baseline issue",
        "todo later",
        "existing issue",
        "will fix later",
        "fix later",
        "preexisting issue",
    }
    if primary_lower in meaningless_phrases:
        return False
    # Reject justification that is just the rule symbol itself.
    return not (rule and primary_lower == rule.lower())
