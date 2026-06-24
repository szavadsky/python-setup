"""Pylint checker enforcing stub coverage (Invariant 1), import contract (Invariant 2),
and stub-impl fidelity (Invariant 3).

Public entry points:
- ``StubChecker`` — ``BaseChecker`` subclass registered via ``register(linter)``.
- ``register(linter)`` — pylint plugin entrypoint, called from ``pyproject.toml``.
"""

from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter

from python_setup_lint.checkers.stub_coverage import _CoverageState
from python_setup_lint.checkers.stub_fidelity import _FidelityState

class StubChecker(BaseChecker):
    """Enforce Invariant 1 (coverage), 2 (import contract), 3 (fidelity)."""

    _coverage: _CoverageState
    _fidelity: _FidelityState

    def __init__(self, linter: PyLinter) -> None: ...
    def open(self) -> None: ...
    def visit_module(self, node: nodes.Module) -> None: ...
    def visit_import(self, node: nodes.Import) -> None: ...
    def visit_importfrom(self, node: nodes.ImportFrom) -> None: ...
    def close(self) -> None: ...
    def _index_impl_annotations(
        self,
        module_name: str,
        py_node: nodes.Module,
    ) -> None: ...

def register(linter: PyLinter) -> None: ...
