"""Pylint checker: ban try/except ImportError patterns.

Imports must be unconditional — missing dependencies should fail fast at
startup rather than silently degrade at runtime.

Optional-dependency exception: imports from modules declared in
``[project.optional-dependencies]`` (e.g. ``sentence_transformers``)
may use ``try/except ImportError`` for lazy loading.
"""

from __future__ import annotations

from astroid import nodes
from beartype import beartype
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter  # noqa: TCH002  # TYPE_CHECKING-only import; pylint is a dev dependency

from python_setup_lint.checkers._base import LintRuleId, MessageDef

# Optional dependency import patterns — try/except ImportError is allowed
# for imports from these modules (declared in [project.optional-dependencies]).
_OPTIONAL_IMPORT_PATTERNS: frozenset[str] = frozenset({"sentence_transformers"})


def _all_imports_optional(stmts: list[nodes.NodeNG]) -> bool:
    """Return True if every import in *stmts* is from an optional dependency."""
    for stmt in stmts:
        if isinstance(stmt, nodes.Import):
            for alias in stmt.names:
                if alias[0] not in _OPTIONAL_IMPORT_PATTERNS:
                    return False
        elif isinstance(stmt, nodes.ImportFrom):
            if stmt.modname not in _OPTIONAL_IMPORT_PATTERNS:
                return False
    return True


class NoTryImportChecker(BaseChecker):
    """AST visitor that flags try blocks containing imports caught by ImportError / ModuleNotFoundError."""

    name: str = "no-try-import"
    msgs: dict[LintRuleId, MessageDef] = {
        "W9001": MessageDef(
            message="Explicit handling of failed import via try/except %s",
            symbol="no-try-import",
            description="Imports must be unconditional. Use dependency management instead of try/except ImportError guards.",
        ),
    }

    @beartype
    def visit_try(self, node: nodes.Try) -> None:
        import_error_names = {"ImportError", "ModuleNotFoundError"}

        # Quick skip: no imports in try body → nothing to flag
        if not self._has_import(node.body):
            return

        # All imports are from optional dependencies — allowed.
        if _all_imports_optional(node.body):
            return

        for handler in node.handlers:
            caught = self._get_exception_names(handler)
            # bare except: — flag it (try body has imports)
            if not caught:
                self.add_message("no-try-import", node=handler, args=("bare except",))
            elif caught & import_error_names:
                self.add_message(
                    "no-try-import",
                    node=handler,
                    args=(", ".join(sorted(caught & import_error_names)),),
                )

    @staticmethod
    def _get_exception_names(handler: nodes.ExceptHandler) -> set[str]:
        if handler.type is None:
            return set()
        if isinstance(handler.type, nodes.Tuple):
            return {n.name for n in handler.type.elts if isinstance(n, nodes.Name)}
        if isinstance(handler.type, nodes.Name):
            return {handler.type.name}
        return set()

    @staticmethod
    def _has_import(stmts: list[nodes.NodeNG]) -> bool:
        return any(isinstance(stmt, (nodes.Import, nodes.ImportFrom)) for stmt in stmts)


def register(linter: PyLinter) -> None: # pylint: disable=missing-beartype # PyLinter is a pylint internal type not available at runtime for beartype
    linter.register_checker(NoTryImportChecker(linter))
