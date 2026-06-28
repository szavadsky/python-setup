"""Enforce stub coverage (Invariant 1), import contract (Invariant 2), and
stub-impl fidelity (Invariant 3): every production .py needs a .pyi stub;
project-local imports must reference declared stub symbols; .pyi annotations
and signatures must match .py counterparts after normalization.
"""

from __future__ import annotations

from pathlib import Path

import structlog
from astroid import nodes
from beartype import beartype
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter  # TYPE_CHECKING-only import; pylint is a dev dependency

from python_setup_lint.checkers._base import MessageDef, _msgs
from python_setup_lint.checkers.stub.coverage import (
    _CoverageState,
    _has_main_block,
    _index_stub_declarations,
    _is_init_exempt,
    _is_opted_out,
    _is_test_file,
    _is_trivial_test_data,
    _is_under_source_root,
    _resolve_stub,
    emit_coverage_violations,
)
from python_setup_lint.checkers.stub.fidelity import (
    _FidelityState,
    emit_fidelity_violations,
)
from python_setup_lint.checkers.stub.import_contract import (
    ImportUsage,
    _in_type_checking_block,
    _resolve_relative,
    emit_import_contract_violations,
)

log = structlog.get_logger(__name__)


class StubChecker(BaseChecker):
    """Enforce Invariant 1 (coverage), 2 (import contract), 3 (fidelity).

    Configuration via TOML under ``[tool.pylint.stub-checker]``.
    """

    name = "stub-checker"
    msgs = _msgs(
        E97A0=MessageDef(
            message="Production module '%s' has no companion .pyi stub",
            symbol="missing-module-stub",
            description="Every production Python module must have a corresponding .pyi stub file.",
        ),
        E97A1=MessageDef(
            message="Symbol '%s' imported by '%s' is not declared in target stub '%s'",
            symbol="missing-import-declaration",
            description="Every project-local import must refer to a symbol declared in the target module's .pyi stub.",
        ),
        E97A2=MessageDef(
            message="Project-local module '%s' imported by '%s' has no .pyi stub",
            symbol="missing-module-stub-for-import",
            description="Every imported project-local module must have a .pyi stub.",
        ),
        E97A3=MessageDef(
            message="Star import from '%s' in '%s' cannot be statically resolved",
            symbol="star-import-unresolvable",
            description="Star imports from project-local modules are not statically resolvable.",
        ),
        E97B3=MessageDef(
            message="Signature mismatch on '%s' in module '%s': %s",
            symbol="signature-mismatch",
            description="Parameter count, name, kind, or default-presence differs between .pyi stub and .py implementation.",
        ),
        E97B4=MessageDef(
            message="Annotation mismatch on '%s' in module '%s': stub has '%s', impl has '%s'",
            symbol="annotation-mismatch",
            description="Variable annotation in .pyi differs from the .py implementation after normalization.",
        ),
        W97B5=MessageDef(
            message="Implementation of '%s' in '%s' has no annotation (stub annotates)",
            symbol="impl-missing-annotation",
            description="Variable is annotated in the .pyi stub but the .py implementation has no annotation.",
        ),
        I97B6=MessageDef(
            message="Annotation for '%s' in module '%s' could not be normalized",
            symbol="annotation-unverifiable",
            description="Annotation is too complex to normalize and compare. Manual review needed.",
        ),
        E97B1=MessageDef(
            message="Stub symbol '%s' in module '%s' has no implementation",
            symbol="stub-symbol-missing",
            description="Symbol declared in .pyi stub is absent from .py implementation.",
        ),
        E97B2=MessageDef(
            message="Kind mismatch for '%s' in module '%s': stub declares '%s', implementation has '%s'",
            symbol="symbol-kind-mismatch",
            description="Symbol exists in both stub and impl but their kinds differ (e.g. class vs function, variable vs class).",
        ),
    )
    options = (
        (
            "source-roots",
            {
                "type": "csv",
                "metavar": "<dirs>",
                "default": ["src"],
                "help": "Source root directories for production code.",
            },
        ),
        (
            "test-patterns",
            {
                "type": "csv",
                "metavar": "<patterns>",
                "default": ["tests/", "test_*.py", "*_test.py", "conftest.py"],
                "help": "Glob patterns for identifying test files.",
            },
        ),
        (
            "stub-opt-out",
            {
                "type": "csv",
                "metavar": "<patterns>",
                "default": [],
                "help": "Path patterns to exclude from stub coverage enforcement.",
            },
        ),
        (
            "stub-roots",
            {
                "type": "csv",
                "metavar": "<dirs>",
                "default": [],
                "help": "Additional directories to search for .pyi stubs.",
            },
        ),
        (
            "star-import-policy",
            {
                "type": "string",
                "metavar": "<policy>",
                "default": "error",
                "help": "Policy for star imports: 'error', 'warn', or 'ignore'.",
            },
        ),
        (
            "impl-missing-annotation",
            {
                "type": "string",
                "metavar": "<policy>",
                "default": "warn",
                "help": "Severity when stub annotates but impl does not: 'error', 'warn', or 'ignore'.",
            },
        ),
    )

    _coverage: _CoverageState
    _fidelity: _FidelityState

    def __init__(self, linter: PyLinter) -> None:
        super().__init__(linter)
        self._coverage = _CoverageState()
        self._fidelity = _FidelityState()

    @beartype
    def open(self) -> None:
        c = self._coverage
        config = self.linter.config
        raw_roots = getattr(config, "source_roots", None)
        c.patterns.source_roots = (
            [Path(r).resolve() for r in raw_roots if r]
            if raw_roots
            else [Path("src").resolve()]
        )
        raw_patterns = getattr(config, "test_patterns", None)
        c.patterns.test_patterns = (
            list(raw_patterns)
            if raw_patterns
            else [
                "tests/",
                "test_*.py",
                "*_test.py",
                "conftest.py",
            ]
        )
        raw_opt_out = getattr(config, "stub_opt_out", None)
        c.patterns.opt_out_patterns = list(raw_opt_out) if raw_opt_out else []
        raw_stub_roots = getattr(config, "stub_roots", None)
        c.patterns.stub_roots = (
            [Path(r) for r in raw_stub_roots if r] if raw_stub_roots else []
        )
        raw_star = getattr(config, "star_import_policy", None) or "error"
        c.star_import_policy = str(raw_star)
        raw_missing = getattr(config, "impl_missing_annotation", None) or "warn"
        c.impl_missing_policy = str(raw_missing)

    @beartype
    def visit_module(self, node: nodes.Module) -> None:
        raw_file: str | None = getattr(node, "file", None)
        if not raw_file:
            return
        py_path = Path(raw_file).resolve()
        if py_path.suffix != ".py":
            return
        module_name: str = getattr(node, "name", "") or ""
        c = self._coverage
        c.current_file_path = py_path
        c.current_module_name = module_name if module_name else None

        if self._is_module_exempt(node, py_path, module_name):
            return

        self._index_module(node, py_path, module_name)

    @beartype
    def _is_module_exempt(
        self,
        node: nodes.Module,
        py_path: Path,
        module_name: str,
    ) -> bool:
        # ── conftest.py always exempt ─────────────────────────────────────
        if py_path.name == "conftest.py":
            log.info(
                "Exempt conftest.py",
                module=module_name,
                reason="always exempt from stub requirement",
            )
            return True

        # ── trivial test data modules (outside source root) exempt ────────
        if _is_trivial_test_data(node) and not _is_under_source_root(self, py_path):  # type: ignore[arg-type]  # Self@StubChecker is StubChecker at runtime  # ty:ignore[invalid-argument-type]
            log.info(
                "Exempt trivial test data module",
                module=module_name,
                reason="only literal assignments",
            )
            return True

        if (
            _is_test_file(self, py_path)  # type: ignore[arg-type]  # Self@StubChecker is StubChecker at runtime  # ty:ignore[invalid-argument-type]
            or not _is_under_source_root(self, py_path)  # type: ignore[arg-type]  # Self@StubChecker is StubChecker at runtime  # ty:ignore[invalid-argument-type]
            or _is_opted_out(self, py_path)  # type: ignore[arg-type]  # Self@StubChecker is StubChecker at runtime  # ty:ignore[invalid-argument-type]
        ):
            return True
        if not module_name:
            return True

        # ── __init__.py exemption ─────────────────────────────────────────
        if py_path.name == "__init__.py" and _is_init_exempt(node):
            log.info(
                "Exempt __init__.py", module=module_name, reason="imports/__all__ only"
            )
            return True

        return False

    @beartype
    def _index_module(
        self,
        node: nodes.Module,
        py_path: Path,
        module_name: str,
    ) -> None:
        c = self._coverage
        # Track modules with __main__ blocks for post-processing in close().
        if _has_main_block(node):
            c.main_module_candidates.add(module_name)

        c.module_index[module_name] = (py_path, node)
        c.production_count += 1
        stub_path = _resolve_stub(self, py_path)  # type: ignore[arg-type]  # Self@StubChecker is StubChecker at runtime  # ty:ignore[invalid-argument-type]
        if stub_path:
            c.stub_index[module_name] = stub_path
            c.stub_found_count += 1
            _index_stub_declarations(self, module_name, stub_path)  # type: ignore[arg-type]  # Self@StubChecker is StubChecker at runtime  # ty:ignore[invalid-argument-type]
        else:
            c.stub_missing.add(module_name)
        self._index_impl_annotations(module_name, node)

    @beartype
    def visit_import(self, node: nodes.Import) -> None:
        c = self._coverage
        if c.current_module_name is None or c.current_module_name not in c.module_index:
            return
        if _in_type_checking_block(node):
            return
        for alias in node.names:
            name, asname = (
                alias if isinstance(alias, tuple) else (alias.name, alias.asname)
            )
            c.import_usages.append(
                ImportUsage(
                    importer_module=c.current_module_name,
                    lineno=node.lineno or 0,
                    target_module=name,
                    symbol_name=None,
                    alias=asname,
                    is_star=False,
                )
            )

    @beartype
    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        c = self._coverage
        if c.current_module_name is None or c.current_module_name not in c.module_index:
            return
        if _in_type_checking_block(node):
            return
        is_package = (
            c.current_file_path is not None
            and c.current_file_path.name == "__init__.py"
        )
        level = node.level or 0
        target_module = _resolve_relative(
            c.current_module_name,
            level,
            node.modname,
            is_package=is_package,
        )
        for alias in node.names:
            name, asname = (
                alias if isinstance(alias, tuple) else (alias.name, alias.asname)
            )
            is_star = name == "*"
            c.import_usages.append(
                ImportUsage(
                    importer_module=c.current_module_name,
                    lineno=node.fromlineno or 0,
                    target_module=target_module,
                    symbol_name=None if is_star else name,
                    alias=asname,
                    is_star=is_star,
                )
            )

    @beartype
    def close(self) -> None:
        c = self._coverage
        # For each main-module candidate, check if any import_usages target it.
        # If none do, it's a standalone script — exempt from stub requirement.
        imported_modules: set[str] = set()
        for usage in c.import_usages:
            imported_modules.add(usage.target_module)
        for mod_name in list(c.main_module_candidates):
            if mod_name not in imported_modules and mod_name in c.stub_missing:
                c.stub_missing.discard(mod_name)
                c.production_count -= 1  # standalone script exempt — keep counts honest
                log.info(
                    "Exempt standalone script",
                    module=mod_name,
                    reason="not imported",
                )

        emit_coverage_violations(self)  # type: ignore[arg-type]  # Self@StubChecker is StubChecker at runtime  # ty:ignore[invalid-argument-type]
        emit_import_contract_violations(self)  # type: ignore[arg-type]  # Self@StubChecker is StubChecker at runtime  # ty:ignore[invalid-argument-type]
        emit_fidelity_violations(self)  # type: ignore[arg-type]  # Self@StubChecker is StubChecker at runtime  # ty:ignore[invalid-argument-type]

        log.info(
            "StubChecker summary",
            production_count=c.production_count,
            stub_found_count=c.stub_found_count,
            violations=len(c.stub_missing),
        )

    def _index_impl_annotations(
        self,
        module_name: str,
        py_node: nodes.Module,
    ) -> None:
        f = self._fidelity
        impl_ann: dict[str, tuple[nodes.NodeNG | None, nodes.AnnAssign | None]] = {}
        impl_callables: dict[str, nodes.FunctionDef | nodes.AsyncFunctionDef] = {}
        impl_classes: dict[str, nodes.ClassDef] = {}
        impl_names: set[str] = set()

        for child in py_node.body:
            if isinstance(child, nodes.AnnAssign) and isinstance(
                child.target, nodes.AssignName
            ):
                impl_ann[child.target.name] = (child.annotation, child)
                impl_names.add(child.target.name)
            elif isinstance(child, (nodes.FunctionDef, nodes.AsyncFunctionDef)):
                impl_callables[child.name] = child
                impl_names.add(child.name)
            elif isinstance(child, nodes.ClassDef):
                impl_classes[child.name] = child
                impl_names.add(child.name)
            elif isinstance(child, nodes.Assign):
                for t in child.targets:
                    if isinstance(t, nodes.AssignName):
                        impl_ann[t.name] = (None, child)  # type: ignore[assignment]  # dict value type is wider at runtime  # ty:ignore[invalid-assignment]
                        impl_names.add(t.name)

        f.impl_annotations[module_name] = impl_ann  # type: ignore[assignment]  # dict value type is wider at runtime  # ty:ignore[invalid-assignment]
        f.impl_callable_nodes[module_name] = impl_callables
        f.impl_class_nodes[module_name] = impl_classes
        f.impl_all_names[module_name] = impl_names


def register(linter: PyLinter) -> None:  # pylint: disable=missing-beartype  # circular import — PyLinter not available at runtime
    # beartype omitted: register is a pylint plugin entrypoint called from
    # pyproject.toml; beartype would introduce a circular import at load time.
    linter.register_checker(StubChecker(linter))
