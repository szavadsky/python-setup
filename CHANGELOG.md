# Changelog

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

## v0.9.0 (2026-06-27)

- Added `pylint-pyi` as a 12th lint tool — a second pylint pass targeting `.pyi` files with `.pyi`-scoped rcfile.
- Semantic reranker-only — removed the embedder (bge-small-en-v1.5), kept only the cross-encoder reranker (jina-reranker-v2-base-multilingual).

## v0.8.0 (2026-06-27)

- Track B: NLP semantic experiment rework — wired `_semantic.py` into `check_if_meaningful` (was disconnected).

## v0.7.0 (2026-06-26)

- New `unnamed_tuple_dict_checker` — flags `dict` values that are bare `tuple`/`Tuple[...]` literals with >1 unnamed positional fields.
- New `generic_key_dict_checker` — flags `dict[str, X]` annotations where the key represents a typed domain value.
- New `suppression_justification_checker` — flags `# pylint: disable`, `# noqa`, `# type: ignore` without a technical justification.

## v0.6.0 (2026-06-23)

- Autofix route through the lint wrapper — `--fix` flag now runs autofix across ALL `supports_fix=True` tools (ruff, rumdl, ty).
- Conflict-tolerant pre-commit hook — staged+unstaged skip, E999 canary revert, env-var opt-out (`PYTHON_SETUP_LINT_NO_AUTOFIX=1`).

## v0.5.0 (2026-06-21)

- `ty check` `--config-file` flag (previous `--config` was rejected by ty>=0.0.49).
- `RunnerConfig.config_paths` field ships in published stub.
- NOTE: v0.4.0 tag existed in git but the wheel was never rebuilt from it — v0.5.0 supersedes both v0.3.0's published wheel and the v0.4.0 tag.
