"""Phase 1 enforcement — module coverage (every .py has a .pyi).

DocStrings:
- ``_matches_path`` checks if a string path matches any of a list of glob/directory patterns.
- ``_is_test_file`` checks against configured test-patterns.
- ``_is_opted_out`` checks against stub-opt-out patterns.
- ``_is_init_exempt`` checks if ``__init__.py`` is exempt (imports/__all__ only, no logic).
- ``_is_trivial_test_data`` checks if module is trivial test data (literal assignments only).
- ``_has_main_block`` checks if module has ``if __name__ == '__main__':`` block.
- ``_is_under_source_root`` checks if path is under any source-root.
- ``_resolve_stub`` resolves .pyi companions (inline, package, stub-roots).
- ``_index_stub_declarations`` parses a .pyi file and indexes its declarations and AST nodes.
- ``emit_coverage_violations`` emits E97A0 for modules without a .pyi stub.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from astroid import nodes

if TYPE_CHECKING:
    from python_setup_lint.checkers.stub.checker import StubChecker
    from python_setup_lint.checkers.stub.import_contract import ImportUsage

@dataclass
    """Configuration patterns for stub coverage filtering."""

    source_roots: list[Path] = ...
    test_patterns: list[str] = ...
    opt_out_patterns: list[str] = ...
    stub_roots: list[Path] = ...


@dataclass
    """Phase 1 and shared state aggregated for StubChecker."""

    module_index: dict[str, tuple[Path, nodes.Module]] = ...
    stub_missing: set[str] = ...
    stub_index: dict[str, Path] = ...
    declaration_index: dict[str, set[str]] = ...
    import_usages: list[ImportUsage] = ...
    production_count: int = 0
    stub_found_count: int = 0
    patterns: _CoveragePatterns = ...
    star_import_policy: str = "error"
    impl_missing_policy: str = "warn"
    current_file_path: Path | None = None
    current_module_name: str | None = None
    main_module_candidates: set[str] = ...


    """Check if *path* matches any configured test pattern."""

    """Check if *path* matches any stub-opt-out pattern."""

    """Check if an AST child node represents logic (not just imports/assignments)."""

    """Check if an ``__init__.py`` is exempt from stub requirement.

    Exempt when body contains only imports, ``__all__``, and simple
    assignments.  NOT exempt if ``__getattr__`` is defined or any
    non-trivial logic (calls, class/func defs, expressions) exists.
    """

    """Check if module is trivial test data (only literal assignments, no
    classes, functions, or imports)."""

    """Check if module has a ``if __name__ == '__main__':`` block."""

    """Check if *path* is under any configured source root."""

    """Resolve a .pyi companion for *py_path*.

    Returns the resolved stub path or None.

    Resolution order:
    1. Inline ``<module>.pyi`` next to ``<module>.py``.
    2. For ``__init__.py``, companion ``__init__.pyi`` in same directory.
    3. Configured *stub-roots*.
    """

    """Collect all declared symbol names from a stub module's body."""

    """Add a single child's declarations to the set."""

    checker: StubChecker, module_name: str, stub_path: Path
) -> None:
    """Parse a .pyi stub file and index its top-level declarations."""

def emit_coverage_violations(checker: StubChecker) -> None:
    """Emit E97A0 for every module without a .pyi stub."""
