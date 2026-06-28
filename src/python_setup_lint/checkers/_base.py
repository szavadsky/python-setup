"""Shared utilities for pylint checkers.

Consolidates duplicate code across checker modules:
- ``MessageDef`` — named representation for checker message definitions.
- ``_matches_path`` — glob/directory path matching (was in stub_coverage.py and tmp_path_checker.py).
- ``_is_under_source_root`` — source-root containment check (was in beartype_checker.py and stub_coverage.py).
- ``_get_file_path`` — resolve a node's file path (was in beartype_checker.py).
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import NamedTuple, NewType
from beartype import beartype

from astroid import nodes  # noqa: TCH002  # astroid is a pylint dependency, only used for type checking in this module


LintRuleId = NewType("LintRuleId", str)


class MessageDef(NamedTuple):
    """Named representation for a pylint checker message definition.

    Replaces bare ``(message, symbol, description)`` tuples in checker
    ``msgs`` dicts with a typed, self-documenting record.
    """

    message: str
    symbol: str
    description: str


def _msgs(**definitions: MessageDef) -> dict[LintRuleId, MessageDef]:
    """Build a checker msgs dict with domain-typed keys."""
    return {LintRuleId(k): v for k, v in definitions.items()}


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
    }
    if primary_lower in meaningless_phrases:
        return False
    # Reject justification that is just the rule symbol itself.
    if rule and primary_lower == rule.lower():
        return False
    return True
