# Task: Fix two regressions found by M6 verification

## Context
M6 verification found two real regressions from M2/M3 changes:

### Regression 1: pylint `too-many-lines` in test file
- File: `tests/runner/test_lint_runner.py` — 524 lines, exceeds `max-module-lines=500` in `config/.pylintrc-tests`
- Cause: M2 added `TestSummarizePyrightVerifyTypes` class (44 lines), pushing from 480→524
- Fix: Add `# pylint: disable=too-many-lines` at the top of the file (after the module docstring)

### Regression 2: rumdl failures on Execute2/ files
- File: `config/rumdl.toml`
- Cause: M3 added `Execute2/` directory but rumdl.toml only excludes `Execute1`
- Fix: Add `"Execute2/**"` to the exclude list in `config/rumdl.toml`, matching the existing `"Execute1/**"` entry

## What to do
1. Read `tests/runner/test_lint_runner.py` — add `# pylint: disable=too-many-lines` at module level
2. Read `config/rumdl.toml` — add `"Execute2/**"` to the exclude list
3. Verify: run `cd ~/aiexp/python-setup && uv run pylint --rcfile=config/.pylintrc-tests tests/runner/test_lint_runner.py` — should pass
4. Verify: run `cd ~/aiexp/python-setup && uv run rumdl check Execute2/` — should pass (no issues)
5. Commit with message "fix: address M6 verification regressions — pylint too-many-lines and rumdl Execute2 exclusion"
