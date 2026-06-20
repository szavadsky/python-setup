"""Phase 1 enforcement — module coverage (every .py has a .pyi).

Extracted from stub_checker.py.  Mechanical cut-paste, no logic change.
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import astroid
from astroid import nodes

if TYPE_CHECKING:
    from python_setup_lint.checkers.stub_checker import StubChecker
    from python_setup_lint.checkers.stub_import_contract import ImportUsage

log = logging.getLogger(__name__)


@dataclass
class _CoverageState:
    """Phase 1 and shared state aggregated for StubChecker.

    Stores coverage tracking state, import-usages, and configuration
    values read from pylint TOML.  Defaults match pylint TOML defaults.
    """

    module_index: dict[str, tuple[Path, nodes.Module]] = field(default_factory=dict)
    stub_missing: set[str] = field(default_factory=set)
    stub_index: dict[str, Path] = field(default_factory=dict)
    declaration_index: dict[str, set[str]] = field(default_factory=dict)
    import_usages: list[ImportUsage] = field(default_factory=list)
    production_count: int = 0
    stub_found_count: int = 0
    source_roots: list[Path] = field(default_factory=list)
    test_patterns: list[str] = field(default_factory=list)
    opt_out_patterns: list[str] = field(default_factory=list)
    stub_roots: list[Path] = field(default_factory=list)
    star_import_policy: str = "error"
    impl_missing_policy: str = "warn"
    current_file_path: Path | None = None
    current_module_name: str | None = None
    main_module_candidates: set[str] = field(default_factory=set)


# ── Pattern matching ──────────────────────────────────────────────────────────


def _matches_path(str_path: str, patterns: list[str]) -> bool:
    """Check if *str_path* matches any of the *patterns*.

    Patterns containing ``/`` or ``\\`` are treated as directory prefixes;
    other patterns use fnmatch globbing against the full path and basename.
    """
    for pattern in patterns:
        if "/" in pattern or "\\" in pattern:
            # Directory prefix pattern
            if str_path.startswith(pattern) or f"/{pattern.lstrip('/')}" in str_path:
                return True
        elif fnmatch.fnmatch(str_path, pattern) or fnmatch.fnmatch(Path(str_path).name, pattern):
            return True
    return False


def _is_test_file(checker: StubChecker, path: Path) -> bool:
    """Check if *path* matches any configured test pattern."""
    return _matches_path(path.as_posix(), checker._coverage.test_patterns)


def _is_opted_out(checker: StubChecker, path: Path) -> bool:
    """Check if *path* matches any stub-opt-out pattern."""
    return _matches_path(path.as_posix(), checker._coverage.opt_out_patterns)


# ── Init file exemption ───────────────────────────────────────────────────────


def _is_init_exempt(node: nodes.Module) -> bool:
    """Check if an ``__init__.py`` is exempt from stub requirement.

    Exempt when body contains only imports, ``__all__``, and simple
    assignments.  NOT exempt if ``__getattr__`` is defined or any
    non-trivial logic (calls, class/func defs, expressions) exists.
    """
    has_logic = False
    for child in node.body:
        if isinstance(child, (nodes.FunctionDef, nodes.AsyncFunctionDef)):
            # Only __getattr__ is allowed in __init__.py
            if child.name == "__getattr__":
                return False  # NOT exempt — requires .pyi
            # Any other function def is logic
            has_logic = True
        elif isinstance(child, nodes.ClassDef):
            has_logic = True
        elif isinstance(child, nodes.Expr):
            # Standalone expression (call, etc.) is logic
            has_logic = True
        elif isinstance(child, (nodes.Import, nodes.ImportFrom)):
            continue  # imports are ok
        elif isinstance(child, nodes.Assign):
            # __all__ assignment ok; anything else is logic
            for target in child.targets:
                if isinstance(target, nodes.AssignName) and target.name != "__all__":
                    has_logic = True
        elif isinstance(
            child,
            (
                nodes.AnnAssign,
                nodes.If,
                nodes.Try,
                nodes.With,
                nodes.For,
                nodes.AugAssign,
                nodes.Delete,
                nodes.Raise,
                nodes.Assert,
            ),
        ):
            has_logic = True
        # Pass, ellipsis, docstring-like Expr with Const → skip
    return not has_logic


def _is_trivial_test_data(node: nodes.Module) -> bool:
    """Check if module is trivial test data (only literal assignments, no
    classes, functions, or imports)."""
    for child in node.body:
        if isinstance(child, (nodes.FunctionDef, nodes.AsyncFunctionDef, nodes.ClassDef)):
            return False
        if isinstance(child, (nodes.Import, nodes.ImportFrom)):
            return False
        if isinstance(child, nodes.Expr):
            return False
        if isinstance(child, nodes.If):
            return False
        if isinstance(child, nodes.Assign):
            # Only allow simple literal/comprehension-free assignments
            for target in child.targets:
                if not isinstance(target, nodes.AssignName):
                    return False
    return True


def _has_main_block(node: nodes.Module) -> bool:
    """Check if module has a ``if __name__ == '__main__':`` block."""
    for child in node.body:
        if isinstance(child, nodes.If):
            test = child.test
            # __name__ == '__main__' or __name__ == "__main__"
            if isinstance(test, nodes.Compare) and len(test.ops) >= 1 and test.ops[0][0] == "==":
                left = test.left
                right = test.ops[0][1]
                if (
                    isinstance(left, nodes.Name)
                    and left.name == "__name__"
                    and isinstance(right, nodes.Const)
                    and right.value == "__main__"
                ):
                    return True
    return False


# ── Source root check ─────────────────────────────────────────────────────────


def _is_under_source_root(checker: StubChecker, path: Path) -> bool:
    """Check if *path* is under any configured source root."""
    for root in checker._coverage.source_roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


# ── Stub resolution ───────────────────────────────────────────────────────────


def _resolve_stub(checker: StubChecker, py_path: Path) -> Path | None:
    """Resolve a .pyi companion for *py_path*.

    Returns the resolved stub path or None.

    Resolution order:
    1. Inline ``<module>.pyi`` next to ``<module>.py``.
    2. For ``__init__.py``, companion ``__init__.pyi`` in same directory.
    3. Configured *stub-roots*.
    """
    # 1. Inline companion
    inline = py_path.with_suffix(".pyi")
    if inline.exists():
        return inline

    # 2. Package __init__ stub
    if py_path.name == "__init__.py":
        pkg_init = py_path.parent.joinpath("__init__.pyi")
        if pkg_init.exists():
            return pkg_init

    # 3. Stub roots
    for stub_root in checker._coverage.stub_roots:
        rel = None
        for root in checker._coverage.source_roots:
            try:
                rel = py_path.relative_to(root)
                break
            except ValueError:
                continue
        if rel is not None:
            candidate = stub_root / rel.with_suffix(".pyi")
            if candidate.exists():
                return candidate

    return None


# ── Declaration indexing ──────────────────────────────────────────────────────


def _index_stub_declarations(checker: StubChecker, module_name: str, stub_path: Path) -> None:
    """Parse a .pyi stub file and index its top-level declarations."""
    try:
        stub_module = astroid.parse(stub_path.read_text(), module_name=module_name)
    except SyntaxError:
        log.warning("Syntax error in stub '%s' — cannot index declarations", stub_path)
        return

    declarations: set[str] = set()
    for child in stub_module.body:
        if isinstance(child, (nodes.FunctionDef, nodes.AsyncFunctionDef, nodes.ClassDef)):
            declarations.add(child.name)
        elif isinstance(child, nodes.Assign):
            for target in child.targets:
                if isinstance(target, nodes.AssignName):
                    declarations.add(target.name)
        elif isinstance(child, nodes.AnnAssign):
            if isinstance(child.target, nodes.AssignName):
                declarations.add(child.target.name)
        elif isinstance(child, nodes.TypeAlias):
            declarations.add(child.name.name)

    checker._coverage.declaration_index[module_name] = declarations

    # Also index callable and class nodes for fidelity phase
    f = checker._fidelity
    stub_vars: dict[str, nodes.AnnAssign] = {}
    stub_callables: dict[str, nodes.FunctionDef | nodes.AsyncFunctionDef] = {}
    stub_classes: dict[str, nodes.ClassDef] = {}
    for child in stub_module.body:
        if isinstance(child, nodes.AnnAssign) and isinstance(child.target, nodes.AssignName):
            stub_vars[child.target.name] = child
        elif isinstance(child, (nodes.FunctionDef, nodes.AsyncFunctionDef)):
            stub_callables[child.name] = child
        elif isinstance(child, nodes.ClassDef):
            stub_classes[child.name] = child
    f.stub_variable_nodes[module_name] = stub_vars
    f.stub_callable_nodes[module_name] = stub_callables
    f.stub_class_nodes[module_name] = stub_classes


# ── Public API ─────────────────────────────────────────────────────────────────


def emit_coverage_violations(checker: StubChecker) -> None:
    """Emit E97A0 for every module without a .pyi stub."""
    c = checker._coverage
    for module_name in sorted(c.stub_missing):
        entry = c.module_index.get(module_name)
        if entry is None:
            continue
        py_path, node = entry
        checker.add_message(
            "missing-module-stub",
            node=node,
            args=(module_name,),
        )