Implement M8 — Redeploy config to consultant.mcp and regenerate baseline

Read {F}/plan1.md:63-64 for the full spec.

## What to do

After M1 (relative symlinks), M4 (W9705 disabled), M5 (500 lines), M6 (noise filter) are all done in python-setup:

1. **Bump python-setup version** in `pyproject.toml` from 1.1.1 → 1.2.0 (breaking config semantics: W9705 disabled, symlink format changed, 500-line gate restored — minor bump justified).

2. **Update `CHANGELOG.md`** with user-visible entries:
   - Relative config symlinks (portability fix)
   - W9705 disabled (behaviour change)
   - `max-module-lines` restored to 500
   - pyright verifytypes noise filtered
   - Root config symlinks for standalone-tool parity

3. **Commit python-setup** first (configs + setup.py + runner + split module + docs).

4. **In consultant.mcp** (`~/aiexp/consultant.mcp/`):
   - Run `uv run python-setup install` (or `uv sync` + install) to regenerate config symlinks as relative and refresh `CodingRules.md` + pylint `load-plugins`
   - Verify the project-specific overlays survive: `tach.toml` (real file, `_SKIP_SYMLINK_IF_EXISTS`) untouched; chunking-corpus ruff `per-file-ignores` in consultant.mcp `pyproject.toml` intact; `config/*.yaml` overlays intact
   - Regenerate `lint.baseline`: run `uv run lint --overwrite-baseline --baseline lint.baseline` then `uv run lint --baseline lint.baseline` to confirm zero new violations (clean diff against new baseline)
   - Verify pre-commit hook still passes: `.pre-commit-config.yaml` runs `uv run lint --fix --baseline lint.baseline`

5. **Bump consultant.mcp version** 0.2.0 → 0.3.0 (config redeploy + baseline regeneration).

6. **Commit consultant.mcp** (gitignore + removed tracked symlinks + regenerated relative symlinks gitignored + baseline + version).

7. **Push both** repos.

## Acceptance
- `uv run lint` in consultant.mcp exits 0 against regenerated `lint.baseline`
- `ls -la consultant.mcp/.pylintrc` → relative symlink (no `/home/slava`)
- `grep -rn /home/slava config/ src/ docs/` → no hardcoded absolute paths
- `uv run python-setup install` on a fresh temp project → symlinks relative + idempotent on re-run
- Both repos committed and pushed
