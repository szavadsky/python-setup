"""Pylint checker: docstring-in-.pyi verification.

CodingRules.md rule: ".pyi only: all usage docstrings". Implementation .py
files should NOT have usage docstrings (params, raises, edge cases) —
those belong in .pyi. Implementation comments (why, tricks) stay in .py.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, cast

from pylint.checkers import BaseChecker

if TYPE_CHECKING:
    from astroid import nodes
    from pylint.lint import PyLinter

    from python_setup_lint.checkers.stub_checker import StubChecker

log = logging.getLogger(__name__)


def _get_stub_checker(linter: PyLinter) -> StubChecker | None:
    """Return the registered StubChecker instance, or None."""
    checkers = linter._checkers.get("stub-checker", [])
    if checkers:
        return cast("StubChecker", checkers[0])
    return None


def _has_companion_stub(py_path: Path, linter: PyLinter) -> bool:
    """Check if *py_path* has a companion .pyi stub.

    Prefers StubChecker's full resolution (inline + package + stub-roots).
    Falls back to inline/package check when StubChecker not registered.
    """
    stub_checker = _get_stub_checker(linter)
    if stub_checker is not None:
        from python_setup_lint.checkers.stub_coverage import _resolve_stub

        result = _resolve_stub(stub_checker, py_path)
        return result is not None

    # Fallback: inline companion only
    if py_path.with_suffix(".pyi").exists():
        return True
    if py_path.name == "__init__.py":
        return py_path.parent.joinpath("__init__.pyi").exists()
    return False


class StubDocstringChecker(BaseChecker):
    """AST visitor that flags usage docstrings in .py files with companion .pyi.

    Only processes modules that passed stub_checker's exemption logic
    (conftest, trivial test data, init-exempt, main-only, test patterns,
    opt-out patterns).

    Uses visitor-method pattern (visit_functiondef, visit_asyncfunctiondef)
    so methods inside classes are also checked. ClassDef is NOT visited —
    class-level docstrings are legitimate in .py per CodingRules.md.
    """

    name = "stub-docstring-checker"
    msgs = {
        "W9700": (
            "Implementation file '%s' has usage docstring for '%s'; move to .pyi",
            "docstring-in-impl",
            "Usage docstrings (params, raises, edge cases) belong in .pyi stubs, "
            "not in .py implementation files. CodingRules.md: '.pyi only: all usage docstrings'.",
        ),
    }

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._enabled_for_module = False
        self._current_module_name: str | None = None

    def visit_module(self, node: nodes.Module) -> None:
        """Decide whether this module should be processed; set up state."""
        self._enabled_for_module = False
        self._current_module_name = None

        raw_file: str | None = getattr(node, "file", None)
        if not raw_file:
            return
        py_path = Path(raw_file).resolve()
        if py_path.suffix != ".py":
            return
        module_name: str = getattr(node, "name", "") or ""
        self._current_module_name = module_name

        # Only process modules that passed stub_checker exemptions
        stub_checker = _get_stub_checker(self.linter)
        if stub_checker is not None:
            if module_name and module_name not in stub_checker._coverage.module_index:
                log.debug("Skip %s: not in stub_checker module_index (exempted)", module_name)
                return

        # Skip files without a companion .pyi
        if not _has_companion_stub(py_path, self.linter):
            return

        self._enabled_for_module = True

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Emit W9700 if function/method has a docstring in an enabled module."""
        if not self._enabled_for_module:
            return
        self._emit_if_docstring(node)

    def visit_asyncfunctiondef(self, node: nodes.AsyncFunctionDef) -> None:
        """Emit W9700 if async function/method has a docstring in an enabled module."""
        if not self._enabled_for_module:
            return
        self._emit_if_docstring(node)

    def _emit_if_docstring(
        self, func_node: nodes.FunctionDef | nodes.AsyncFunctionDef
    ) -> None:
        """Emit W9700 if *func_node* has a docstring (via doc_node)."""
        if func_node.doc_node is not None:
            self.add_message(
                "docstring-in-impl",
                node=func_node,
                args=(self._current_module_name or "", func_node.name),
            )


def register(linter: PyLinter) -> None:
    linter.register_checker(StubDocstringChecker(linter))