"""Parametrize rows for ``NoTryImportChecker`` tests.

Split by checker domain out of the former 1393-line ``_factories.py`` (pylint
C0302). Paired with ``tests/checkers/test_no_try_import_checker.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from _pytest.mark.structures import ParameterSet

_p = pytest.param


# ── no-try-import checker ──

_NO_TRY_DETECT_CASES: list[ParameterSet] = [
    _p(
        "try:\n    import litellm\nexcept ImportError:\n    pass\n",
        1,
        ("ImportError",),
        id="import_in_try_except_importerror",
    ),
    _p(
        "try:\n    import litellm\nexcept ModuleNotFoundError:\n    pass\n",
        1,
        (),
        id="import_in_try_except_modulenotfound",
    ),
    _p(
        "try:\n    from pydantic import ValidationError\nexcept ImportError:\n    pass\n",
        1,
        (),
        id="from_import_in_try_except_importerror",
    ),
    _p(
        "try:\n    import httpx\nexcept:\n    pass\n",
        1,
        ("bare except",),
        id="import_in_try_bare_except",
    ),
    _p(
        "try:\n    import litellm\nexcept (ImportError, ModuleNotFoundError):\n    pass\n",
        1,
        (),
        id="import_in_try_tuple_import_errors",
    ),
    _p(
        "try:\n    import litellm\nexcept ImportError:\n    pass\n\ntry:\n    import httpx\nexcept ImportError:\n    pass\n",
        2,
        (),
        id="two_imports_separate_try_blocks",
    ),
    _p(
        "try:\n    import litellm\nexcept ImportError:\n    pass\nexcept ModuleNotFoundError:\n    pass\n",
        2,
        (),
        id="two_imports_separate_handlers_one_try",
    ),
    _p(
        "try:\n    import litellm\nexcept ValueError:\n    pass\n",
        0,
        (),
        id="import_in_try_non_import_handler_not_flagged",
    ),
    _p(
        "try:\n    import httpx\nexcept ValueError:\n    pass\nexcept ImportError:\n    pass\nexcept OSError:\n    pass\n",
        1,
        (),
        id="handler_mixed_import_and_non_import",
    ),
    _p(
        "try:\n    import litellm as _litellm\nexcept ImportError:\n    _litellm = None\n",
        1,
        (),
        id="proxy_module_level_guard",
    ),
]

_NO_TRY_DO_NOT_DETECT_CASES: list[ParameterSet] = [
    _p(
        "try:\n    x = 1 / 0\nexcept ZeroDivisionError:\n    pass\n",
        id="try_without_import",
    ),
    _p("import os\nx = os.path.join('a', 'b')\n", id="import_outside_try"),
    _p("", id="empty_module"),
    _p(
        "try:\n    result = api_call()\nexcept ConnectionError:\n    result = None\n",
        id="non_import_exception_handling",
    ),
]
