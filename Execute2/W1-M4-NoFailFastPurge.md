# Task: Purge stale `--no-fail-fast` from consultant.mcp docs

## Plan reference
Read `~/aiexp/python-setup/scratchpad/plan2.md` lines 55-56 (M4 section), lines 26-27 (surface direction), lines 67 (pitfall about test comments).

## What to do

The `--no-fail-fast` flag was removed in v1.0.0 (CHANGELOG.md:66) yet consultant.mcp docs still reference it. Purge every stale reference.

### Files to edit in consultant.mcp repo (at `~/aiexp/consultant.mcp`):

1. **`AGENTS.md`** — lines 37, 43: remove `--no-fail-fast` references
2. **`CHANGELOG.md`** — lines 8-9: remove `--no-fail-fast` references
3. **`design/08-decisions-and-references.md`** — lines 423-424: remove `--no-fail-fast` references
4. **`tests/unit/_lint/test_precommit.py`** — lines 5, 50, 61: these are comments/docstrings only (the actual test asserts `--baseline`, not `--no-fail-fast`). Update the comments.

### Verify
- Run `grep -rn 'no-fail-fast' ~/aiexp/consultant.mcp/` — should return no hits
- Confirm `.pre-commit-config.yaml:33` is already clean (read it to verify)

## Constraints
- Doc-only changes — no logic changes
- Test comments are stale but the test logic itself is correct — only fix the comments
- Do not worry about other tasks in plan — they are taken care of elsewhere
