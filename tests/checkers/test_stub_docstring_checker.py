"""Unit tests for python_setup_lint.checkers.stub_docstring_checker.

Tests docstring detection logic and full pipeline with stub_checker.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import astroid

if TYPE_CHECKING:
    import pytest

from python_setup_lint.checkers.stub_docstring_checker import StubDocstringChecker
from python_setup_lint.testing import _make_tc as _make_tc_factory

_make_tc = lambda: _make_tc_factory(StubDocstringChecker)


def _walk_and_release(code: str, file_path: str = "/workspace/src/mod.py"):
    tc = _make_tc()
    module = astroid.parse(code)
    module.file = file_path
    tc.walk(module)
    return tc.linter.release_messages()


def _walk_both_release(code: str, py_path: Path, source_roots: list[str] | None = None):
    pyi_path = py_path.with_suffix(".pyi")
    pyi_path.parent.mkdir(parents=True, exist_ok=True)
    pyi_path.write_text("# stub\n")
    module_name = py_path.stem

    from pylint.testutils import UnittestLinter
    from pylint.utils import ASTWalker

    from python_setup_lint.checkers.stub_checker import StubChecker
    from python_setup_lint.checkers.stub_docstring_checker import StubDocstringChecker

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


class TestNoCompanionStub:
    """Checker emits nothing when no companion .pyi exists."""

    def test_no_companion_plain_func(self):
        msgs = _walk_and_release("def foo():\n    \"\"\"My docstring.\"\"\"\n    pass\n")
        assert len([m for m in msgs if m.msg_id == "docstring-in-impl"]) == 0

    def test_no_companion_async_func(self):
        msgs = _walk_and_release("async def foo():\n    \"\"\"My docstring.\"\"\"\n    pass\n")
        assert len([m for m in msgs if m.msg_id == "docstring-in-impl"]) == 0

    def test_no_companion_method(self):
        msgs = _walk_and_release("class MyClass:\n    def method(self):\n        \"\"\"Method doc.\"\"\"\n        pass\n")
        assert len([m for m in msgs if m.msg_id == "docstring-in-impl"]) == 0


class TestDoesNotDetect:
    """Checker does NOT emit W9700 in valid negative cases."""

    def test_no_docstring_no_message(self):
        msgs = _walk_and_release("def foo():\n    pass\n")
        assert len([m for m in msgs if m.msg_id == "docstring-in-impl"]) == 0

    def test_empty_body_no_message(self):
        msgs = _walk_and_release("def foo():\n    ...\n")
        assert len([m for m in msgs if m.msg_id == "docstring-in-impl"]) == 0

    def test_class_docstring_no_message(self):
        msgs = _walk_and_release("class MyClass:\n    \"\"\"Class-level docs.\"\"\"\n    pass\n")
        assert len([m for m in msgs if m.msg_id == "docstring-in-impl"]) == 0

    def test_non_string_first_expr(self):
        msgs = _walk_and_release("def foo():\n    42\n    pass\n")
        assert len([m for m in msgs if m.msg_id == "docstring-in-impl"]) == 0


class TestDetectsDocstringInImpl:
    """Checker emits W9700 when companion .pyi exists and .py has docstrings."""

    def test_function_docstring_detected(self, tmp_path: Path):
        py_path = tmp_path / "src" / "mod.py"
        py_path.parent.mkdir(exist_ok=True)
        msgs = _walk_both_release(
            code="def foo():\n    \"\"\"Usage docstring.\"\"\"\n    pass\n",
            py_path=py_path,
            source_roots=[str(tmp_path / "src")],
        )
        doc_msgs = [m for m in msgs if m.msg_id == "docstring-in-impl"]
        assert len(doc_msgs) == 1
        assert doc_msgs[0].args[1] == "foo"

    def test_async_function_docstring_detected(self, tmp_path: Path):
        py_path = tmp_path / "src" / "mod.py"
        py_path.parent.mkdir(exist_ok=True)
        msgs = _walk_both_release(
            code="async def foo():\n    \"\"\"Usage docstring.\"\"\"\n    pass\n",
            py_path=py_path,
            source_roots=[str(tmp_path / "src")],
        )
        doc_msgs = [m for m in msgs if m.msg_id == "docstring-in-impl"]
        assert len(doc_msgs) == 1

    def test_method_docstring_detected(self, tmp_path: Path):
        py_path = tmp_path / "src" / "mod.py"
        py_path.parent.mkdir(exist_ok=True)
        msgs = _walk_both_release(
            code="class MyClass:\n    def method(self):\n        \"\"\"Method doc.\"\"\"\n        pass\n",
            py_path=py_path,
            source_roots=[str(tmp_path / "src")],
        )
        doc_msgs = [m for m in msgs if m.msg_id == "docstring-in-impl"]
        assert len(doc_msgs) == 1
        assert doc_msgs[0].args[1] == "method"

    def test_mixed_docstrings_and_no_docstrings(self, tmp_path: Path):
        py_path = tmp_path / "src" / "mod.py"
        py_path.parent.mkdir(exist_ok=True)
        msgs = _walk_both_release(
            code="def foo():\n    \"\"\"Doc.\"\"\"\n    pass\n\ndef bar():\n    pass\n",
            py_path=py_path,
            source_roots=[str(tmp_path / "src")],
        )
        doc_msgs = [m for m in msgs if m.msg_id == "docstring-in-impl"]
        assert len(doc_msgs) == 1