"""Guard test: runner package surface exposes no private symbols.

The lint gate owns static import-hygiene checks (source scans, AST rules);
this asserts the runtime public surface only — ``runner.__all__`` must not
contain names starting with ``_``.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.no_external_api


def test_runner_imports_given_runner_all_then_no_private_symbols() -> None:
    """``python_setup_lint.runner.__all__`` MUST NOT contain ``_``-prefixed names."""
    import python_setup_lint.runner as runner_pkg

    private_in_all = [n for n in runner_pkg.__all__ if n.startswith("_")]
    assert not private_in_all, f"runner.__all__ contains private symbol(s): {private_in_all}"
