Implement M1 — Relative config symlinks in `python-setup install`

Read {F}/plan1.md:43-44 for the full spec.

## What to do

Fix `src/python_setup_lint/setup.py:_step_config_symlinks`:

1. **Relative symlink target**: Replace `os.symlink(str(source.resolve()), str(target))` with a relative link computed via `os.path.relpath(source.resolve(), start=target.parent.resolve())`. The symlink must read e.g. `.venv/lib/python3.14/site-packages/python_setup_lint/config/.pylintrc` (relative to project root), not `/home/slava/.../config/.pylintrc`.

2. **Matching-content skip logic**: Update the existing skip logic (around L321-330) to handle relative links: compare `Path(existing_target)` resolved against `project_dir` to `source.resolve()`. Keep the `_SKIP_SYMLINK_IF_EXISTS` exception for `tach.toml`. Keep the `copy2` fallback for symlink-hostile environments.

3. **Idempotent reinstall**: Existing absolute symlinks must be detected and replaced. The current code checks `os.path.isabs(existing_target)` then resolves — must also handle the new relative case: `(project_dir / existing_target).resolve() == source.resolve()`.

4. **Update existing tests** in `tests/test_setup_config_symlinks.py` to verify:
   - `os.readlink(target)` is relative (doesn't start with `/`)
   - `target.resolve() == source.resolve()` (resolves correctly)
   - Integration test passes

## Acceptance
- `uv run pytest tests/ -k config_symlink -v` passes
- `uv run pytest tests/integration.py -v` passes
- `os.readlink(target)` returns a relative path for every symlink created
- All changes committed with descriptive message
