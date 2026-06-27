# Plan 1 — python-setup lint-goal (iteration 1, max 7)

## Summary

This iteration makes the python-setup linting package self-consistent and
production-complete per `.tmpoutput/lint-goal/goal.md`. The codebase already
has most custom checkers and a runner pipeline, but carries five load-bearing
defects that violate the goal and the project's own CodingRules:

1. **Masked checkers.** `pyi_underscore_checker` (W9707) is registered and
   `enable`d in `config/.pylintrc`, but `ignore-patterns=.*\.pyi$` means pylint
   never visits `.pyi` files — the rule is dead. The goal's accumulated
   feedback is explicit: "ALL CHECKS MUST BE EXECUTED, NO checks masked," and
   "we MUST retain ability to check pyi<->py."
2. **Internal self-contradiction.** `_base.py:check_if_meaningful` wraps a
   first-party import (`from python_setup_lint.checkers._semantic import …`)
   in `try/except ImportError: pass` — the exact pattern the project's own
   `no_try_import_checker` (W9001) bans, and a "fallback for a hard-declared
   dependency" that CodingRules.md prohibits. The first-party import can
   never raise ImportError, so the guard is impossible-case dead code.
3. **Semantic feature is half-built.** Tests `importorskip` the semantic
   path (goal says this is WRONG — all paths must be tested), there is no
   gitignored arg-keyed result cache in the runner path, and the embedder
   exists only as a quick-fail gate whose economics are marginal once a cache
   exists.
4. **Missing `.pyi` stubs** for `generic_key_dict_checker`,
   `suppression_justification_checker`, and `pyi_underscore_checker` —
   violating CodingRules' "Required for all other `.py` files."
5. **Docs/rules drift.** CodingRules.md is missing three tightened wordings
   the goal mandates; README has a stale `@v0.7.0`; version needs a bump;
   the minimum sample project and its single integration test under-sample
   the checker surface and do not `.gitignore` setup-generated files.

The plan decomposes into eight sequential workstreams. Each is independently
committable. Workstreams 1–4 are parallelizable (disjoint files); 5–8 have
light dependencies on earlier ones.

---

## Changes

### Workstream 1 — Unmask `.pyi` checking (run pylint twice)  ★ load-bearing

**Root cause:** `config/.pylintrc` has `ignore-patterns=.*\.pyi$`, and
`_find_py_files` in `cmd_build.py` globs `*.py` only. So `pyi_underscore_checker`
and any future `.pyi`-targeting checker never run.

**Decision (grounded):** Do NOT widen the single pylint pass to include
`.pyi`, because the stub-fidelity `StubChecker` reads `.pyi` directly via
`_resolve_stub` and compares in-memory — feeding pylint `.pyi` would create
the false-positive duplicates the prior iteration hit. Instead run **pylint
twice**: once on `.py` (current behavior, StubChecker active) and once on
`.pyi` only, with a `.pyi`-scoped rcfile that enables the `.pyi`-targeting
checkers (`pyi_underscore_checker`) and disables the `.py`-only/stub checkers
that would false-positive on stubs. Both passes feed the same baseline.

**Files:**
- `src/python_setup_lint/runner/cmd_build.py` — add `_find_pyi_files(dirs, *, cwd)`
  mirroring `_find_py_files` but globbing `*.pyi`.
- `src/python_setup_lint/runner/dispatch.py` — add a second `LintTool`
  strategy `_PylintPyiLintTool` (or a second `ToolSpec` entry "pylint-pyi")
  that builds a pylint command over `.pyi` files using a `.pyi`-scoped rcfile.
  Register it in `LINT_TOOLS`/`TOOLS` so it is part of the "all tools" count.
- `config/.pylintrc` — keep `ignore-patterns=.*\.pyi$` for the `.py` pass.
- `config/.pylintrc.pyi` (NEW) — a `.pyi`-only rcfile: `ignore-patterns=.*\.py$`,
  `load-plugins=python_setup_lint.checkers.conformance.pyi_underscore_checker`
  (and only the checkers that make sense on stubs), `enable=pyi-underscore-symbol`,
  disable the stub/conformance rules that are `.py`-only (beartype,
  no-try-import, structlog, tmp_path, asyncio_timeout, suppression-justification,
  unnamed-tuple, generic-key, stub.* , docstring).
- `src/python_setup_lint/runner/types.py` — if `RunnerConfig` needs a slot for
  the `.pyi` rcfile path, add it; else resolve it via `_resolve_pylintrc`
  sibling logic.
- `src/python_setup_lint/setup.py:_BUNDLED_CONFIGS` — add `.pylintrc.pyi` so
  consumers receive it.
- `tests/runner/test_lint_runner.py` — extend `TestStrategyBuildCommand` with
  cases for the `.pyi` pass (file expansion globs `*.pyi`, uses the `.pyi`
  rcfile).
- `tests/runner/test_real_pipeline_smoke.py:test_consolidated_real_pipeline_smoke`
  — add a `.pyi` with a planted `_`-symbol and assert the `pylint-pyi` tool
  emits W9707. Keeps the test non-slow (no model load).

**Acceptance:** Running `uv run lint` on the repo produces a `pylint-pyi`
section that reports `.pyi` violations; `pyi_underscore_checker` now actually
fires. `test_consolidated_real_pipeline_smoke` (non-slow) asserts it. No new
false-positive duplicates vs the `.py` pass.

### Workstream 2 — Remove the try/except ImportError self-contradiction  ★ load-bearing

**Decision (grounded):** Remove the `try/except ImportError` in
`_base.py:check_if_meaningful` entirely. Import `_semantic` unconditionally
(the module is first-party and always present). The semantic feature is gated
solely by config (env var / RunnerConfig), not by import fallback. This
satisfies CodingRules "remove fallbacks for hard-declared dependencies" and
removes the W9001 self-violation. `_semantic.semantic_check_if_meaningful`
already returns `None` when models are unavailable, so `_base.py` simply
checks the config flag → calls it → honors `None` by falling to the
heuristic.

**Files:**
- `src/python_setup_lint/checkers/_base.py` — replace the `try/except
  ImportError` block (lines ~88–107) with: a config-flag guard, then a plain
  `from python_setup_lint.checkers._semantic import
  semantic_check_if_meaningful as _semantic_check` at module top (or a guarded
  top-level import under `if TYPE_CHECKING` + a runtime import inside the
  config branch WITHOUT try/except). Add a `# noqa`/justification only if a
  genuine suppression remains (there should be none).
- `src/python_setup_lint/checkers/_semantic.py` — confirm
  `semantic_check_if_meaningful` returns `None` (not raises) when models
  unavailable; adjust if needed so the contract is "returns None → heuristic
  fallback."
- `tests/checkers/test_semantic_check.py` — update tests that asserted on
  the `try/except ImportError` path: the "fallback on import error" tests now
  test the "models unavailable → returns None → heuristic" path (patch
  `_semantic_check` to return `None`, not patch the import). Remove
  `pytest.importorskip` usage that was gating the semantic path (see
  Workstream 5 for the full test rewrite).

**Acceptance:** `no_try_import_checker` reports zero violations in
`_base.py`. `check_if_meaningful` still falls back to heuristic when models
are unavailable, proven by a unit test (no network).

### Workstream 3 — Add the three missing `.pyi` stubs + tighten CodingRules

**Files (stubs):**
- `src/python_setup_lint/checkers/conformance/generic_key_dict_checker.pyi`
  (NEW) — public surface: `GenericKeyDictChecker`, `register`.
- `src/python_setup_lint/checkers/conformance/suppression_justification_checker.pyi`
  (NEW) — public surface: `SuppressionJustificationChecker`, `register`.
- `src/python_setup_lint/checkers/conformance/pyi_underscore_checker.pyi`
  (NEW) — public surface: `PyiUnderscoreChecker`, `register`.
  - Each must have NO `_`-prefixed symbols (which, after Workstream 1, the
    `.pyi` pass will actually enforce — so these stubs must be clean).

**Files (CodingRules.md):** tighten three existing wordings to match the
goal exactly, keeping the existing semantic-compression style:
  - Generic-key dict: "If it is a bona fide generic, it must be a named type
    that defines what it is (`LintRuleId`). Otherwise enum, `Literal`, etc."
  - Unnamed-tuple dict values: "shall be a `NamedTuple`, dataclass, or
    `Protocol` where fields are named."
  - Suppression comments: "must carry a trailing technical-justification
    comment explaining why the rule is suppressed."
  - Add the explicit rule: "Tests import `_`-prefixed symbols only from the
    defining submodule, not the package `__init__`" if not already a
    standalone line (verify — explore reports it's present as a sentence
    within the Symbol Convention section; make it explicit).
  - Add the universal-exception line for tests-only parameter count if not
    standalone (explore reports it's present).

**Acceptance:** `mypy`/`pyright`/`stubtest` pass on the new stubs; the `.pyi`
pass (Workstream 1) finds no `_` symbols in the new stubs; CodingRules.md
contains all goal-mandated wordings.

### Workstream 4 — Semantic feature: reranker-only + arg-keyed cache + config

**Decision (grounded, PoC-gated):** Drop the embedder quick-fail gate and keep
only the reranker (`jina-reranker-v2-base-multilingual`) as the semantic
signal. Rationale: with an arg-keyed gitignored cache, the expensive reranker
call is paid once per unique (text, rule, code_context, comment); the embedder
only saves cost on the fraction it would filter, but its own model load
(~130MB) + inference is non-trivial and adds LoC. If a quick PoC shows the
embedder filters a large fraction at materially lower cost, keep it — but
default plan is reranker-only. The cache makes the consolidated smoke test
cheap (cache hit after first run) so it can stay non-slow.

**Files:**
- `src/python_setup_lint/checkers/_semantic.py`:
  - Remove `_load_embedder` and the embedder gate; keep `_load_reranker` +
    `semantic_check_if_meaningful`.
  - Add an **arg-keyed result cache** persisted to a gitignored path
    (`~/.cache/python-setup/semantic/results.json` already exists per explore
    — verify it's arg-keyed and idempotent; if not, make it keyed on a
    SHA-256 of `(text, rule, code_context, comment, model_id)` with load-on-
    init + save-on-mutation). Cache must be idempotent (same args → same
    result, no recompute).
  - Model loading uses the default Hugging Face cache dir; document
    pre-loading (see docs).
- `src/python_setup_lint/checkers/_base.pyi` and `_semantic.pyi` — update
  signatures if the embedder removal changes them.
- `pyproject.toml` — keep `semantic = ["sentence-transformers>=3.0.0"]`;
  ensure the `[semantic]` extra is the only place sentence-transformers is
  declared.
- `.gitignore` — confirm `.cache/python-setup/semantic/` is gitignored
  (explore says yes) and add the result-cache file if separate.
- `docs/semantic-justification.md` — add: how to enable/disable semantic
  (env var + future RunnerConfig), how to pre-load models as fallback
  (`python -c "from sentence_transformers import CrossEncoder;
  CrossEncoder('jinaai/jina-reranker-v2-base-multilingual')"`), cache
  location + how to clear it, and the seamless-dep story (install with
  `[semantic]` extra; without it, heuristic fallback; config-guarded on by
  default).

**Acceptance:** `semantic_check_if_meaningful` returns a stable result for
identical args across processes (cache hit). Heuristic fallback works with
the `[semantic]` extra absent. No `try/except ImportError` for
sentence_transformers at the `_base.py` boundary (the lazy load inside
`_semantic.py` is the only place it's touched, and it returns `None` on
failure).

### Workstream 5 — Semantic tests: all paths tested, no importorskip

The goal is explicit: tests must not `importorskip` the semantic path;
network-requiring tests require network; only cache-bypass tests may be
`@pytest.mark.slow`; `test_consolidated_real_pipeline_smoke` MUST NOT be slow.

**Files:**
- `tests/checkers/test_semantic_check.py` — rewrite:
  - Heuristic-fallback tests: patch `_semantic_check` to return `None`
    (models-unavailable contract), no network.
  - Semantic-path tests: require network (model available). Mark with a
    network marker (e.g. `@pytest.mark.with_real_api` per CodingRules test
    categories). These run when sentence-transformers + network present.
  - Cache-bypass tests: mark `@pytest.mark.slow` (force cache miss → model
    load). Cache-hit tests (run once to warm cache, then assert cache hit)
    are NOT slow once cache is warm — but the warm-up may be slow; structure
    so the warm-up is a session fixture marked slow-separated, and the cache-
    hit assertion is fast.
  - Remove every `pytest.importorskip("sentence_transformers")`.
- `tests/conftest.py` — add a session fixture that pre-loads the reranker
  model once (marked appropriately) and a fast "is model available" check
  used to skip network tests cleanly when the `[semantic]` extra is absent —
  but the skip must be a clear network/extra skip, NOT importorskip-as-
  fallback. Per goal: "Test need to require network if we use sentence
  transformer." So if extra absent → skip with reason "network required,"
  not silently fall back.
- `pyproject.toml` `[tool.pytest.ini_options]` — ensure markers include the
  network/slow split per goal. `addopts = "-m 'not slow'"` stays.

**Acceptance:** `pytest -m "not slow"` runs all heuristic + cache-hit +
non-network semantic tests. `pytest -m slow` runs cache-bypass/model-load
tests. No `importorskip`. The semantic path is exercised when the extra is
installed (network available).

### Workstream 6 — Minimum sample project + single integration test (full coverage)

**Goal:** a simple python project (not part of project linting) with planted
violations for ALL custom-linter-checked rules + 1–2 per tool/critical rule, a
list of violations, tested by a single large `test/integration.py` covering:
setup new (run linter, check violations, check all tools run), check setup
correct, edit configs (rules overlay, check lint result), check
resetup/update, dry-run git hooks. `.gitignore` everything setup adds.

**Files:**
- `test/data/minimal_sample_project/src/minimal_sample/mod.py` — extend with
  planted violations for EVERY checker currently missing: all StubChecker
  rules (E97A0–E97B5, I97B6) via a companion `mod.pyi` that mismatches, the
  `use-structured-logging` (W9711) case, and the
  `internal-helper-docstring-allowed` (W9706) case. Keep 1–2 per critical
  rule.
- `test/data/minimal_sample_project/src/minimal_sample/mod.pyi` — add
  mismatches + one `_`-prefixed symbol (now actually caught by Workstream 1's
  `.pyi` pass).
- `test/data/minimal_sample_project/violations.txt` — expand to the full list
  of expected violation symbols (regex per line), one per planted violation.
- `test/data/minimal_sample_project/pyproject.toml` — ensure it declares the
  `[semantic]` extra is NOT required for the sample (sample uses heuristic
  fallback) so the integration test is network-free.
- `test/integration.py` — extend the existing `TestInstallAndLint`,
  `TestPlantedViolations`, `TestOverlayConfig`, `TestResetup`, `TestGitHooks`
  to cover: (a) all tools run (assert each of the N tool sections appears),
  (b) setup correct (assert `.python-setup-state.json` + copied configs
  present), (c) the full planted-violations list is detected, (d) overlay
  edit changes the lint result, (e) resetup/update is idempotent, (f)
  dry-run git hooks behave as expected. Keep it a single large test file.
- `test/data/minimal_sample_project/.gitignore` (NEW or extend root
  `.gitignore` with sample-project-scoped entries) — ignore everything setup
  adds to the sample: `.pre-commit-config.yaml`, `lint.baseline`,
  `.secrets.baseline`, `pyrightconfig.json`, `mypy.ini`, `.pylintrc`,
  `ruff.toml`, `rumdl.toml`, `ty.toml`, `.yamllint`, `config/`,
  `.python-setup-state.json`, `CodingRules.md`. The root `.gitignore` already
  has most; verify the sample dir is covered and the committed planted source
  is excepted (`!/test/data/minimal_sample_project/`).

**Acceptance:** `test/integration.py` (non-slow, network-free) asserts the
full planted violation set is reported by `uv run lint` on the sample, all
tool sections appear, overlay edit changes results, resetup is idempotent,
dry-run hooks pass. `git status` on the sample shows only committed planted
source.

### Workstream 7 — Optimize non-slow test runtime <30s + private-imports guard

**Files:**
- `tests/runner/test_real_pipeline_smoke.py` — confirm
  `test_consolidated_real_pipeline_smoke` is NOT slow (it isn't) and that it
  stays fast (it runs the full pipeline; ensure it uses cache where semantic
  is involved — Workstream 4 makes this cheap).
- Profile the non-slow suite (`pytest -m "not slow" --durations=20`) and move
  any test that spawns heavy subprocesses or model loads but isn't already
  `slow` into `slow` ONLY if it is a model-load/cache-bypass test. Do NOT mark
  the consolidated smoke slow.
- `tests/runner/test_runner_private_imports.py` — verify it asserts
  `runner.__all__` has no `_`-prefixed names and that tests import `_`
  symbols from defining submodules (explore says it does). Tighten if the
  CodingRules wording from Workstream 3 adds new expectations.

**Acceptance:** `time pytest -m "not slow"` < 30s. `test_consolidated_real_
pipeline_smoke` is in the non-slow run and passes.

### Workstream 8 — Version bump, README, CHANGELOG, DoD sweep

**Files:**
- `pyproject.toml` — bump `version` 0.8.0 → 0.9.0.
- `README.md` — fix the stale `@v0.7.0` reference (line ~46) to `@v0.9.0`;
  keep short and user-focused; confirm overlays/custom-checks/semantic link
  to `docs/` (they do).
- `CHANGELOG.md` — add a `v0.9.0` entry (user-visible changes only: new
  `.pyi` lint pass, semantic reranker-only + cache, CodingRules tightening,
  integration test coverage).
- `AGENTS.md` — verify it stays a short index linking out (explore says it
  does); update any architecture pointers if the `checkers/` layout changed
  (it doesn't in this plan).
- `docs/overlays.md` — expand if thin (explore says thin) with re-baselining
  commands and the new `.pyi` pass overlay.
- DoD sweep: run `uv run lint` on the repo; reconcile `lint.baseline` so that
  the only remaining violations are explicit, justified exceptions (test
  parameter count per the universal exception; any `pyi` vs `py`
  justified exceptions). No bare suppressions without justification.

**Acceptance:** Version 0.9.0 consistent across `pyproject.toml`, README,
CHANGELOG. `uv run lint` self-passes with only justified exceptions in the
baseline. README short, user-focused, links to `docs/`.

---

## Sequence

```
WS1 (unmask .pyi) ──┐
WS2 (try/except)  ──┼─→ WS5 (semantic tests) ──→ WS6 (sample+integration) ──→ WS7 (perf) ──→ WS8 (release)
WS3 (stubs+rules) ──┤                                              ↑ depends on WS1 (.pyi pass) + WS4 (cache)
WS4 (semantic)    ──┘
```

- **WS1, WS2, WS3, WS4 run in parallel** (disjoint files; WS3's new stubs are
  checked by WS1's `.pyi` pass so sequence WS3 after WS1 if the stubs would
  otherwise self-violate — but new stubs are clean by construction, so
  parallel is safe; verify at merge).
- **WS5 depends on WS2 + WS4** (the test rewrite reflects the removed
  try/except and the reranker-only + cache design).
- **WS6 depends on WS1 + WS4** (integration test exercises the `.pyi` pass
  and the cached semantic path).
- **WS7 depends on WS5 + WS6** (perf measured on the final test shape).
- **WS8 is last** (version/docs after all functional work).

---

## Edge Cases

- **`.pyi` pass false positives:** the `.pyi`-scoped rcfile must disable every
  checker that operates on `.py` semantics (beartype, no-try-import,
  structlog, tmp_path, asyncio-timeout, suppression-justification,
  unnamed-tuple, generic-key, stub.*, docstring). Verify by running the
  `.pyi` pass over the repo's own `.pyi` files and confirming only
  `pyi-underscore-symbol` (and any genuinely `.pyi`-valid rules) fire.
- **Stubtest interaction:** adding `.pylintrc.pyi` to `_BUNDLED_CONFIGS` must
  not break `mypy.stubtest` (it only checks stubs vs impl; an extra rcfile is
  inert to it). Verify.
- **Cache idempotency:** the arg-keyed cache must be stable across processes
  (same args → same result, no duplicate model loads). The cache file must be
  safely concurrent-read (tests run in parallel) — use atomic read + write.
- **Semantic extra absent in CI:** the non-slow test suite must run with the
  `[semantic]` extra absent and pass (heuristic path). Network tests skip
  cleanly with a "network required" reason, not silent fallback.
- **Sample project not part of project linting:** ensure `config/.pylintrc`
  `ignore-paths` and the runner's source-roots exclude
  `test/data/minimal_sample_project` from the repo's own self-lint (it
  already ignores `tests/data/` — verify the sample path is covered; if not,
  add `test/data/` to `ignore-paths`).
- **Universal exception for tests:** the goal wants a universal exception for
  test parameter count. CodingRules already has it; ensure no checker
  (e.g. `too-many-arguments`) is enabled in a way that flags tests —
  `.pylintrc` disables `too-many-arguments`, so this is satisfied; verify.
- **`test_consolidated_real_pipeline_smoke` must stay non-slow:** any
  semantic involvement in it must use the cache (warm on first run in the
  session) so it never triggers a model load.

---

## Verification

1. `uv run lint` on the repo passes (self-linting) with only justified
   baseline exceptions.
2. `pytest -m "not slow"` — all green, < 30s, includes
   `test_consolidated_real_pipeline_smoke` (non-slow) which asserts the
   `.pyi` pass emits W9707.
3. `pytest -m slow` — cache-bypass / model-load tests green when the
   `[semantic]` extra + network present; clean skip with reason otherwise.
4. `test/integration.py` (non-slow, network-free) asserts the full planted
   violation set across ALL custom checkers + all tool sections + overlay +
   resetup + dry-run hooks.
5. `grep -rn "try/except ImportError" src/python_setup_lint/checkers/_base.py`
   returns nothing; `no_try_import_checker` reports zero self-violations.
6. New `.pyi` stubs exist and pass `stubtest` + the `.pyi` pylint pass.
7. `git status` on `test/data/minimal_sample_project` after setup shows only
   committed planted source (setup artifacts gitignored).
8. Version 0.9.0 consistent in `pyproject.toml`, README, CHANGELOG.

---

## Critical Files (implementer must read)

- `.tmpoutput/lint-goal/goal.md` — the full goal with accumulated feedback.
- `CodingRules.md` — the rules being enforced/tightened (read fully).
- `pyproject.toml` — version, extras, pytest markers, bundled configs.
- `config/.pylintrc` — current `ignore-patterns=.*\.pyi$`, `load-plugins`,
  `enable`/`disable` lists.
- `src/python_setup_lint/runner/cmd_build.py` — `_find_py_files`,
  `_resolve_pylintrc`, `_build_command`.
- `src/python_setup_lint/runner/dispatch.py` — `TOOLS`, `LINT_TOOLS`,
  `_PylintLintTool` strategy.
- `src/python_setup_lint/checkers/_base.py` — `check_if_meaningful`,
  `MessageDef`, `LintRuleId` (the try/except to remove).
- `src/python_setup_lint/checkers/_semantic.py` — embedder/reranker, cache.
- `src/python_setup_lint/checkers/conformance/no_try_import_checker.py` —
  W9001 + the `_OPTIONAL_IMPORT_PATTERNS` exemption set.
- `src/python_setup_lint/checkers/conformance/pyi_underscore_checker.py` —
  the dead checker Workstream 1 revives.
- `src/python_setup_lint/setup.py` — `_BUNDLED_CONFIGS`,
  `_discover_checkers`, install/update steps.
- `test/data/minimal_sample_project/` — current sample (mod.py, mod.pyi,
  violations.txt, pyproject.toml).
- `test/integration.py` — current integration test classes.
- `tests/checkers/test_semantic_check.py` — current importorskip tests to
  rewrite.
- `tests/runner/test_real_pipeline_smoke.py` — consolidated smoke (non-slow).
- `.gitignore` — current gitignored artifacts.
- `docs/semantic-justification.md`, `docs/overlays.md`, `docs/custom-checks.md`.
