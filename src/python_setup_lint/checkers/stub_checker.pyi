"""Pylint checker enforcing stub coverage (Invariant 1), import contract (Invariant 2),
and stub-impl fidelity (Invariant 3).

Public entry points:
- ``StubChecker`` — ``BaseChecker`` subclass registered via ``register(linter)``.
- ``register(linter)`` — pylint plugin entrypoint, called from ``pyproject.toml``.
"""

from pathlib import Path

from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter

from python_setup_lint.checkers.stub_coverage import _CoverageState
from python_setup_lint.checkers.stub_fidelity import _FidelityState

class StubChecker(BaseChecker):
    """Enforce Invariant 1 (coverage), 2 (import contract), 3 (fidelity)."""

    _coverage: _CoverageState
    _fidelity: _FidelityState

    def __init__(self, linter: PyLinter) -> None:
        """Initialize state via dataclass aggregates."""

    def open(self) -> None:
        """Read pylint config into state dataclasses."""

    def visit_module(self, node: nodes.Module) -> None:
        """Classify and index each .py file."""


    def _is_module_exempt(
        self, node: nodes.Module, py_path: Path, module_name: str
    ) -> bool:
        """Check if a module is exempt from stub requirements."""

    def _index_module(
        self, node: nodes.Module, py_path: Path, module_name: str
    ) -> None:
        """Index a module's stub and track coverage."""

    def visit_import(self, node: nodes.Import) -> None:
        """Record import facts for ``import X`` / ``import X as Y``."""

    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        """Record import facts for ``from X import Y``."""

    def close(self) -> None:
        """Emit Phase 1-3 violations: coverage, import contract, fidelity.

        Post-processing: remove non-imported ``__main__`` modules from
        stub-missing (standalone scripts exempt from stub requirement).
        """

    def _index_impl_annotations(
        self,
        module_name: str,
        py_node: nodes.Module,
    ) -> None:
        """Index annotation nodes from implementation for fidelity comparison."""

def register(linter: PyLinter) -> None:
    """Register the StubChecker with pylint."""
