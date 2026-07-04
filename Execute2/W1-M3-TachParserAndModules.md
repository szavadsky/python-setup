# Task: Make tach actually report — fix parser and add module boundaries

## Plan reference
Read `~/aiexp/python-setup/scratchpad/plan2.md` lines 54-55 (M3 section), lines 24-25 (surface direction), lines 37-38 (data structures), lines 46-47 (test coverage), lines 13-14 (tach direction), lines 63-66 (pitfalls).

## What to do

### Part A: Fix `_parse_tach_json` in `src/python_setup_lint/runner/parsers.py`

1. Read the current `_parse_tach_json` function (around lines 162-168) and `_load_json_dict` callers
2. Handle tach 0.35.0's list schema: when `json.loads` yields a list, scan items for `severity == "Error"` and return `[("tach:error", n)]`; treat `Warning` items explicitly (surface as `[("tach:warning", n)]` so warnings aren't silently lost)
3. Keep legacy dict-`errors` path working
4. **Critical**: Do NOT change `_load_json_dict` signature — it's load-bearing elsewhere. Handle list inline in `_parse_tach_json` or create a separate helper.

### Part B: Add `[[modules]]` to tach.toml files

1. Read current `tach.toml` and `config/tach.toml`
2. Add `[[modules]]` entries reflecting python-setup's layer boundaries (e.g. `python_setup_lint.checkers`, `python_setup_lint.runner`, `python_setup_lint.setup`)
3. Run `tach check` iteratively to confirm no "No first-party imports" warning and real boundary enforcement
4. If module boundaries prove unmotivated, document why and leave tach.toml without modules (prefer configuring it though)

### Part C: Verify
- Run `pytest tests/runner/` to confirm tests pass
- Run `tach check` to confirm no warnings

## Constraints
- Do NOT break the legacy dict path — some consumers/tests still use `{"errors": [...]}`
- `_load_json_dict` returning `{}` for list input is load-bearing elsewhere — check all callers before changing
- consultant.mcp tach.toml is preserved by `_SKIP_SYMLINK_IF_EXISTS` — changing `config/tach.toml` in python-setup does NOT change consultant.mcp's tach config
- Do not worry about other tasks in plan — they are taken care of elsewhere
