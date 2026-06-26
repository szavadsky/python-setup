"""Pylint checker: require suppression comments to carry technical justification.

Flags any ``# pylint: disable=...``, ``# noqa: <code>``, ``# type: ignore``
whose line lacks a meaningful technical reason.  The reason may appear as a
trailing comment on the same line, or as a comment on the preceding line.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from beartype import beartype
from pylint.checkers import BaseChecker

from python_setup_lint.checkers._base import MessageDef, check_if_meaningful

if TYPE_CHECKING:
    from pylint.lint import PyLinter


# Regex patterns for suppression comments.
_PAT_PYLINT_DISABLE = re.compile(r"#\s*pylint:\s*disable=")
_PAT_NOQA = re.compile(r"#\s*noqa(?::\s*\S+)?")
_PAT_TYPE_IGNORE = re.compile(r"#\s*type:\s*ignore")
_PAT_TRAILING_REASON = re.compile(r"#\s+(.+)")
_PAT_PRECEDING_COMMENT = re.compile(r"^\s*#\s+(.+)")


class SuppressionJustificationChecker(BaseChecker):
    """AST visitor that flags unjustified suppression comments."""

    name: str = "suppression-justification"
    msgs: dict[str, MessageDef] = {
        "W9704": MessageDef(
            message="Suppression comment without technical justification: %s",
            symbol="unjustified-suppression",
            description=(
                "Suppression comments (# pylint: disable=..., # noqa, "
                "# type: ignore) must be accompanied by a technical reason "
                "on the same line or the preceding line."
            ),
        ),
    }

    @beartype
    def visit_module(self, node: object) -> None:
        """Walk the module's source lines looking for bare suppressions."""
        try:
            stream = node.stream()  # type: ignore[union-attr]  # node is ModuleNode from astroid, stream() exists at runtime
        except (AttributeError, OSError):
            return

        try:
            raw = stream.read()
        except OSError:
            return

        if isinstance(raw, bytes):
            source = raw.decode("utf-8")
        else:
            source = raw

        lines = source.splitlines(keepends=True)

        for lineno, line in enumerate(lines, start=1):
            stripped = line.rstrip("\n")
            if not self._is_suppression_line(stripped):
                continue
            if self._has_justification(lines, lineno - 1):
                continue
            self.add_message(
                "unjustified-suppression",
                line=lineno,
                args=(stripped.strip(),),
            )

    @staticmethod
    def _is_suppression_line(line: str) -> bool:
        """Return True if *line* contains a suppression comment."""
        return bool(
            _PAT_PYLINT_DISABLE.search(line)
            or _PAT_NOQA.search(line)
            or _PAT_TYPE_IGNORE.search(line)
        )

    @staticmethod
    def _has_justification(lines: list[str], idx: int) -> bool:
        """Check whether the suppression at *idx* has a justification.

        Looks for a trailing comment on the same line, or a comment on the
        preceding line.
        """
        line = lines[idx].rstrip("\n")

        # Same-line trailing comment after the suppression.
        # Find the suppression comment position, then look for a second
        # ``#`` after it.
        for pat in (_PAT_PYLINT_DISABLE, _PAT_NOQA, _PAT_TYPE_IGNORE):
            m = pat.search(line)
            if m:
                after = line[m.end() :]
                tm = _PAT_TRAILING_REASON.search(after)
                if tm:
                    reason = tm.group(1)
                    if check_if_meaningful(reason):
                        return True
                break

        # Preceding line is a comment with a reason.
        if idx > 0:
            prev = lines[idx - 1].rstrip("\n")
            pm = _PAT_PRECEDING_COMMENT.match(prev)
            if pm:
                reason = pm.group(1)
                if check_if_meaningful(reason):
                    return True

        return False


@beartype
def register(linter: PyLinter) -> None:  # pylint: disable=missing-beartype  # pylint entry point, signature fixed by pylint API
    """Register the checker with the linter."""
    linter.register_checker(SuppressionJustificationChecker(linter))
