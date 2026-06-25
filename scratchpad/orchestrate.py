#!/usr/bin/env python3
"""
Mechanical orchestration: for each file with violations, spawn a fix agent,
then a check agent, then commit or rollback.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path.home() / "aiexp/python-setup"
os.chdir(ROOT)

# Load violation list
violations_path = Path.home() / ".omp/agent/sessions/-aiexp-python-setup/2026-06-25T12-18-01-602Z_019efeb7-3b02-7000-8dbd-40ee4b42592b/local/violation_list.json"
with open(violations_path) as f:
    files = json.load(f)

# Common fix patterns for each violation type
FIX_PATTERNS = {
    "I001": "Fix import ordering with `uv run ruff check --fix --select I001 {file}`",
    "C0413": "Move imports to top of file (before any non-import code)",
    "C0412": "Group imports: stdlib first, then third-party, then local",
    "RUF022": "Sort __all__ entries alphabetically",
    "RUF100": "Remove unused `# noqa` comments",
    "TC001": "Move TYPE_CHECKING-only imports inside TYPE_CHECKING block",
    "TC002": "Move TYPE_CHECKING-only imports inside TYPE_CHECKING block, add `# noqa: TC002` if needed at runtime",
    "TC003": "Move TYPE_CHECKING-only imports inside TYPE_CHECKING block",
    "TC004": "Move TYPE_CHECKING-only imports inside TYPE_CHECKING block",
    "W9700": "Add `# pylint: disable=docstring-in-impl` with technical justification, or move docstring to .pyi",
    "W9701": "Add `# pylint: disable=missing-beartype` with technical justification (circular import or type not available at runtime)",
    "W97B5": "Add type annotation to the function/variable",
    "E97B3": "Fix signature mismatch between .py and .pyi (param count, names, defaults)",
    "E97B4": "Fix annotation mismatch between .py and .pyi",
    "ARG002": "Prefix unused parameter with `_` or use `del param`",
    "S603": "Use `subprocess.run` with explicit args list instead of shell=True",
    "S607": "Use full path for executable in subprocess.run",
    "PT006": "Use `@pytest.mark.parametrize` with the correct argument style (list of tuples)",
    "SIM108": "Use ternary expression instead of if-else assignment",
    "PERF401": "Use a list comprehension instead of for-loop append",
    "PYI034": "Fix type annotation in .pyi stub",
    "type-arg": "Add type argument to generic type (e.g., dict -> dict[str, Any])",
    "arg-type": "Fix argument type annotation",
    "call-arg": "Fix call argument",
    "no-untyped-def": "Add type annotations to function definition",
    "no-any-return": "Add explicit return type annotation",
    "no-matching-overload": "Fix overload signature to match implementation",
    "unused-ignore": "Remove unused `# type: ignore` comments",
    "unresolved-import": "Fix import path or add missing dependency",
    "unknown-argument": "Fix unknown argument in function call",
    "invalid-argument-type": "Fix invalid argument type",
    "invalid-assignment": "Fix invalid assignment type",
    "invalid-return-type": "Fix invalid return type",
    "invalid-attribute-override": "Fix attribute override in subclass",
    "not-subscriptable": "Fix type that is not subscriptable",
    "unsupported-operator": "Fix unsupported operator usage",
    "index": "Fix index type",
    "too-many-positional-arguments": "Reduce positional arguments or use keyword args",
    "misc": "Fix miscellaneous type error",
}

def build_fix_assignment(entry):
    """Build a fix assignment for a single file."""
    file = entry["file"]
    violations = entry["violations"]
    pyi = entry.get("pyi")
    test = entry.get("test")

    lines = [
        f"## Target\nFix all lint violations in {file}",
        "",
        "## Violations to fix",
    ]
    for v in violations:
        pattern = FIX_PATTERNS.get(v, f"Fix {v} violation")
        lines.append(f"- **{v}**: {pattern.format(file=file)}")
    
    if pyi:
        lines.append(f"\nAlso update companion .pyi stub at {pyi} if needed (signature/annotation must match)")
    
    lines.append("")
    lines.append("## Change")
    lines.append(f"1. Read {file} to understand current state")
    if pyi:
        lines.append(f"2. Read {pyi} to understand current stub")
    lines.append(f"3. Fix all violations listed above")
    lines.append(f"4. Run `uv run ruff check --fix {file}`")
    if pyi:
        lines.append(f"5. Run `uv run ruff check --fix {pyi}`")
    lines.append(f"6. Run `uv run ruff format {file}`")
    if pyi:
        lines.append(f"7. Run `uv run ruff format {pyi}`")
    lines.append("")
    lines.append("## Acceptance")
    lines.append(f"- All violations listed above are fixed in {file}")
    if pyi:
        lines.append(f"- Companion .pyi stub at {pyi} is consistent with the .py file")
    lines.append("- Ruff check passes on the file(s)")
    lines.append("- Do NOT run tests or full lint pipeline - just fix the file")
    
    return "\n".join(lines)


def build_check_assignment(entry):
    """Build a check assignment for a single file."""
    file = entry["file"]
    test = entry.get("test")
    
    lines = [
        f"## Target\nVerify that fixes to {file} don't cause regressions",
        "",
        "## Change",
        f"1. Run `uv run ruff check {file}` to verify no ruff violations remain",
        f"2. Run `uv run lint --no-fail-fast --path {file}` to verify no lint regressions",
    ]
    if test:
        lines.append(f"3. Run `uv run pytest -x -q -k \"{Path(test).stem.replace('test_', '')}\" tests/` to verify tests pass")
    else:
        # Try to find a relevant test
        lines.append(f"3. Run `uv run pytest -x -q` to verify all tests pass")
    
    lines.append("")
    lines.append("## Acceptance")
    lines.append(f"- Ruff check passes on {file}")
    lines.append(f"- Lint pipeline shows no regressions on {file}")
    lines.append("- All relevant tests pass")
    lines.append("- If any check fails, rollback with `git checkout -- {file}`")
    if entry.get("pyi"):
        lines.append(f"- If any check fails, also rollback with `git checkout -- {entry['pyi']}`")
    
    return "\n".join(lines)


def main():
    print(f"Processing {len(files)} files with violations...")
    
    for i, entry in enumerate(files):
        file = entry["file"]
        print(f"\n{'='*60}")
        print(f"[{i+1}/{len(files)}] Processing: {file}")
        print(f"  Violations: {', '.join(entry['violations'])}")
        print(f"{'='*60}")
        
        # Step 1: Fix the file
        fix_assignment = build_fix_assignment(entry)
        print(f"\n  Fix assignment prepared ({len(fix_assignment)} chars)")
        
        # Step 2: Check the fix
        check_assignment = build_check_assignment(entry)
        print(f"  Check assignment prepared ({len(check_assignment)} chars)")
        
        # Save assignments for task agents
        fix_path = ROOT / f".fix_{i}_{Path(file).name.replace('.', '_')}.txt"
        check_path = ROOT / f".check_{i}_{Path(file).name.replace('.', '_')}.txt"
        
        with open(fix_path, "w") as f:
            f.write(fix_assignment)
        with open(check_path, "w") as f:
            f.write(check_assignment)
        
        print(f"  Saved fix assignment to {fix_path.name}")
        print(f"  Saved check assignment to {check_path.name}")
    
    print(f"\n{'='*60}")
    print(f"All {len(files)} assignments prepared.")
    print(f"Run them sequentially with task agents.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
