"""Phase 3 enforcement — stub-impl fidelity (Invariant 3).

Compares variable annotations, callable signatures, class structure,
and symbol presence/kind between .pyi stubs and .py implementations.

Public entrypoint: :func:`emit_fidelity_violations` (re-exported from
:mod:`.orchestrator`) — called from
:class:`~python_setup_lint.checkers.stub_checker.StubChecker.close` to
emit all Phase 3 violations for every module in the checker's
``stub_index``.

Package split (T10, G5 §2): the original 763-LOC
``checkers/stub_fidelity.py`` module was decomposed into cohesive
sub-modules, each ≤500 LOC + a ``.pyi`` companion:

- :mod:`._ast_helpers` — shared state types
  (``_FidelityState``, ``ParamDescriptor``, ``ClassComparisonCtx``,
  ``CallableComparisonCtx``).
- :mod:`.signature` — callable signature + param/return annotation
  compare → E97B3 / E97B4 / I97B6.
- :mod:`.annotation` — variable + class-base / class-method /
  class-attribute compare → E97B4 / W97B5 / I97B6.  Delegates
  class-method comparison to :mod:`.signature`.
- :mod:`.kind` — symbol presence check → E97B1 / E97B2. Delegates class
  comparison to :mod:`.annotation`.
- :mod:`.orchestrator` — :func:`emit_fidelity_violations` (top-level
  dispatcher: per-module ``kind`` → ``annotation`` → ``signature``).

This ``__init__`` re-exports the public surface AND the ``_``-prefixed
helpers that tests reach through the
``python_setup_lint.checkers.stub_fidelity`` import path, so external
imports (e.g. ``from python_setup_lint.checkers.stub_fidelity import
_is_classvar``) resolve unchanged after the T10 split.

Re-exports use redundant ``as`` aliases so ruff F401 treats them as
intentional re-exports.  CodingRules forbids ``import *``; this
``__init__.py`` is pure re-export (no logic) so no ``.pyi`` is required
per the CodingRules ``__init__.py`` exemption.
"""

from __future__ import annotations

from ._ast_helpers import CallableComparisonCtx as CallableComparisonCtx
from ._ast_helpers import ClassComparisonCtx as ClassComparisonCtx
from ._ast_helpers import ParamDescriptor as ParamDescriptor
from ._ast_helpers import _FidelityState as _FidelityState
from .annotation import _compare_class_attrs as _compare_class_attrs
from .annotation import _compare_class_bases as _compare_class_bases
from .annotation import _compare_class_methods as _compare_class_methods
from .annotation import _emit_variable_fidelity as _emit_variable_fidelity
from .annotation import _is_classvar as _is_classvar
from .annotation import _is_public_method as _is_public_method
from .annotation import _normalize_bases as _normalize_bases
from .kind import _emit_stub_symbol_check as _emit_stub_symbol_check
from .orchestrator import emit_fidelity_violations as emit_fidelity_violations
from .signature import _compare_callable_annotations as _compare_callable_annotations
from .signature import _compare_callable_descriptors as _compare_callable_descriptors
from .signature import _compare_return_annotations as _compare_return_annotations
from .signature import _emit_callable_fidelity as _emit_callable_fidelity
from .signature import _emit_callable_fidelity_issues as _emit_callable_fidelity_issues
from .signature import _extract_param_descriptors as _extract_param_descriptors

__all__ = [
    "CallableComparisonCtx",
    "ClassComparisonCtx",
    "ParamDescriptor",
    "_FidelityState",
    "_compare_callable_annotations",
    "_compare_callable_descriptors",
    "_compare_class_attrs",
    "_compare_class_bases",
    "_compare_class_methods",
    "_compare_return_annotations",
    "_emit_callable_fidelity",
    "_emit_callable_fidelity_issues",
    "_emit_stub_symbol_check",
    "_emit_variable_fidelity",
    "_extract_param_descriptors",
    "_is_classvar",
    "_is_public_method",
    "_normalize_bases",
    "emit_fidelity_violations",
]
