# Changelog

## v1.2.0 (2026-07-04)

## v1.2.1 (2026-07-04)

- Pyright verifytypes: strip docstring/default-param noise from runner summary display
- Tach parser: fix for 0.35.0 list schema (handle both dict and list error shapes)
- Tach modules: add [[modules]] boundaries at subpackage granularity
- Output stub: add _summarize_pyright_verify_types to output.pyi stub
- Fix M6 verification regressions: pylint too-many-lines and rumdl Execute2 exclusion
- Docs: align deployment docs with actual code behavior

- Config symlinks: create relative symlinks instead of absolute paths for cross-machine portability
- W9705 (generic-return-requires-returns): disabled in both .pylintrc and .pylintrc-pyi
- max-module-lines: restored to 500 (was inadvertently lowered)
- pyright verifytypes: filter metadata noise from _print_result display
- Root config symlinks: create root-level symlinks for standalone-tool parity

## v1.1.1 (2026-07-04)

- Config registries: add .pylintrc-pyi/.pylintrc-tests to _BUNDLED_CONFIGS and _SHIPPED_CONFIG_FILES
- Dispatch: fix pylint-pyi/tests rcfile fallback to use _default_config_paths instead of broken Path(__file__) arithmetic
- Detect-secrets: fix `;`→`&&` separator so missing tool surfaces as exit 1 instead of being masked

## v1.1.0 (2026-07-03)

- Baseline: relativize file paths in lint.baseline for cross-machine portability
- Installer: create root-level config symlinks for single-source-of-truth tool config
- Runner: fix pylint-pyi/tests config resolution to check root symlinks first
- Installer: dynamically resolve ruff version for pre-commit template

## v0.17.0 (2026-07-02)

- Fixed crash on non-existent baseline file (WS-1).
- Fixed W9704 docstring false-positive (WS-2).
- W9704 Any param/return detection in prod code (WS-3).
- Enabled R0801 (similar lines) pylint checker (WS-4).
- Improved crash visibility — runner now shows tool name and exit code on failure (WS-5).
- Migrated baseline format to JSON (WS-6).
- Fixed benchmark memory leak (WS-7).
- Added config symlink support for consumer projects (WS-8).
- Config symlink root stubs (WS-8 detail).
- Unjustified suppression audit (WS-12).
- Sentence-transformer download-avoidance + fallback test (WS-11).

## v0.16.0 (2026-07-01)

- Rumdl now lints all project `.md` files (default_paths changed from `["src/"]` to `["."]`).
- Enabled rumdl frontmatter rules MD071 (blank-line-after-frontmatter) and MD072 (frontmatter-key-sort).
- Fixed missing runtime dependencies: `structlog`, `beartype`, `tomli-w` now in `[project] dependencies`.
- Removed duplicate `pytest`/`pylint`/`beartype` from `[dependency-groups] dev`.
- Fixed frontmatter violations in `.omp/agents/*.md` (MD071×3, MD072×8).

## v0.14.0 (2026-06-28)

- No material changes — version skipped during development cycle.

## v0.15.0 (2026-06-28)

- Lint `tests/` with pylint via new `.pylintrc-tests` hybrid rcfile (W9704/W9702 now enforced on test code; production-only rules disabled for tests with justification).
- Pipeline now 13 tools (added `pylint tests`).

## v0.13.0 (2026-06-28)

- Fixed rumdl regression — trailing space in .omp/agents/implement-subtask.md.

## v0.12.0 (2026-06-28)

- Scoped pylint and ty to `src/` only — removed 236 baked-in baseline violations from tests/.
- Fixed `_semantic.py` reranker download-failure retry storm — `_RERANKER_UNAVAILABLE` sentinel now set on OSError/RuntimeError/ValueError.

## v0.11.0 (2026-06-28)

- Removed fail-fast behavior entirely. The runner always executes all lint tools; the `--no-fail-fast` flag is no longer needed.

## v0.10.0 (2026-06-27)

- Runner robustness: `_run_cmd` now catches FileNotFoundError (returns rc=127 instead of crashing).

## v0.8.0 (2026-06-26)

- No material changes — version skipped during development cycle.

## v0.9.0 (2026-06-27)

    - Added `pylint-pyi` as a 12th lint tool — a second pylint pass targeting `.pyi` files with `.pyi`-scoped rcfile.

## v0.7.0 (2026-06-26)

- New `unnamed_tuple_dict_checker` — flags `dict` values that are bare `tuple`/`Tuple[...]` literals with >1 unnamed positional fields.
- New `generic_key_dict_checker` — flags `dict[str, X]` annotations where the key represents a typed domain value.
- New `suppression_justification_checker` — flags `# pylint: disable`, `# noqa`, `# type: ignore` without a technical justification.

## v0.6.0 (2026-06-23)

- Autofix route through the lint wrapper — `--fix` flag now runs autofix across ALL `supports_fix=True` tools (ruff, rumdl, ty).
- Conflict-tolerant pre-commit hook — staged+unstaged skip, E999 canary revert, env-var opt-out (`PYTHON_SETUP_LINT_NO_AUTOFIX=1`).

## v0.5.0 (2026-06-21)

- `ty check` `--config-file` flag (previous `--config` was rejected by ty>=0.0.49).
- `RunnerConfig.config_paths` now defaults to empty dict instead of None.
