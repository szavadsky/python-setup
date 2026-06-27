"""Guard test: no ``_``-prefixed symbols imported through runner package surface.

Ensures that ``python_setup_lint.runner`` does not re-export any private
symbols (names starting with ``_``) in its ``__all__`` or module-level
namespace accessible via ``from python_setup_lint.runner import ...``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.no_external_api
_RUNNER_PKG = "python_setup_lint.runner"



def _get_public_names(module: Any) -> set[str]:
    """Return the set of names exported by *module* via ``__all__`` or dir()."""
    if hasattr(module, "__all__"):
        return set(module.__all__)
    return {n for n in dir(module) if not n.startswith("_")}


def test_runner_imports_given_runner_all_then_no_private_symbols() -> None:
    """``python_setup_lint.runner.__all__`` MUST NOT contain ``_``-prefixed names."""
    import python_setup_lint.runner as runner_pkg

    if not hasattr(runner_pkg, "__all__"):
        pytest.skip("runner package has no __all__")

    private_in_all = [n for n in runner_pkg.__all__ if n.startswith("_")]
    assert not private_in_all, (
        f"runner.__all__ contains private symbol(s): {private_in_all}"
    )


def test_runner_imports_given_runner_namespace_then_no_private_symbols() -> None:
    """``from python_setup_lint.runner import *`` MUST NOT expose private names."""
    import python_setup_lint.runner as runner_pkg

    public = _get_public_names(runner_pkg)
    private = {n for n in public if n.startswith("_")}
    assert not private, (
        f"runner package exposes private symbol(s): {private}"
    )


def test_runner_imports_given_init_then_no_private_submodule() -> None:
    """Runner ``__init__`` MUST NOT import ``_``-prefixed submodules."""
    import python_setup_lint.runner as runner_pkg

    init_path = Path(runner_pkg.__file__)  # type: ignore[arg-type]
    init_text = init_path.read_text()

    # Check for imports of private submodules
    import re

    private_imports = re.findall(
        r"^\s*from\s+\.(_[a-zA-Z]\w*)\s+import\s",
        init_text,
        re.MULTILINE,
    )
    private_imports += re.findall(
        r"^\s*import\s+\.(_[a-zA-Z]\w*)",
        init_text,
        re.MULTILINE,
    )
    assert not private_imports, (
        f"runner __init__ imports private submodule(s): {private_imports}"
    )



def test_tests_import_privates_only_from_defining_submodule() -> None:
    """Tests MUST import ``_``-prefixed symbols from the defining submodule,
    not through the package ``__init__``."""
    import ast

    tests_dir = Path(__file__).resolve().parent.parent
    violations: list[str] = []

    for pyfile in sorted(tests_dir.rglob("*.py")):
        if pyfile.name == "__init__.py":
            continue
        tree = ast.parse(pyfile.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.module is None:
                continue
            # Check imports from the runner package root (not a submodule)
            if node.module == "python_setup_lint.runner":
                for alias in node.names:
                    if alias.name.startswith("_"):
                        rel = pyfile.relative_to(tests_dir)
                        violations.append(
                            f"{rel}: from python_setup_lint.runner import {alias.name}"
                        )

    assert not violations, (
        "Tests import _-prefixed symbols from runner package root, "
        "not the defining submodule:\n" + "\n".join(violations)
    )
