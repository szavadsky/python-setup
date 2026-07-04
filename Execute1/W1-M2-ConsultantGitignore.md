Implement M2 — consultant.mcp gitignore + remove committed absolute symlinks

Read {F}/plan1.md:46-47 for the full spec.

## What to do

consultant.mcp's `.gitignore` (L92-94) only ignores `.pylintrc-pyi` and `.pylintrc-tests`. Extend the gitignore block to cover ALL python-setup-generated config symlinks.

1. **Find consultant.mcp**: It should be at `~/aiexp/consultant.mcp/`. If not there, search for it.

2. **Extend `.gitignore`** in consultant.mcp to ignore:
   - `.pylintrc`
   - `ruff.toml`
   - `mypy.ini`
   - `pyrightconfig.json`
   - `rumdl.toml`
   - `ty.toml`
   - `.yamllint`
   - (keep existing `.pylintrc-pyi`, `.pylintrc-tests`)

   These point into `.venv` (machine-specific) and must never be committed.

3. **Remove currently-tracked absolute symlinks** from git:
   - `git rm --cached` the 9 config files listed above
   - Leave them on disk so local lint keeps working until M1 redeploy regenerates them as relative

4. **Commit** the changes in consultant.mcp.

## Acceptance
- `git status` in consultant.mcp shows the symlinks removed from index
- `.gitignore` matches each config file name
- All changes committed with descriptive message
