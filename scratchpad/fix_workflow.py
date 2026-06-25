#!/usr/bin/env python3
"""
Workflow: fix lint violations file by file, sequentially.

For each .py file (and companion .pyi if applicable):
1. Launch a task agent to fix all non-size violations
2. The agent runs ruff check --fix, ruff format, and relevant tests
3. If tests fail, the agent rolls back with git checkout
4. We verify the result and move to the next file
"""

import subprocess
import sys
import os
import json
import time
from pathlib import Path

ROOT = Path.home() / "aiexp/python-setup"
os.chdir(ROOT)

# All .py files to process
PY_FILES = [
    "src/python_setup_lint/__init__.py",
    "src/python_setup_lint/_setup_precommit.py",
    "src/python_setup_lint/checkers/__init__.py",
    "src/python_setup_lint/checkers/asyncio_timeout_checker.py",
    "src/python_setup_lint/checkers/beartype_checker.py",
    "src/python_setup_lint/checkers/no_try_import_checker.py",
    "src/python_setup_lint/checkers/stub_checker.py",
    "src/python_setup_lint/checkers/stub_coverage.py",
    "src/python_setup_lint/checkers/stub_docstring_checker.py",
    "src/python_setup_lint/checkers/stub_fidelity/__init__.py",
    "src/python_setup_lint/checkers/stub_fidelity/_ast_helpers.py",
    "src/python_setup_lint/checkers/stub_fidelity/annotation.py",
    "src/python_setup_lint/checkers/stub_fidelity/kind.py",
    "src/python_setup_lint/checkers/stub_fidelity/orchestrator.py",
    "src/python_setup_lint/checkers/stub_fidelity/signature.py",
    "src/python_setup_lint/checkers/stub_import_contract.py",
    "src/python_setup_lint/checkers/stub_normalizer.py",
    "src/python_setup_lint/checkers/tmp_path_checker.py",
    "src/python_setup_lint/runner/__init__.py",
    "src/python_setup_lint/runner/__main__.py",
    "src/python_setup_lint/runner/baseline.py",
    "src/python_setup_lint/runner/cli.py",
    "src/python_setup_lint/runner/cmd_build.py",
    "src/python_setup_lint/runner/dispatch.py",
    "src/python_setup_lint/runner/extra_tools.py",
    "src/python_setup_lint/runner/output.py",
    "src/python_setup_lint/runner/parsers.py",
    "src/python_setup_lint/runner/types.py",
    "src/python_setup_lint/setup.py",
    "src/python_setup_lint/testing.py",
    "tests/__init__.py",
    "tests/checkers/_factories.py",
    "tests/checkers/test_asyncio_timeout_checker.py",
    "tests/checkers/test_beartype_checker.py",
    "tests/checkers/test_no_try_import_checker.py",
    "tests/checkers/test_stub_checker.py",
    "tests/checkers/test_stub_checker_callable.py",
    "tests/checkers/test_stub_checker_class.py",
    "tests/checkers/test_stub_coverage.py",
    "tests/checkers/test_stub_docstring_checker.py",
    "tests/checkers/test_stub_fidelity_invariants.py",
    "tests/checkers/test_stub_normalizer.py",
    "tests/checkers/test_tmp_path_checker.py",
    "tests/conftest.py",
    "tests/runner/__init__.py",
    "tests/runner/_factories.py",
    "tests/runner/test_autofix_conflict.py",
    "tests/runner/test_baseline_diff.py",
    "tests/runner/test_bench_runner_overhead.py",
    "tests/runner/test_extra_tools.py",
    "tests/runner/test_lint_runner.py",
    "tests/runner/test_real_pipeline_smoke.py",
    "tests/runner/test_setup.py",
    "tests/runner/test_t11_health_checks.py",
    "tests/runner/test_t1b_self_discovery.py",
    "tests/runner/test_t3_coverage.py",
    "tests/runner/test_t5_compose_ruff.py",
    "tests/runner/test_t9_7_compose_pyright.py",
    "tests/runner/test_testing_fakes.py",
]


def has_pyi(py_path: str) -> bool:
    return Path(py_path + "i").exists()


def test_file_for(py_path: str) -> str | None:
    p = Path(py_path)
    if p.name.startswith("test_"):
        return None
    if str(p).startswith("src/"):
        rel = p.relative_to("src/python_setup_lint")
        test_path = ROOT / "tests" / rel.parent / f"test_{rel.name}"
        if test_path.exists():
            return str(test_path)
        test_path2 = ROOT / "tests" / rel.parent / f"test_{rel.stem}.py"
        if test_path2.exists():
            return str(test_path2)
    return None


def build_assignment(py_path: str) -> str:
    """Build the task assignment for a given .py file."""
    p = Path(py_path)
    has_pyi_file = has_pyi(py_path)
    test = test_file_for(py_path)

    lines = [
        f"# Fix all non-size lint violations in: {py_path}",
        "",
        f"## File: {py_path}",
    ]

    if has_pyi_file:
        lines.append(f"## Companion .pyi: {py_path}i")
        lines.append("IMPORTANT: If you modify the .pyi, you MUST keep it in sync with the .py.")

    if test:
        lines.append(f"## Test file: {test}")

    lines.extend([
        "",
        "## Instructions",
        "1. Read the file to understand its current state",
        "2. Run `uv run ruff check --fix {py_path}` to auto-fix import sorting and other auto-fixable issues",
        "3. Run `uv run ruff format {py_path}` to format",
        "4. Run `uv run ruff check {py_path}` to see remaining issues",
        "5. Fix ALL remaining non-size violations manually (see context for common fixes)",
        "6. After each fix, run `uv run ruff check --fix {py_path}` and `uv run ruff format {py_path}`",
        "7. If companion .pyi exists, also run `uv run ruff check --fix {py_path}i` and `uv run ruff format {py_path}i`",
        "8. Run the test: `uv run pytest -x -q -k {Path(test).stem if test else 'nonexistent'}`",
        "9. If tests fail, rollback with `git checkout -- {py_path}`" + (f" && `git checkout -- {py_path}i`" if has_pyi_file else ""),
        "10. Report what was fixed or why rollback happened",
        "",
        "## Size/complexity violations to IGNORE (do not fix)",
        "- SIM102 (nested if)",
        "- C0302 (too many lines)",
        "- R09* (too many branches/locals/returns/statements/arguments)",
        "- E97A0/E97A2 (missing module stub)",
        "- C0301 (line too long)",
        "- R0902/R0903 (too many/few instance attributes/public methods)",
        "- R0801 (duplicate code)",
        "- R0917 (too many positional arguments)",
        "",
        "## Verification",
        "After all changes, run:",
        f"  uv run ruff check --fix {py_path}",
        f"  uv run ruff format {py_path}",
        f"  uv run pytest -x -q -k {Path(test).stem if test else 'nonexistent'}",
    ])

    return "\n".join(lines)


def run_agent(py_path: str) -> dict:
    """Launch a task agent for one file and wait for result."""
    assignment = build_assignment(py_path)
    p = Path(py_path)
    agent_id = p.stem.replace("_", "").replace("-", "")[:28]

    # Write assignment to a temp file for the agent
    assignment_path = ROOT / f"scratchpad/agent_{agent_id}.md"
    assignment_path.write_text(assignment)

    print(f"\n{'='*60}")
    print(f"Launching agent for: {py_path}")
    print(f"Agent ID: {agent_id}")
    print(f"{'='*60}")

    # Use the task tool via subprocess - we'll use the eval mechanism
    # The agent will be launched from the main loop
    return {
        "file": py_path,
        "agent_id": agent_id,
        "assignment_path": str(assignment_path),
    }


def main():
    print(f"Starting workflow: {len(PY_FILES)} files to process")
    print(f"Root: {ROOT}")
    print()

    results = []

    for i, py_path in enumerate(PY_FILES):
        print(f"\n{'#'*60}")
        print(f"# File {i+1}/{len(PY_FILES)}: {py_path}")
        print(f"{'#'*60}")

        info = run_agent(py_path)
        results.append(info)

        # Print the assignment for the main loop to use
        print(f"\nASSIGNMENT_FOR:{py_path}")
        print(build_assignment(py_path))
        print(f"END_ASSIGNMENT:{py_path}")

    print(f"\n{'='*60}")
    print(f"All {len(PY_FILES)} files processed")
    print(f"{'='*60}")

    # Save results
    results_path = ROOT / "scratchpad/workflow_results.json"
    results_path.write_text(json.dumps(results, indent=2))
    print(f"Results saved to {results_path}")


if __name__ == "__main__":
    main()
