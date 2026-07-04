# Task: Commit, bump versions, push both repos

## Plan reference
Read `~/aiexp/python-setup/scratchpad/plan2.md` lines 58-59 (M7 section), lines 68 (pitfall about patch vs minor bump).

## What to do

### Part A: Check git status
1. `cd ~/aiexp/python-setup && git status` — check for uncommitted changes
2. `cd ~/aiexp/consultant.mcp && git status` — check for uncommitted changes

### Part B: Commit any remaining uncommitted changes
- python-setup: commit with message describing the changes (M2 pyright summary strip, M3 tach parser + modules, M6 fixups, M5 doc alignment)
- consultant.mcp: commit with message describing the changes (M4 no-fail-fast purge, M5 doc alignment)

### Part C: Bump versions
- python-setup: patch bump 1.2.0 → 1.2.1 (bugfix/noise fixes per semver)
  - Update `pyproject.toml` version field
  - Update `CHANGELOG.md` with new version entry
- consultant.mcp: patch bump 0.4.0 → 0.4.1
  - Update `pyproject.toml` version field
  - Update `CHANGELOG.md` with new version entry

### Part D: Push
- `cd ~/aiexp/python-setup && git push`
- `cd ~/aiexp/consultant.mcp && git push` (if it tracks a remote)

### Part E: Final verification
- `cd ~/aiexp/python-setup && git status` — should be clean
- `cd ~/aiexp/consultant.mcp && git status` — should be clean

## Constraints
- Patch bump per semver (bugfix) — unless the team considers noise-filtering a behavior change worth a minor bump. Default to patch.
- Do not worry about other tasks in plan — they are taken care of elsewhere
