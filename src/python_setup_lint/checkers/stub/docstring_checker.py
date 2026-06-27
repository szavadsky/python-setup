"""Pylint checker: docstring-in-.pyi verification.

CodingRules.md rule: ".pyi only: all usage docstrings". Implementation .py
files should NOT have usage docstrings (params, raises, edge cases) —
those belong in .pyi. Implementation comments (why, tricks) stay in .py.
"""

from __future__ import annotations

import structlog
from pathlib import Path
from typing import TYPE_CHECKING, cast

from astroid import nodes  # noqa: TCH002  # TYPE_CHECKING-only import; pylint is a dev dependency
from beartype import beartype
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter  # noqa: TCH002  # TYPE_CHECKING-only import; pylint is a dev dependency

from python_setup_lint.checkers._base import LintRuleId, MessageDef

if TYPE_CHECKING:
    from python_setup_lint.checkers.stub.checker import StubChecker


log = structlog.get_logger(__name__)


def _get_stub_checker(linter: PyLinter) -> StubChecker | None:
    # Return the registered StubChecker instance, or None.
    checkers = linter._checkers.get("stub-checker", [])
    if checkers:
        return cast("StubChecker", checkers[0])
    return None


def _has_companion_stub(py_path: Path, linter: PyLinter) -> bool:
    # True when *py_path* has a companion .pyi stub.
    # Prefers StubChecker's full resolution (inline + package + stub-roots);
    # falls back to inline/package check when StubChecker not registered.
    stub_checker = _get_stub_checker(linter)
    if stub_checker is not None:
        from python_setup_lint.checkers.stub.coverage import _resolve_stub

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

    Also enforces:
    - Generic-return-requires-Returns: functions with non-None concrete return
      type annotations must have a ``Returns:`` clause in their docstring.
    """

    name: str = "stub-docstring-checker"
    _enabled_for_module: bool
    _current_module_name: str | None
    msgs: dict[LintRuleId, MessageDef] = {
        "W9700": MessageDef(
            message="Implementation file '%s' has usage docstring for '%s'; move to .pyi",
            symbol="docstring-in-impl",
            description="Usage docstrings (params, raises, edge cases) belong in .pyi stubs, "
            "not in .py implementation files. CodingRules.md: '.pyi only: all usage docstrings'.",
        ),
        "W9705": MessageDef(
            message="Function '%s' has a non-None return type annotation but no 'Returns:' clause in its docstring",
            symbol="generic-return-requires-returns",
            description="Functions with concrete return type annotations (e.g. -> int, -> str, -> bool) "
            "must have a 'Returns:' clause in their docstring describing the return value. "
            "CodingRules.md: 'Generic-typed returns require a Returns clause'.",
        ),
    }

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._current_module_name: str | None = None
        self._enabled_for_module: bool = False

    @beartype
    def visit_module(self, node: nodes.Module) -> None:
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
        if (
            stub_checker is not None
            and module_name
            and module_name not in stub_checker._coverage.module_index
        ):
            log.debug(
                "Skip module not in stub_checker module_index", module=module_name
            )
            return

        # Skip files without a companion .pyi
        if not _has_companion_stub(py_path, self.linter):
            return

        self._enabled_for_module = True

    @beartype
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        if not self._enabled_for_module:
            return
        self._check_function(node)

    @beartype
    def visit_asyncfunctiondef(self, node: nodes.AsyncFunctionDef) -> None:
        if not self._enabled_for_module:
            return
        self._check_function(node)

    def _check_function(
        self, func_node: nodes.FunctionDef | nodes.AsyncFunctionDef
    ) -> None:
        # Rule 1: docstring-in-impl — flag usage docstrings in .py with companion .pyi
        if func_node.doc_node is not None:
            # _-prefixed helpers MAY have docstrings (no message emitted)
            if not func_node.name.startswith("_"):
                self.add_message(
                    "docstring-in-impl",
                    node=func_node,
                    args=(self._current_module_name or "", func_node.name),
                )

        # Rule 2: generic-return-requires-Returns
        self._check_returns_clause(func_node)

    def _check_returns_clause(
        self, func_node: nodes.FunctionDef | nodes.AsyncFunctionDef
    ) -> None:
        """Emit W9701 if function has a non-None return type but no Returns: clause."""
        returns = func_node.returns
        if returns is None:
            return  # No return type annotation

        # Skip None return type (-> None)
        if isinstance(returns, nodes.Const) and returns.value is None:
            return
        if isinstance(returns, nodes.Name) and returns.name == "None":
            return

        # Check if docstring has a Returns: clause
        doc_node = func_node.doc_node
        if doc_node is None:
            # No docstring at all — no Returns clause to check
            return

        doc_text = doc_node.value
        if not doc_text:
            return

        # Look for a Returns: clause in the docstring
        if not self._has_returns_clause(doc_text):
            self.add_message(
                "generic-return-requires-returns",
                node=func_node,
                args=(func_node.name,),
            )

    @staticmethod
    def _has_returns_clause(doc_text: str) -> bool:
        """Check if a docstring contains a Returns: or Yields: clause."""
        for line in doc_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("Returns:") or stripped.startswith("Yields:"):
                return True
        return False


@beartype
def register(linter: PyLinter) -> None:
    linter.register_checker(StubDocstringChecker(linter))
