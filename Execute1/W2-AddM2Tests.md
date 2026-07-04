Add unit tests for the config symlink creation step (`_step_config_symlinks`) in python-setup.

Read {F}/plan1.md:39-43 for context.

## Background

The `_step_config_symlinks` function in `src/python_setup_lint/setup.py` creates project-root symlinks for every bundled config file. Currently there are NO tests for this function.

## What to test

1. **`_step_config_symlinks` creates symlinks**: Given a fake project dir and a fake package dir with `config/` subdir containing bundled config files, calling `_step_config_symlinks` should create symlinks at the project root pointing to the config files.

2. **Symlink skip if already exists and matches**: If a symlink already exists pointing to the right source, it should be skipped (increment `skipped` counter).

3. **Symlink skip if content matches**: If a regular file exists with matching content, it should be skipped.

4. **`_SKIP_SYMLINK_IF_EXISTS` handling**: `tach.toml` should be skipped if it already exists (even if content differs).

5. **Fallback to copy on symlink failure**: If `os.symlink` raises `OSError`, it should fall back to `shutil.copy2`.

6. **`_s_fake_pkg` helper**: The test helper `_s_fake_pkg` (or equivalent) must create a `config/` subdir with bundled config files so the step doesn't silently produce 0/0.

7. **`_s_empty_bundled` helper**: Must not set `_BUNDLED_CONFIGS=()` — the step should work with the real bundled configs.

## Implementation approach

- Create a new test file `tests/test_setup_config_symlinks.py`
- Use `tmp_path` fixture for project dir
- Create a fake package dir with `config/` subdir containing test config files
- Monkey-patch `_get_package_dir` to return the fake package dir
- Assert symlinks created, counters correct, fallback behavior

## Acceptance
- All new tests pass: `uv run pytest tests/ -k config_symlink -v`
- Existing tests not broken: `uv run pytest tests/integration.py -v`
- All changes committed with descriptive message
