"""Phase 3 enforcement — stub-impl fidelity (Invariant 3).

Public surface: :func:`emit_fidelity_violations`,
:class:`CallableComparisonCtx`, :class:`ClassComparisonCtx`,
:class:`ParamDescriptor`.
"""

from ._ast_helpers import CallableComparisonCtx, ClassComparisonCtx, ParamDescriptor
from .orchestrator import emit_fidelity_violations

__all__ = [
    "CallableComparisonCtx",
    "ClassComparisonCtx",
    "ParamDescriptor",
    "emit_fidelity_violations",
]
