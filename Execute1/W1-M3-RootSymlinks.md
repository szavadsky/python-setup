Implement M3 — Root config symlinks for standalone-tool parity in python-setup

Read {F}/plan1.md:48-49 for the full spec.

## What to do

python-setup itself has configs only in `config/`, so `uv run rumdl fmt` / `uv run pylint` / `uv run ruff` cannot auto-discover them (rumdl searches CWD+parents, not `config/`).

Create root-level relative symlinks `config/<name> → <name>` (or `<name> → config/<name>`) for:
- `ruff.toml`
- `.pylintrc`
- `mypy.ini`
- `pyrightconfig.json`
- `rumdl.toml`
- `ty.toml`
- `.yamllint`
- `.pylintrc-pyi`
- `.pylintrc-tests`

These are already gitignored (`.gitignore` L226-233 lists root config names as ignored), so they're local-only.

This mirrors what `python-setup install` does for consumers; apply the same relative-symlink helper to python-setup's own root.

## Implementation approach
- Create a script or add a step in the project setup that creates these symlinks
- Use `os.path.relpath` to compute relative targets (same pattern as M1)
- The symlinks should be relative: `config/ruff.toml -> ../config/ruff.toml` (or similar)
- Add a `postinstall` or `setup` mechanism, OR just create them as part of a setup script

## Acceptance
- `uv run rumdl fmt --check .` no longer splits long lines / adds `text` fence tags (MD013/MD040 respected)
- `uv run pylint src/python_setup_lint` standalone == `uv run lint` pylint section
- Symlinks are relative (no `/home/slava` paths)
- All changes committed with descriptive message
