Implement M5 — Restore `max-module-lines=500` and split setup.py

Read {F}/plan1.md:54-55 for the full spec.

## What to do

CodingRules L141 + L168: C0302 ≤500/module, "never raise global thresholds to mask a hit… split the module."

1. **Revert `max-module-lines`**: `config/.pylintrc:9` and `config/.pylintrc-pyi:2` currently say `max-module-lines=510`. Revert both to `500`.

2. **Split `src/python_setup_lint/setup.py`** (currently 501 lines) below 500 lines by extracting a coherent slice into a sibling file. Candidates: the pyproject read/write helpers (`_read_pyproject_toml`, `_write_pyproject_toml`, `_pylint_main_section`, `_ensure_pylint_main_section`, `_get/set_pylint_load_plugins`, `_get_dev_deps`, `_has_python_setup_dep`) form a cohesive ~80-line TOML-manipulation slice.

3. **Update imports** in `setup.py` to import from the new module.

4. **Keep `install`/`main` in `setup.py`** — the CLI entry point must not break.

## Acceptance
- `wc -l src/python_setup_lint/setup.py` < 500
- `grep max-module-lines config/.pylintrc config/.pylintrc-pyi` → `=500` only
- `uv run lint` exits 0
- `uv run python-setup install` still works (CLI entry point intact)
- All changes committed with descriptive message
