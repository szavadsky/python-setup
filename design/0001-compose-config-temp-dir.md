# ADR 0001: Config composers — pyright writes to cwd, ruff writes to temp-dir

## Context

Config composers produce effective config files that extend a shared shipped config with
project-local settings. The ruff composer merges `pyproject.toml` overrides; the pyright composer
ensures pyright resolves `venvPath`/`exclude` against the project cwd (not the shipped config dir).

## Decision

- **Ruff** composes to `tempfile.gettempdir() / python_setup_lint_ruff_<cwd>/ruff.toml` — ruff
  accepts absolute `extend` targets, so a temp-dir works.
- **Pyright** composes to `cwd/.pyrightconfig-composed.json` (gitignored) — pyright resolves
  `venvPath` and `exclude` relative to the **config file's directory** and **silently rejects
  absolute paths** in `exclude`. A temp-dir breaks excludes (they resolve against the temp dir);
  absolute rewrites are ignored. Only a config file IN cwd with relative paths works.

The asymmetry is forced by the tools' differing path-resolution semantics.

## Consequences

- `.pyrightconfig-composed.json` is gitignored (`.gitignore:227`) — no leak into git.
- Ruff temp files are OS-cleaned; pyright cwd files are overwritten idempotently.
- Consumer projects must add `.pyrightconfig-composed.json` to their `.gitignore` (documented in
  `docs/overlays.md`).
