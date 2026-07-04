# Task: Strip pyright verifytypes docstring/default-param noise from runner summary

## Plan reference
Read `~/aiexp/python-setup/scratchpad/plan2.md` lines 53-54 (M2 section), lines 23-24 (surface direction), lines 45-46 (test coverage), lines 12-13 (pyright direction).

## What to do

1. **Edit `src/python_setup_lint/runner/output.py`** — In `_summarize_pyright_verify_types` (around lines 221-250), stop appending `missingFunctionDocStringCount`, `missingClassDocStringCount`, and `missingDefaultParamCount` to the `parts` list. Render only `completenessScore` (and "all complete" fallback). Rationale: CodingRules.md declares `.py` docstrings intentionally empty; pyright verifytypes hardcodes these counts with no config/flag to disable — so the runner must not surface them.

2. **Add unit tests** — In the appropriate test module (likely `tests/runner/`), add test cases for:
   - Score present (normal case)
   - Score absent (fallback)
   - Malformed JSON
   - Non-dict top-level
   - All-zero counts

3. **Verify** — Run `pytest tests/runner/` to confirm tests pass.

## Constraints
- Do NOT change the symbols-array dump filtering — that's already done in `_print_result` (output.py:263-268)
- Do NOT change the JSON parsing or data structures — only the rendered summary text
- Keep the `completenessScore` rendering intact
- Do not worry about other tasks in plan — they are taken care of elsewhere
