Implement M6 — Filter pyright `verifytypes` metadata noise in runner

Read {F}/plan1.md:58-59 for the full spec.

## What to do

`runner/output.py:_print_result` (L229-230) prints `result.stdout` verbatim. For `pyright verify types`, stdout is the full `--outputjson` blob whose `typeCompleteness` section contains: `missingFunctionDocStringCount`, `missingClassDocStringCount`, `missingDefaultParamCount`, `completenessScore`, a `symbols` array (one entry per exported symbol with `referenceCount` etc.), and absolute machine paths (`packageRootDirectory`, `moduleRootDirectory`, `pyTypedPath`).

The runner's violation parser (`parsers.py:_parse_pyright_verify_types` L134-149) already extracts only the `incomplete` symbol count from `symbols` — the rest is noise.

## Fix

For the `pyright verify types` tool, replace verbatim stdout printing with a filtered summary:
- Parse the JSON
- Print only `summary` fields (or a concise summary line)
- Do NOT print the full `symbols` array or absolute machine paths
- Keep `LintResult.stdout` intact for parsers — filter only the `_print_result` display

## Important
- The baseline comparison (`_baseline_helpers._strip_pyright_volatile`) already strips `moduleRootDirectory`/`packageRootDirectory` from stored baselines — the printed-noise filter must not break the parser path.
- Filter only the `_print_result` display, keep `LintResult.stdout` intact for parsers.

## Acceptance
- `uv run lint` output no longer contains pyright `typeCompleteness`/`symbols`/`missingFunctionDocStringCount` noise
- No absolute `/home/` paths in lint output
- `uv run lint` exits 0
- All changes committed with descriptive message
