"""Parametrize rows and walker for ``StubDocstringChecker`` tests.

Split by checker domain out of the former 1393-line ``_factories.py`` (pylint
C0302). Paired with ``tests/checkers/test_stub_docstring_checker.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import astroid
import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.mark.structures import ParameterSet

_p = pytest.param


# ── stub docstring checker ──

_DOCSTRING_NO_COMPANION_CASES: list[ParameterSet] = [
    _p(
        'def foo():\n    """My docstring."""\n    pass\n',
        0,
        id="no_companion_plain_func",
    ),
    _p(
        'async def foo():\n    """My docstring."""\n    pass\n',
        0,
        id="no_companion_async_func",
    ),
    _p(
        'class MyClass:\n    def method(self):\n        """Method doc."""\n        pass\n',
        0,
        id="no_companion_method",
    ),
]

_DOCSTRING_DOES_NOT_DETECT_CASES: list[ParameterSet] = [
    _p("def foo():\n    pass\n", id="no_docstring_no_message"),
    _p("def foo():\n    ...\n", id="empty_body_no_message"),
    _p(
        'class MyClass:\n    """Class-level docs."""\n    pass\n',
        id="class_docstring_no_message",
    ),
    _p("def foo():\n    42\n    pass\n", id="non_string_first_expr"),
]

_DOCSTRING_DETECT_CASES: list[ParameterSet] = [
    _p(
        'def foo():\n    """Usage docstring."""\n    pass\n',
        1,
        "foo",
        id="function_docstring_detected",
    ),
    _p(
        'async def foo():\n    """Usage docstring."""\n    pass\n',
        1,
        None,
        id="async_function_docstring_detected",
    ),
    _p(
        'class MyClass:\n    def method(self):\n        """Method doc."""\n        pass\n',
        1,
        "method",
        id="method_docstring_detected",
    ),
    _p(
        'def foo():\n    """Doc."""\n    pass\n\ndef bar():\n    pass\n',
        1,
        None,
        id="mixed_docstrings_and_no_docstrings",
    ),
]

_DOCSTRING_RETURNS_DETECT_CASES: list[ParameterSet] = [
    _p(
        'def f() -> int:\n    """Do something."""\n    return 1\n',
        1,
        id="generic_int_fires",
    ),
    _p(
        'def f() -> str:\n    """Do something."""\n    return "x"\n',
        1,
        id="generic_str_fires",
    ),
    _p(
        'def f() -> bool:\n    """Do something."""\n    return True\n',
        1,
        id="generic_bool_fires",
    ),
    _p(
        'def f() -> dict[str, int]:\n    """Do something."""\n    return {}\n',
        1,
        id="generic_dict_str_fires",
    ),
    _p(
        'def f() -> dict[int, str]:\n    """Do something."""\n    return {}\n',
        1,
        id="generic_dict_int_fires",
    ),
]

_DOCSTRING_RETURNS_DO_NOT_DETECT_CASES: list[ParameterSet] = [
    _p(
        'def f() -> UserId:\n    """Do something."""\n    return UserId(1)\n',
        id="named_alias_skips",
    ),
    _p(
        'def _helper() -> int:\n    """Do something."""\n    return 1\n',
        id="underscore_prefixed_skips",
    ),
    _p(
        'def f() -> None:\n    """Do something."""\n    pass\n',
        id="none_return_skips",
    ),
    _p(
        "def f() -> int:\n    pass\n",
        id="no_docstring_skips",
    ),
    _p(
        'def f() -> int:\n    """Do something.\n\n    Returns:\n        The answer.\n    """\n    return 42\n',
        id="has_returns_clause_skips",
    ),
    _p(
        'def f() -> int:\n    """Do something.\n\n    Yields:\n        Items.\n    """\n    yield 1\n',
        id="has_yields_clause_skips",
    ),
    _p(
        'def f() -> Self:\n    """Do something."""\n    return self\n',
        id="self_return_skips",
    ),
    _p(
        'def f() -> NoReturn:\n    """Do something."""\n    sys.exit(1)\n',
        id="noreturn_skips",
    ),
    _p(
        'def f() -> MyClass:\n    """Do something."""\n    return MyClass()\n',
        id="custom_class_skips",
    ),
]


# ── stub_docstring: shared walker ──


def walk_both_release_for_pyi(
    code: str,
    py_path: Path,
    source_roots: list[str] | None = None,
) -> list[Any]:
    from pylint.testutils import UnittestLinter
    from pylint.utils import ASTWalker

    from python_setup_lint.checkers.stub.checker import StubChecker
    from python_setup_lint.checkers.stub.docstring_checker import StubDocstringChecker

    pyi_path = py_path.with_suffix(".pyi")
    pyi_path.parent.mkdir(parents=True, exist_ok=True)
    pyi_path.write_text("# stub\n")
    module_name = py_path.stem
    linter = UnittestLinter()
    stub = StubChecker(linter)
    stub_doc = StubDocstringChecker(linter)
    linter.register_checker(stub_doc)
    if source_roots:
        linter.config.source_roots = source_roots
    stub.open()
    module = astroid.parse(code, module_name=module_name)
    module.file = str(py_path)
    walker = ASTWalker(linter)
    walker.add_checker(stub)
    walker.add_checker(stub_doc)
    walker.walk(module)
    return linter.release_messages()
