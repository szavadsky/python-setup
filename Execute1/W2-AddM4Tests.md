Add unit tests for the ruff version resolution logic in `_step_precommit` in python-setup.

Read {F}/plan1.md:51-55 for context.

## Background

The `_step_precommit` function in `src/python_setup_lint/_setup_precommit.py` resolves the installed ruff version at install time by running `ruff --version` and interpolates it into the pre-commit template. Currently there are NO unit tests for this resolution logic.

## What to test

1. **Normal ruff version parsing**: Mock `subprocess.run` to return `"ruff 0.15.17"` — verify the template gets `rev: v0.15.17`.

2. **Version with 'v' prefix**: Mock output `"ruff v0.15.17"` — verify `rev: v0.15.17` (no double v).

3. **FileNotFoundError fallback**: Mock `subprocess.run` to raise `FileNotFoundError` — verify fallback to `_RUFF_FALLBACK_REV` (v0.14.10).

4. **Non-zero returncode**: Mock `subprocess.run` to return `returncode=1` — verify fallback to `_RUFF_FALLBACK_REV`.

5. **Integration test update**: The existing integration test writes raw unformatted template with `{ruff_rev}` placeholder. Update it to exercise dynamic resolution (or at least verify the template is properly formatted).

## Implementation approach

- Create a new test file `tests/test_setup_precommit.py`
- Use `tmp_path` fixture for project dir
- Mock `subprocess.run` to control ruff version output
- Call `_step_precommit` and verify the written `.pre-commit-config.yaml` content
- Test all 4 paths: normal, v-prefixed, FileNotFoundError, non-zero returncode

## Acceptance
- All new tests pass: `uv run pytest tests/ -k precommit -v`
- Existing tests not broken: `uv run pytest tests/integration.py -v`
- All changes committed with descriptive message
