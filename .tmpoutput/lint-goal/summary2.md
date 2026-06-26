# lint-goal — Iteration 2 Summary

## Status: All high-priority work complete

Track A (self-consistency/DoD closure) and Track C (perf audit) implemented and verified. 985 tests pass, 9 deselected. Non-slow run: 17.27s.

## Track A — Self-consistency / DoD closure

### A1: Justify bare suppressions in src/
- Added technical justifications to all bare `# noqa: TC001/TC002/TC003` imports across 20+ files in `checkers/`, `runner/`, and `testing.py`.
- All now carry `# TYPE_CHECKING-only import; pylint is a dev dependency` or similar.

### A2: Register 3 new checkers in config/.pylintrc
- Added `suppression_justification_checker`, `unnamed_tuple_dict_checker`, `generic_key_dict_checker` to `load-plugins`.

### A3: Migrate suppression_justification_checker msgs to MessageDef
- Converted from old tuple format to `MessageDef` named tuples.

### A4: Wire check_if_meaningful params
- `check_if_meaningful` now uses `comment` as primary text (falls back to `text`).
- `rule` and `code_context` reserved for future semantic analysis.

### A5: Add check_if_meaningful to _base.pyi
- Added full signature declaration to `_base.pyi`.

### A6: Expose __version__ in __init__.py
- `__version__` reads from `importlib.metadata.version("python-setup")`.

## Track C — WS-2.3 perf audit

### C1: Mark pyright-live tests slow
- `TestLiveSmokePyrightConfigCollapse` in `test_t9_7_compose_pyright_live.py` now has `@pytest.mark.slow`.

### Result
- Non-slow run: **17.27s** (down from 25.97s in iteration 1).

## Track B — NLP semantic experiment (DEFERRED)

Not implemented. Opt-in research gated behind `[semantic]` optional-dep. Lowest priority per plan.

## Verification

- **985 tests passed**, 9 deselected (slow).
- Non-slow test run: **17.27s** (well under 30s target).
- All checker tests pass.
- All runner tests pass.

## Remaining Work

- **Track B (NLP)**: `bge-small` + `jina` reranker — opt-in, deferred. Would require `sentence-transformers` extra, lazy imports, and a `_semantic.py` module. Not needed for DoD.

## Iteration Count

2 of 5 iterations complete. DoD satisfied. Ready for iteration 3 if Track B is desired.
