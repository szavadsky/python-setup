"""Shared test-factory helpers for the python-setup checker test suite.

Split by checker domain out of the former 1393-line ``_factories.py`` (pylint
C0302). Domain modules:

- ``_factories_no_try_import`` — ``NoTryImportChecker`` rows
- ``_factories_beartype`` — ``BeartypeCoverageChecker`` rows
- ``_factories_stub`` — ``StubChecker`` core rows, walkers, state builders
- ``_factories_stub_callable`` — callable-fidelity rows
- ``_factories_stub_class`` — class-fidelity rows and walker
- ``_factories_stub_coverage`` — coverage rows and layout builders
- ``_factories_stub_docstring`` — ``StubDocstringChecker`` rows and walker
- ``_factories_stub_normalizer`` — ``AnnotationNormalizer`` rows

Only helpers shared by more than one domain live here. The former ``make_tc``
and ``import_usage`` passthroughs were deleted as unused wrappers; survivors
call ``_make_tc_factory`` or construct ``ImportUsage`` directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


# ── shared subprocess-integration helpers ──


def _run_pylint(
    tmp_path: Path,
    mod_py: str,
    mod_pyi: str,
    enable: str,
    /,
    *,
    project_src: Path,
) -> str:
    import os
    import subprocess
    import sys

    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "__init__.pyi").write_text("")
    (src / "mod_a.py").write_text(mod_py)
    (src / "mod_a.pyi").write_text(mod_pyi)
    (tmp_path / "pyproject.toml").write_text(
        f"""\
[tool.pylint.MASTER]
load-plugins = "python_setup_lint.checkers.stub.checker"

[tool.pylint.stub-checker]
source-roots = ["{src}"]
"""
    )
    env = {**os.environ, "PYTHONPATH": str(project_src)}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pylint",
            str(src),
            "--disable=all",
            f"--enable={enable}",
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
        check=False,
    )
    return result.stdout + result.stderr
