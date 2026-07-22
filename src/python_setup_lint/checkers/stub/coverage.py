from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path  # TYPE_CHECKING-only import; not available at runtime
from typing import TYPE_CHECKING

import astroid
import structlog
from astroid import nodes

from python_setup_lint.checkers._base import _matches_path

if TYPE_CHECKING:
    from python_setup_lint.checkers.stub.checker import StubChecker
    from python_setup_lint.checkers.stub.import_contract import ImportUsage
log = structlog.get_logger(__name__)


@dataclass
class _CoveragePatterns:
    source_roots: list[Path] = field(default_factory=list)
    test_patterns: list[str] = field(default_factory=list)
    opt_out_patterns: list[str] = field(default_factory=list)
    stub_roots: list[Path] = field(default_factory=list)


@dataclass
class _CoverageState:
    module_index: dict[str, tuple[Path, nodes.Module]] = field(default_factory=dict)
    stub_missing: set[str] = field(default_factory=set)
    stub_index: dict[str, Path] = field(default_factory=dict)
    declaration_index: dict[str, set[str]] = field(default_factory=dict)
    import_usages: list[ImportUsage] = field(default_factory=list)
    production_count: int = 0
    stub_found_count: int = 0
    patterns: _CoveragePatterns = field(default_factory=_CoveragePatterns)
    star_import_policy: str = "error"
    impl_missing_policy: str = "warn"
    current_file_path: Path | None = None
    current_module_name: str | None = None
    main_module_candidates: set[str] = field(default_factory=set)


# ── Pattern matching ──────────────────────────────────────────────────────────


def _is_test_file(checker: StubChecker, path: Path) -> bool:
    return _matches_path(path.as_posix(), checker._coverage.patterns.test_patterns)


def _is_opted_out(checker: StubChecker, path: Path) -> bool:
    return _matches_path(path.as_posix(), checker._coverage.patterns.opt_out_patterns)


# ── Init file exemption ───────────────────────────────────────────────────────


_LOGIC_NODE_TYPES: tuple[type, ...] = (
    nodes.If,
    nodes.Try,
    nodes.With,
    nodes.For,
    nodes.AugAssign,
    nodes.Delete,
    nodes.Raise,
    nodes.Assert,
)


def _is_logic_node(child: nodes.NodeNG) -> bool:
    if isinstance(child, (nodes.FunctionDef, nodes.AsyncFunctionDef)):
        # __getattr__ is logic — requires .pyi, not exempt
        return True
    if isinstance(child, (nodes.ClassDef, nodes.Expr)):
        return True
    if isinstance(child, (nodes.Import, nodes.ImportFrom)):
        return False
    if isinstance(child, nodes.Assign):
        return any(isinstance(target, nodes.AssignName) and target.name != "__all__" for target in child.targets)
    if isinstance(child, nodes.AnnAssign):
        # __version__/__all__ annotated assignments are package metadata, not logic —
        # __init__.py carrying only these (plus docs/imports) needs no .pyi (CodingRules.md:37).
        return not (isinstance(child.target, nodes.AssignName) and child.target.name in {"__version__", "__all__"})
    return bool(isinstance(child, _LOGIC_NODE_TYPES))


def _is_init_exempt(node: nodes.Module) -> bool:
    return not any(_is_logic_node(child) for child in node.body)


def _is_trivial_test_data(node: nodes.Module) -> bool:
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
    for root in checker._coverage.patterns.source_roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:  # pylint: disable=W9740  # best-effort path relative-to fallback; logging would noise unavoidable path-mismatch degrade
            continue
    return False


# ── Stub resolution ───────────────────────────────────────────────────────────


def _resolve_stub(checker: StubChecker, py_path: Path) -> Path | None:
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
    for stub_root in checker._coverage.patterns.stub_roots:
        rel = None
        for root in checker._coverage.patterns.source_roots:
            try:
                rel = py_path.relative_to(root)
                break
            except ValueError:  # pylint: disable=W9740  # best-effort path relative-to fallback; logging would noise unavoidable path-mismatch degrade
                continue
        if rel is not None:
            candidate = stub_root / rel.with_suffix(".pyi")
            if candidate.exists():
                return candidate

    return None


# ── Declaration indexing ──────────────────────────────────────────────────────


def _collect_declarations(stub_module: nodes.Module) -> set[str]:
    declarations: set[str] = set()
    for child in stub_module.body:
        _add_declaration(child, declarations)
    return declarations


def _add_declaration(child: nodes.NodeNG, declarations: set[str]) -> None:
    if isinstance(child, (nodes.FunctionDef, nodes.AsyncFunctionDef, nodes.ClassDef)):
        declarations.add(child.name)
    elif isinstance(child, nodes.Assign):
        for target in child.targets:
            if isinstance(target, nodes.AssignName):
                declarations.add(target.name)
    elif isinstance(child, nodes.AnnAssign):
        if isinstance(child.target, nodes.AssignName):
            declarations.add(child.target.name)
    elif isinstance(child, (nodes.ImportFrom, nodes.Import)):
        for name, _ in child.names:
            declarations.add(name)
    elif isinstance(child, nodes.TypeAlias):
        if isinstance(child.name, nodes.AssignName):
            declarations.add(child.name.name)


def _index_stub_declarations(checker: StubChecker, module_name: str, stub_path: Path) -> None:
    try:
        stub_module = astroid.parse(stub_path.read_text(), module_name=module_name)
    except SyntaxError:
        log.warning("Syntax error in stub", stub_path=str(stub_path))
        return

    checker._coverage.declaration_index[module_name] = _collect_declarations(stub_module)

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


# pylint: disable=missing-beartype  # StubChecker is TYPE_CHECKING-only; beartype can't resolve at runtime
def emit_coverage_violations(checker: StubChecker) -> None:
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
