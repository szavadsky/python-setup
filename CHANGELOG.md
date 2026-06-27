# Changelog

## v0.9.0 (2026-06-27) — Iteration 7: pylint-pyi pass, self-consistency, semantic reranker-only, integration test
  
**WS1: Unmask .pyi checking.** Added `pylint-pyi` as a 12th lint tool — a second pylint pass
that targets `.pyi` files with a `.pyi`-scoped rcfile. `pyi_underscore_checker` (W9707) now
actually fires. Created `config/.pylintrc-pyi` that disables `.py`-only checkers.
  
**WS2: Remove try/except ImportError self-contradiction.** `check_if_meaningful` in `_base.py`
now imports `_semantic` unconditionally (first-party module, always present). The feature is
gated by env var, not import fallback. Resolves W9001 self-violation.
  
**WS3: Missing .pyi stubs + CodingRules.** Added stubs for `generic_key_dict_checker`,
`unnamed_tuple_dict_checker`, and `structlog_checker`. Added Test Imports, Generic-key Dict,
and Unnamed Tuple Dict Values sections to CodingRules.md.
  
**WS4: Semantic reranker-only.** Removed the embedder (`bge-small-en-v1.5`) from the semantic
pipeline — kept only the cross-encoder reranker (`jina-reranker-v2-base-multilingual`).
Arg-keyed SHA-256 cache persists results across processes. Cache dir is `~/.cache/python-setup/semantic/`
(outside repo, effectively gitignored).
  
**WS5: Semantic tests — no importorskip.** Removed all `pytest.importorskip` calls from semantic
tests. Slow tests fail visibly with ImportError when `sentence_transformers` is absent. Added
cache-hit test (non-slow). Only cache-bypass tests are `@pytest.mark.slow`.
  
**WS6: Integration test + sample project.** Created `tests/integration.py` with 4 scenarios
(setup+lint, config overlay, resetup idempotent, dry-run hooks). Extended
`test/data/minimal_sample_project/` with `.secrets.baseline`, `tach.toml`, `AGENTS.md`,
`tests/test_tempfile.py`, `standalone.pyi`.
  
**WS7: Test invariants for 12-tool set.** Updated all test invariants that hardcoded the old
11-tool count. Non-slow test suite: 1002 passed in 15.55s (under 30s target).
  
**WS8: Version bump 0.8.0→0.9.0.** Updated `pyproject.toml`, README, CHANGELOG.

## v0.8.0 (2026-06-27) — Iteration 5+6 hardening: NLP rework, bug fixes, sample project, integration tests

Hardening batch covering iteration 5 and 6 of the lint-goal:

**Track B: NLP semantic experiment rework.** Wired `_semantic.py` into
`check_if_meaningful` (was disconnected). Resolved W9001 vs `try/except ImportError`
conflict with optional-dependency allowlist. Fixed `.gitignore` cache entry (tilde
path was ineffective). Added model singleton cache + arg-keyed result cache.
Reworked tests: `pytest.importorskip` instead of silent `@pytest.mark.skipif`.
Removed `@pytest.mark.slow` from `test_consolidated_real_pipeline_smoke`.
Created `_semantic.pyi` stub. Fixed broad `except Exception` to specific types.
Reranker failure now returns `None` (defer to heuristic) instead of `True`.

**Track X: Latent bug fixes.** Fixed Python-2-style `except AttributeError, TypeError:`
in `beartype_checker.py`. Resolved W9720 rule-ID collision between
`generic_key_dict_checker` and `unnamed_tuple_dict_checker` (W9720→W9721).
Updated all 11 checker `msgs` dicts to `dict[LintRuleId, MessageDef]`.
Fixed bare `# type: ignore[union-attr]` in `suppression_justification_checker.py`.
Repaired `_base.pyi` broken stub (orphaned docstring string-literals).
Eliminated duplicated checker helpers (`_get_file_path`, `_is_under_source_root`,
`_matches_path`) by importing from `_base`.
Normalized `asyncio_timeout_checker` msgs typing to `dict[LintRuleId, MessageDef]`.

**Track C: Sample project + integration tests.** Created
`test/data/minimal_sample_project/` with planted violations for all 10 custom
linters. Created `tests/test_integration.py` with 7 scenarios (setup, lint,
tools, config overlay, resetup, git hooks). Added `sample_project` fixture.

**Track V: Version + docs.** Bumped to 0.8.0. Updated `docs/semantic-justification.md`
with rework details (config flag, cache singleton, test strategy).
`configured_project` fixture changed to session-scoped for perf.

**Perf:** Non-slow test suite optimized. `configured_project` session-scoped.
`check_if_meaningful` now uses `rule` param to reject justifications equal to
the rule symbol.

## v0.7.0 (2026-06-26) — Docstring returns-clause rule, checkers reorg, dict-prohibition rules, suppression-justification linter, test perf, sample project

Feature batch covering WS-1 through WS-8:

**WS-1: `_`-symbol test-import convention.** Tests import `_`-prefixed symbols only from
their defining submodule, never through the package root. New guard test enforces this.

**WS-2: Test perf under 30 s.** Default `pytest` excludes `@pytest.mark.slow` tests
(benchmarks, real-subprocess runs). Slow-marked `TestPerfBenchmark` class.

**WS-3: Sample project + integration tests.** `test/data/minimal_sample_project/` with
planted violations. `test/integration.py` with scenario-based E2E tests. `.gitignore`
updated for setup-generated artifacts.

**WS-4: Checkers reorg.** `checkers/` restructured into `conformance/` and `stub/`
subfolders. `_checker_base.py` renamed to `_base.py`. `check_if_meaningful` helper
added to `_base.py`.

**WS-5: Unnamed-tuple dict prohibition.** New `unnamed_tuple_dict_checker` flags `dict`
values that are bare `tuple`/`Tuple[...]` literals with >1 unnamed positional fields.
All checker `msgs` dicts migrated to `MessageDef` named type.

**WS-6: Generic-key dict prohibition.** New `generic_key_dict_checker` flags `dict[str, X]`
annotations where the key represents a typed domain value. `LintRuleId` type introduced.
Runner helpers and record types migrated.

**WS-7: Justified-suppression linter.** New `suppression_justification_checker` flags
`# pylint: disable`, `# noqa`, `# type: ignore` without a technical justification.
`check_if_meaningful` heuristic in `_base.py`.

**WS-8: Docstring rules + version + README + docs/.**
- `stub_docstring_checker` gains `generic-return-requires-returns` and
  `internal-helper-docstring-allowed` rules.
- `CodingRules.md` updated with docstring rule bullets.
- `README.md` slimmed to user-focused content; detail moved to `docs/overlays.md`
  and `docs/custom-checks.md`.
- Version bumped to 0.7.0.

## v0.6.0 (2026-06-23) — T4 autofix route through the lint wrapper + conflict-tolerant pre-commit hook + E999 canary + env-var opt-out

The `lint` console-script's `--fix` flag now runs autofix across ALL
`supports_fix=True` tools (ruff, rumdl, ty), not just the standalone
`ruff-fix` pre-commit hook. The pre-commit template's `lint` local hook
entry is `python-setup lint --fix --no-fail-fast --baseline lint.baseline`
— the full pipeline now runs on `git commit` (no `pre-push` hook), autofixes
all supported tools, then re-runs the baseline-gated verification pass.
Autofix is courtesy, never blocks. Three conflict-tolerance mechanisms:

1. **Staged+unstaged skip** — files appearing in BOTH `git diff --name-only
   --cached` and `git diff --name-only` (a file the user has staged AND
   further edited in the worktree) skip autofix entirely; the runner
   never `git add`s, so applying a fix there would conflict with the
   staged blob. One stderr line per skipped file.
2. **E999 canary revert** — after each `supports_fix` tool's fix pass, a
   single extra `ruff check --no-fix` parseability canary runs over the
   files the tool touched. Any file ruff reports `E999` on is reverted
   from an in-memory byte snapshot captured BEFORE the fix pass — the
   tracked-file `git checkout` fallback is never reached in tests. The
   canary call carries the `python-setup:autofix-canary` label so a
   dict-mode fake can return E999-marked output for the canary only. The
   E999 line parser is tolerant of Windows drive-letter colons in the
   path group (greedy regex anchors on `:INT:INT: E999` shape).
3. **Env-var opt-out** — `PYTHON_SETUP_LINT_NO_AUTOFIX=1` flips `fix=False`
   internally before the tool loop runs; the `--fix` CLI arg still parses
   unchanged. A single stderr line confirms the override for observability.

New public surface (all underscore-prefixed, re-exported from
`python_setup_lint.runner`): `_apply_autofix_conflict_aware`,
`_autofix_target_paths`, `_git_changed_files`, `_ruff_parseability_errors`,
`_AUTOFIX_ENV_VAR`, `_E999_RULE`, `_E999_LINE_RE`. `run_lint(fix=True)`
routes `supports_fix` tools through `_apply_autofix_conflict_aware`; other
tools keep the plain path.

README: the pre-commit section now reflects the new hook shape (no
`pre-push`; full pipeline on `git commit` with `--fix`). The "Using
python-setup in another project" step table's "Pre-commit config" row
lists the full new entry.

## v0.5.0 (2026-06-21) — ty config-file fix + RunnerConfig.config_paths stub published + portable PYI048 + pylint rcfile auto-discovery contract + README sections

Adds `ty check` `--config-file` flag (previous `--config` was rejected by ty>=0.0.49).
The `RunnerConfig.config_paths` field — present in source since T9 — now ships in the published `runner/types.pyi`.
Portable ruff `*.pyi` per-file-ignores gains `PYI048` (docstring + `...` is two statements; allowed in stubs).
Adds the 4-test contract for `_PylintLintTool._resolve_pylintrc` auto-discovery/explicit-override/missing-None/build-injects-rcfile.
README gains the 3 user-facing sections: 'Custom lint steps via pyproject.toml', 'Using python-setup in another project', 'Re-baselining'.

**NOTE:** the v0.4.0 tag existed in git but the wheel was never rebuilt from it — v0.5.0 supersedes both v0.3.0's published wheel and the v0.4.0 tag.
