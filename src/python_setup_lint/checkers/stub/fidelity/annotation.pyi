"""Variable + class annotation fidelity (Invariant 3 — the E97B4/W97B5/I97B6 family) — stub.

See ``annotation.py`` for full docstrings.
"""

from typing import TYPE_CHECKING

from astroid import nodes

from ._ast_helpers import ClassComparisonCtx

if TYPE_CHECKING:
    from python_setup_lint.checkers.stub.checker import StubChecker

def _normalize_bases(bases: list[nodes.NodeNG]) -> list[str]:
    """Strips module prefix from ``Attribute`` nodes (e.g. ``pydantic.BaseModel``
    to ``BaseModel``). Treats ``builtins.object`` as ``object``. For subscript
    nodes (e.g. ``Generic[T]``), extracts the base name (``Generic``).
    Sorts the result. Returns an empty list for empty bases.
    """

def _is_public_method(member_name: str) -> bool:
    """Check if *member_name* is a public method for class comparison.

    Includes:
    - Public methods (no leading underscore).
    - ``__init__`` and ``__new__`` (special methods with public semantics).
    Excludes:
    - Private methods (leading ``_`` but not ``__``).
    - Dunder methods other than ``__init__``/``__new__`` (e.g. ``__str__``, ``__repr__``).
    - Class-level attributes (handled separately via variable comparison).
    """

def _is_classvar(ann_node: nodes.NodeNG) -> bool:
    """Check if *ann_node* has ``ClassVar`` as its base type.

    Detects ``ClassVar[...]`` via AST structure (Subscript with Name('ClassVar')).
    """

def _compare_class_bases(ctx: ClassComparisonCtx) -> None:
    """Compare base classes between stub and impl classes.

    Emits E97B4 when normalized base lists differ.
    """

def _compare_class_methods(ctx: ClassComparisonCtx) -> None:
    """Compare public methods between stub and impl class bodies.

    Delegates to ``_emit_callable_fidelity_issues`` for each method pair.
    """

def _compare_class_attrs(ctx: ClassComparisonCtx) -> None:
    """Compare class-level annotated attributes between stub and impl.

    Emits W97B5, E97B4, or I97B6 for each attribute comparison.
    Skips ClassVar-annotated attributes.
    """

def _build_attr_index(
    ctx: ClassComparisonCtx,
) -> tuple[
    dict[str, nodes.AnnAssign],
    dict[str, tuple[nodes.NodeNG | None, nodes.AnnAssign | nodes.Assign | None]],
]:
    """Build stub and impl attribute indexes for a class."""

def _check_one_variable(
    checker: StubChecker,
    module_name: str,
    var_name: str,
    stub_ann_node: nodes.AnnAssign,
    *,
    impl_vars: dict[
        str, tuple[nodes.NodeNG | None, nodes.NodeNG | None]
    ],
    impl_node: nodes.Module,
    impl_missing_policy: str,
) -> None:
    """Check annotation fidelity for a single variable."""

def _emit_variable_fidelity(checker: StubChecker, module_name: str) -> None:
    """Compare variable annotations between stub and impl for *module_name*.

    Only compares variables PRESENT in both stub and impl.
    Variables absent from impl are caught by E97B1/E97B2 dispatch.
    """
