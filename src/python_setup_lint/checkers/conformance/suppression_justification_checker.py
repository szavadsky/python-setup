"""Pylint checker: require suppression comments to carry technical justification.

Flags any ``# pylint: disable=...``, ``# noqa: <code>``, ``# type: ignore``
whose line lacks a meaningful technical reason.  The reason may appear as a
trailing comment on the same line, or as a comment on the preceding line.

Any-annotation enforcement scope:
- Standalone annotated assignments (``x: Any = ...``, ``y: dict[str, Any] = ...``)
  via ``visit_annassign`` — fires on ALL files (tests included).
- Function parameter and return annotations via ``visit_functiondef`` /
  ``visit_asyncfunctiondef`` — fires ONLY under configured source roots
  (production code).  Test files are excluded by source-root filtering so
  that test helpers (``**kwargs: Any``, factory returns) are not flagged.
  Each Any-bearing param/return line must carry a trailing ``# <reason>``
  comment on that same line; def-line justification does NOT propagate to
  individual param lines.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from astroid import nodes
from beartype import beartype
from pylint.checkers import BaseChecker
from pylint.typing import MessageDefinitionTuple

from python_setup_lint.checkers._base import (
    MessageDef,
    SourceRootMixin,
    _get_file_path,
    _is_under_source_root,
    _msgs,
    check_if_meaningful,
)

if TYPE_CHECKING:
    from pylint.lint import PyLinter


# Regex patterns for suppression comments.
_PAT_PYLINT_DISABLE = re.compile(r"#\s*pylint:\s*disable=")
_PAT_NOQA = re.compile(r"#\s*noqa(?::\s*\S+)?")
_PAT_TYPE_IGNORE = re.compile(r"#\s*type:\s*ignore")
_PAT_TY_IGNORE = re.compile(r"#\s*ty:\s*ignore")
_PAT_TRAILING_REASON = re.compile(r"#\s+(.+)")
_PAT_PRECEDING_COMMENT = re.compile(r"^\s*#\s+(.+)")


class SuppressionJustificationChecker(SourceRootMixin, BaseChecker):  # type: ignore[misc]  # SourceRootMixin.options conflicts with BaseChecker.options; both define the same pylint options tuple
    """AST visitor that flags unjustified suppression comments."""

    name: str = "suppression-justification"
    msgs: dict[str, MessageDefinitionTuple] = _msgs(
        W9704=MessageDef(
            message="Suppression comment without technical justification: %s",
            symbol="unjustified-suppression",
            description="Suppression comments (pylint-disable, noqa, "
            "type-ignore comments) must be accompanied by a technical reason "
            "on the same line or the preceding line."
        ),
    )

    @beartype
    def visit_module(self, node: object) -> None:
        # Walk the module's source lines looking for bare suppressions.
        try:
            stream = node.stream()  # type: ignore[union-attr]  # node is ModuleNode from astroid, stream() exists at runtime
        except AttributeError, OSError:  # pylint: disable=W9740  # best-effort stream access fallback; logging would noise unavoidable attribute/IO degrade
            return

        try:
            raw = stream.read()
        except OSError:  # pylint: disable=W9740  # best-effort stream read fallback; logging would noise unavoidable IO degrade
            return

        source = raw.decode("utf-8") if isinstance(raw, bytes) else raw

        lines = source.splitlines(keepends=True)

        string_spans = self._get_string_literal_spans(node)

        for lineno, line in enumerate(lines, start=1):
            stripped = line.rstrip("\n")
            if not self._is_suppression_line(stripped):
                continue
            # Check if the suppression # is inside a string literal
            if self._suppression_in_string(stripped, string_spans.get(lineno, [])):
                continue
            if self._has_justification(lines, lineno - 1):
                continue
            self.add_message(
                "unjustified-suppression",
                line=lineno,
                node=node,  # type: ignore[arg-type]  # node is object; add_message expects NodeNG | None  # ty:ignore[invalid-argument-type]
                args=(stripped.strip(),),
            )

    def visit_annassign(self, node: nodes.AnnAssign) -> None:  # pylint: disable=missing-beartype  # nodes.AnnAssign is TYPE_CHECKING-only; @beartype cannot resolve forward ref
        self._check_any_annotation(node)

    def _check_function(self, node: nodes.FunctionDef | nodes.AsyncFunctionDef) -> None:
        # Skip modules outside source roots — param/return Any checks are
        # production-only.  Test files (tests/) are excluded so that test
        # helpers (``**kwargs: Any``, factory returns) are not flagged.
        file_path = _get_file_path(node)
        if file_path is None or not _is_under_source_root(
            file_path, self._source_roots
        ):
            return

        # Collect every annotation-bearing parameter plus the return annotation.
        # astroid stores annotations in parallel arrays aligned with the arg
        # lists; ``varargannotation``/``kwargannotation`` are single nodes.
        args = node.args
        candidates: list[nodes.NodeNG] = []
        candidates.extend(a for a in args.posonlyargs_annotations if a is not None)
        candidates.extend(a for a in args.annotations if a is not None)
        candidates.extend(a for a in args.kwonlyargs_annotations if a is not None)
        if args.varargannotation is not None:
            candidates.append(args.varargannotation)
        if args.kwargannotation is not None:
            candidates.append(args.kwargannotation)
        if node.returns is not None:
            candidates.append(node.returns)

        for annotation in candidates:
            if not self._annotation_contains_any(annotation):
                continue
            lineno = annotation.fromlineno
            if lineno is None:
                continue
            self._emit_if_unjustified(annotation, lineno)

    @staticmethod
    def _annotation_contains_any(annotation: nodes.NodeNG) -> bool:
        # Direct ``Any`` name.
        if isinstance(annotation, nodes.Name) and annotation.name == "Any":
            return True
        # Subscript containing ``Any`` (e.g. ``dict[str, Any]``).
        if isinstance(annotation, nodes.Subscript):
            return SuppressionJustificationChecker._subscript_contains_any(annotation)
        return False

    def _emit_if_unjustified(
        self, annotation: nodes.NodeNG, lineno: int
    ) -> None:
        # Extract the source line for *lineno* and look for a trailing
        # ``# <reason>`` comment on that same line.
        try:
            parent = annotation.root()
            stream = parent.stream()  # type: ignore[union-attr]  # parent.stream() returns a stream object with .read()
            raw = stream.read()
            source = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            lines = source.splitlines(keepends=True)
            src_line = lines[lineno - 1].rstrip("\n")
        except (AttributeError, OSError, IndexError):  # pylint: disable=W9740  # best-effort source line extraction; silently skip if unavailable
            return

        m = _PAT_TRAILING_REASON.search(src_line)
        if m:
            reason = m.group(1)
            if check_if_meaningful(reason, comment=reason):
                return

        self.add_message(
            "unjustified-suppression",
            line=lineno,
            node=annotation,  # type: ignore[arg-type]  # annotation is NodeNG; add_message expects NodeNG | None
            args=(annotation.as_string(),),
        )

    def _check_any_annotation(self, node: nodes.AnnAssign) -> None:
        # Check Any annotations for trailing justification.
        #
        # If the annotation is ``Any`` (or contains ``Any``, e.g.
        # ``dict[str, Any]``) and the line lacks a trailing ``# <reason>``
        # comment, emit ``unjustified-suppression`` (W9704).
        annotation = node.annotation
        if annotation is None:
            return
        if not self._annotation_contains_any(annotation):
            return
        line = node.fromlineno
        if line is None:
            return
        self._emit_if_unjustified(annotation, line)

    @staticmethod
    def _subscript_contains_any(node: nodes.Subscript) -> bool:
        """Recursively check if a Subscript node contains ``Any``.

        Returns:
            True if any part of the subscript is ``Any``.
        """
        # Check the value (e.g. ``dict`` in ``dict[str, Any]``).
        if isinstance(node.value, nodes.Name) and node.value.name == "Any":
            return True
        if isinstance(node.value, nodes.Subscript) and SuppressionJustificationChecker._subscript_contains_any(node.value):
            return True
        # Check the slice.
        if isinstance(node.slice, nodes.Name) and node.slice.name == "Any":
            return True
        if isinstance(node.slice, nodes.Subscript) and SuppressionJustificationChecker._subscript_contains_any(node.slice):
            return True
        # Check tuple slices (e.g. ``dict[str, Any]`` has a Tuple slice).
        if isinstance(node.slice, nodes.Tuple):
            for elt in node.slice.elts:
                if isinstance(elt, nodes.Name) and elt.name == "Any":
                    return True
                if isinstance(elt, nodes.Subscript) and SuppressionJustificationChecker._subscript_contains_any(elt):
                    return True
        return False

    @staticmethod
    def _is_suppression_line(line: str) -> bool:
        """Return True if *line* contains a suppression comment.

        Returns:
            True if *line* contains a suppression comment.
        """
        return bool(
            _PAT_PYLINT_DISABLE.search(line)
            or _PAT_NOQA.search(line)
            or _PAT_TYPE_IGNORE.search(line)
            or _PAT_TY_IGNORE.search(line)
        )

    @staticmethod
    def _get_string_literal_spans(node: object) -> dict[int, list[tuple[int, int]]]:
        """Return dict mapping 1-indexed line numbers to string literal column spans.

        Each entry is ``{lineno: [(start_col, end_col), ...]}`` where
        ``start_col`` and ``end_col`` are 0-indexed character positions
        (exclusive end) of string literal content on that line.
        Falls back to empty dict if AST walking fails.

        Returns:
            Dict mapping line numbers to lists of ``(start, end)`` column spans.
        """
        spans: dict[int, list[tuple[int, int]]] = {}
        try:
            for const_node in node.nodes_of_class(nodes.Const):  # type: ignore[union-attr]  # node is ModuleNode at runtime; nodes_of_class is available
                if not isinstance(const_node.value, str):
                    continue
                start_line = const_node.fromlineno
                end_line = const_node.end_lineno
                start_col = const_node.col_offset
                end_col = const_node.end_col_offset
                if start_line is None or end_line is None or start_col is None or end_col is None:
                    continue
                if start_line == end_line:
                    spans.setdefault(start_line, []).append((start_col, end_col))
                else:
                    # Multi-line string: first line from start_col to end, last line from 0 to end_col
                    spans.setdefault(start_line, []).append((start_col, 10**9))
                    for mid in range(start_line + 1, end_line):
                        spans.setdefault(mid, []).append((0, 10**9))
                    spans.setdefault(end_line, []).append((0, end_col))
        except AttributeError:  # pylint: disable=W9740  # node may not have nodes_of_class (e.g. non-Module node); fall back to empty spans  # best-effort fallback; logging would noise unavoidable attribute degrade
            pass
        return spans

    @staticmethod
    def _suppression_in_string(
        line: str,
        spans: list[tuple[int, int]],
    ) -> bool:
        """Return True if the suppression ``#`` on *line* is inside a string literal.

        Args:
            line: The source line (without trailing newline).
            spans: List of ``(start_col, end_col)`` string literal spans on this line.

        Returns:
            True if the suppression ``#`` falls inside any string literal span.
        """
        if not spans:
            return False
        for pat in (_PAT_PYLINT_DISABLE, _PAT_NOQA, _PAT_TYPE_IGNORE, _PAT_TY_IGNORE):
            m = pat.search(line)
            if m:
                hash_pos = m.start()
                return any(
                    start_col <= hash_pos < end_col
                    for start_col, end_col in spans
                )
        return False

    @staticmethod
    def _has_justification(lines: list[str], idx: int) -> bool:
        """Check whether the suppression at *idx* has a justification.

        Looks for a trailing comment on the same line, or a comment on the
        preceding line.

        Returns:
            True if the suppression at *idx* has a meaningful justification.
        """
        line = lines[idx].rstrip("\n")

        # Same-line trailing comment after the suppression.
        # Find the suppression comment position, then look for a second
        # ``#`` after it.
        for pat in (_PAT_PYLINT_DISABLE, _PAT_NOQA, _PAT_TYPE_IGNORE, _PAT_TY_IGNORE):
            m = pat.search(line)
            if m:
                after = line[m.end() :]
                tm = _PAT_TRAILING_REASON.search(after)
                if tm:
                    reason = tm.group(1)
                    if check_if_meaningful(reason, comment=reason):
                        return True
                break

        # Preceding line is a comment with a reason.
        if idx > 0:
            prev = lines[idx - 1].rstrip("\n")
            pm = _PAT_PRECEDING_COMMENT.match(prev)
            if pm:
                reason = pm.group(1)
                if check_if_meaningful(reason, comment=reason):
                    return True

        return False


def register(linter: PyLinter) -> None:  # pylint: disable=missing-beartype  # pylint entry point, signature fixed by pylint API; @beartype cannot resolve PyLinter forward ref
    # Register the checker with the linter.
    linter.register_checker(SuppressionJustificationChecker(linter))
