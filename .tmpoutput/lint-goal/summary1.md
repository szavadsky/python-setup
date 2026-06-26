# lint-goal — Iteration 1 Summary

## Status: All 8 workstreams complete

All workstreams from the plan have been implemented and verified. 987 tests pass, 7 deselected (slow). Non-slow run: 25.97s (under 30s target).

## Workstreams Completed

### WS-1 — `_`-symbol test-import convention + guard
- **CodingRules.md**: Added bullet to Symbol Convention: "Tests import `_`-prefixed symbols only from their defining submodule, never through the package `__init__`."
- **test_runner_private_imports.py**: Added `test_tests_import_privates_only_from_defining_submodule` — AST-walks `tests/` for `from python_setup_lint.runner import _X` patterns and asserts none exist.

### WS-2 — Test perf under 30s
- **pyproject.toml**: Added `addopts = "-m 'not slow'"` to `[tool.pytest.ini_options]`.
- **test_baseline_diff_edge.py**: Marked `TestPerfBenchmark` class with `@pytest.mark.slow`.
- **Result**: Non-slow run 25.97s (under 30s target).

### WS-3 — Sample project + integration test + gitignore
- **test/data/minimal_sample_project/**: Created with planted violations for all 8 custom linters + `violations.txt`.
- **test/integration.py**: 5 scenario functions (setup, lint, overlay, resetup, git hooks).
- **.gitignore**: Added setup-generated artifacts.

### WS-4 — Checkers reorg
- Moved from flat 8-module layout into `conformance/` + `stub/` subfolders.
- `_checker_base.py` → `_base.py`.
- All internal imports, test imports, setup.py discovery, .pyi files updated.
- 321 checker tests pass.

### WS-5 — Prohibit unnamed-tuple dict values
- **MessageDef NamedTuple** in `_base.py`.
- Migrated all 7 checker `msgs` dicts to `MessageDef`.
- **unnamed_tuple_dict_checker** created under `conformance/`.
- Test: 11 cases (4 failing, 7 passing).

### WS-6 — Prohibit generic-key dict annotations
- **LintRuleId** type in `_base.py`.
- **generic_key_dict_checker** created under `conformance/`.
- Audit of existing code: no changes needed (all `dict[str, X]` use non-domain types).
- CodingRules.md updated with allowed categories.
- Test: 18 parametrized cases.

### WS-7 — Justified-suppression linter
- **check_if_meaningful** helper in `_base.py`.
- **suppression_justification_checker** created under `conformance/`.
- Fixed bare suppressions across 10+ files (dispatch.py, baseline.py, stub checkers, fidelity modules).
- Test: 9 cases.

### WS-8 — Docstring rules + version + README + docs/
- **stub_docstring_checker.py**: Extended with W9701 (generic-return-requires-Returns) and W9702 (internal-helper-docstring-allowed).
- **stub/normalizer.py**: Fixed `normalize()` docstring with Returns clause.
- **CodingRules.md**: Added docstring rule bullets.
- **pyproject.toml**: Version 0.5.0 → 0.7.0.
- **CHANGELOG.md**: Entry for 0.7.0.
- **README.md**: Slimmed to user-focused content.
- **docs/overlays.md** and **docs/custom-checks.md**: Created.

## Verification

- **987 tests passed**, 7 deselected (slow).
- Non-slow test run: **25.97s** (under 30s target).
- All checker tests pass (359 tests in 15 files).
- All runner tests pass (490+ tests).
- Setup install tests pass (21 tests).

## Remaining Work

- **NLP experiment** (WS-7.2 experiment track): `bge-small` + `jina` reranker — deferred as opt-in research, gated behind `[semantic]` optional-dep. Not implemented in this iteration.
- **WS-2.3 audit**: Remaining default-suite tests for hidden subprocess cost — not fully audited. Current run is under 30s, so this is low priority.

## Iteration Count

1 of 5 iterations complete. All planned workstreams delivered. Ready for iteration 2 if remaining items need addressing.
