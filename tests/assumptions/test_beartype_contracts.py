"""Pin beartype's handling of TYPE_CHECKING-only forward references.

Observed with beartype 0.22.9 (pinned in ``pyproject.toml``):

* module import and ``@beartype`` decoration succeed (no import-time failure);
* the first call raises ``BeartypeCallHintForwardRefException`` at call time,
  even when the argument is an instance of the intended runtime type;
* the outcome is therefore call-time, not import-time and not checker-only:
  ``@beartype`` silences the project's static ``missing-beartype`` rule but
  cannot enforce a signature whose name is imported only under ``TYPE_CHECKING``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from beartype.roar import BeartypeCallHintForwardRefException
from pylint.lint import PyLinter

pytestmark = pytest.mark.no_external_api

_FORWARD_REF_SOURCE = """from __future__ import annotations

from typing import TYPE_CHECKING

from beartype import beartype

if TYPE_CHECKING:
    from pylint.lint import PyLinter


@beartype
def accept(linter: PyLinter) -> None:
    return None
"""


class TestBeartypeContracts:
    """Contract from beartype that the checker decorator policy depends on."""

    def test_beartype_given_type_checking_only_forward_ref_then_first_call_raises_forward_ref_exception(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OBSERVED at beartype 0.22.9: import succeeds; calls raise at call time."""
        module_path = tmp_path / "forward_ref_module.py"
        module_path.write_text(_FORWARD_REF_SOURCE)
        module_name = "_beartype_forward_ref_contract"
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, module_name, module)

        spec.loader.exec_module(module)  # OBSERVED: decoration succeeds at import time

        assert callable(module.accept)
        with pytest.raises(BeartypeCallHintForwardRefException, match="PyLinter"):
            module.accept(None)
        # OBSERVED: name resolution fails before the argument value is checked,
        # so even an instance of the intended runtime type raises.
        with pytest.raises(BeartypeCallHintForwardRefException, match="PyLinter"):
            module.accept(PyLinter())
