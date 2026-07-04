# Task: Regenerate proof artifacts and verify both repos

## Plan reference
Read `~/aiexp/python-setup/scratchpad/plan2.md` lines 57-58 (M6 section), lines 72-78 (V&V section).

## What to do

### Part A: Run `uv run lint` in python-setup
1. Run `cd ~/aiexp/python-setup && uv run lint` and capture output
2. Assert:
   - No symbols-array dump (no long JSON symbol listings in terminal output)
   - No `missingFunctionDocStringCount` line
   - No ty `Unknown rule` warning
   - No tach `No first-party imports` warning
   - All tools PASSED
3. Redirect output to `scratchpad/lint.out.txt` (overwrite the stale one)

### Part B: Run `uv run lint` in consultant.mcp
1. Run `cd ~/aiexp/consultant.mcp && uv run lint`
2. Assert exit code 0
3. Confirm it passes against regenerated baseline

### Part C: Run tests
1. Run `cd ~/aiexp/python-setup && pytest tests/runner/test_parsers_hypothesis.py tests/runner/test_t3_coverage.py` — should be green

### Part D: Run `tach check`
1. Run `cd ~/aiexp/python-setup && tach check` — should show no "No first-party imports" warning

### Part E: Run `grep -rn no-fail-fast` on both repos
1. `cd ~/aiexp/python-setup && grep -rn 'no-fail-fast' .` — should return no hits
2. `cd ~/aiexp/consultant.mcp && grep -rn 'no-fail-fast' .` — should return no hits

### Part F: Run `uv run ty check`
1. Run `cd ~/aiexp/python-setup && uv run ty check` — should report "All checks passed!" with zero diagnostics

## Report
Report all results verbatim — what passed, what failed, any unexpected output.

## Constraints
- This is verification only — do NOT make code changes
- If something fails, report it clearly — don't try to fix it
- The `scratchpad/lint.out.txt` artifact is the record of proof
