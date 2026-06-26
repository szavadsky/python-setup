# lint-goal — Iteration 2 Plan

## Summary

Iteration 1 declared all 8 workstreams complete, but a skeptical re-review
found that the prior work left a class of **higher-priority self-consistency
gaps** that contradict the project's own DoD ("all linting violations fixed
except a small number explicitly expected") and the very rules WS-7 was built
to enforce. The two items the summary explicitly flagged as "remaining"
— the NLP semantic experiment (WS-7.2) and the WS-2.3 default-suite subprocess
audit — are real but **lower priority**: the semantic track is explicitly an
opt-in research experiment, and the current run is already under the 30s
target (25.97s).

This plan therefore **re-prioritizes**: it first closes the self-consistency
gaps that the linter would flag in its own codebase, then completes the two
nominated remaining items. It is scoped to leave the project "perfectly
functional … code well organized, LoC minimized, no linting violations except
small number explicitly expected" as the DoD requires.

## Findings from re-review (evidence basis)

From the read-only scouts (PlanAgent2.MeaningfulScout, PerfAuditScout,
QualityScout, CodeQuoteScout, DetailScout):

1. **Bare suppressions across `src/`** — ~19 comment lines carry `# noqa: …`,
   `# type: ignore[…]`, or `# pylint: disable=…` with **no technical
   justification** text, e.g. `src/python_setup_lint/checkers/_base.py:16`
   (`# noqa: TC002`), `…/runner/baseline.py:7`, `…/conformance/beartype_checker.py:15`,
   `…/conformance/suppression_justification_checker.py:50`
   (`# type: ignore[union-attr]`), plus 8 checker modules, `_autofix.py`,
   `_cli_complexity.py`, `parsers.py`, `testing.py`, `setup.py`. WS-7 built a
   checker to *require* justification but the codebase itself violates it.
2. **3 new checkers not registered** — `config/.pylintrc` `load-plugins` lists
   only 6 checkers. `suppression_justification_checker`,
   `unnamed_tuple_dict_checker`, and `generic_key_dict_checker` are NOT in the
   list, so the linter does not enforce them on its own code. They have
   `register(linter)` functions and are auto-discoverable by `setup.py`, but the
   project's own config doesn't load them.
3. **`suppression_justification_checker` msgs not migrated** — its `msgs` dict
   still uses the OLD tuple format; WS-5's `MessageDef` migration skipped this
   one checker (the newest). The other two new checkers use `MessageDef`.
4. **`check_if_meaningful` ignores its inputs** — signature accepts
   `rule`, `code_context`, `comment` keyword params but the body never reads
   them; it is a pure length-floor + boilerplate-set heuristic. This is the
   stub the NLP experiment is meant to replace/extend.
5. **`_base.pyi` missing `check_if_meaningful`** — the type stub is out of sync
   with `_base.py`.
6. **`__init__.py` missing `__version__`** — version bumped to 0.7.0 in
   pyproject/CHANGELOG but not exposed at runtime.
7. **WS-2.3 hidden subprocess cost (real, but non-blocking)** — default suite
   contains: 7 real `python -m pylint` subprocesses via
   `tests/checkers/_factories.py:_run_pylint` (stub checker integration tests,
   NOT marked `slow`); 10+ `uv add python-setup` subprocesses via
   `tests/runner/test_setup_install.py` + `tests/runner/test_setup.py` +
   `tests/conftest.py:configured_project` (function-scoped, paid per test);
   2 real `pyright --outputjson` subprocesses in
   `tests/runner/test_t9_7_compose_pyright_live.py` (gated on pyright install,
   NOT marked `slow`); real `git` subprocesses in autofix tests via
   `tests/runner/_autofix_helpers.py`. Current 25.97s is under target, so this
   is optimization, not correction.

---

## Changes

### Track A — Self-consistency / DoD closure (HIGH priority)

**A1. Add technical-justification comments to all bare suppressions in `src/`.**
Files & line evidence from the review:
- `src/python_setup_lint/checkers/_base.py:16` — `# noqa: TC002`
- `src/python_setup_lint/checkers/conformance/beartype_checker.py:15`
- `…/conformance/asyncio_timeout_checker.py:20`
- `…/conformance/generic_key_dict_checker.py:21`
- `…/conformance/no_try_import_checker.py:12`
- `…/conformance/structlog_checker.py:9`
- `…/conformance/tmp_path_checker.py:15`
- `…/conformance/unnamed_tuple_dict_checker.py:17`
- `…/conformance/suppression_justification_checker.py:50` — `# type: ignore[union-attr]`
- `…/stub/checker.py:15`, `…/stub/docstring_checker.py:17`
- `…/stub/coverage.py:10`, `…/stub/normalizer.py:10`
- `src/python_setup_lint/runner/_autofix.py:25-26`
- `src/python_setup_lint/runner/_cli_complexity.py:10`
- `src/python_setup_lint/runner/baseline.py:7`
- `src/python_setup_lint/runner/parsers.py:20,29`
- `src/python_setup_lint/testing.py:24,164-165`
- `src/python_setup_lint/setup.py:182`
- `…/conformance/suppression_justification_checker.py:34` (msgs tuple format — see A3)

Each bare suppression becomes a comment stating *why* the rule is suppressed
(e.g. `# noqa: TC002  # pylint imports pylint.lint only for type checking at runtime`).
Use the exact justification style the CodingRules already mandate. This is the
single largest DoD violation.

**A2. Register the 3 new checkers in `config/.pylintrc`.**
Add `python_setup_lint.checkers.conformance.suppression_justification_checker`,
`python_setup_lint.checkers.conformance.unnamed_tuple_dict_checker`, and
`python_setup_lint.checkers.conformance.generic_key_dict_checker` to the
`load-plugins =` line so the linter enforces them on its own code. Confirm no
new violations surface from A1 (the justification comments should satisfy the
suppression checker).

**A3. Migrate `suppression_justification_checker` `msgs` to `MessageDef`.**
In `…/conformance/suppression_justification_checker.py`, convert the `msgs`
dict (currently old tuple format) to `MessageDef` named tuples, matching the
form used in `unnamed_tuple_dict_checker.py` and `generic_key_dict_checker.py`.
This completes WS-5's migration consistently.

**A4. Implement the unused `check_if_meaningful` params (or document them out).**
`check_if_meaningful(rule, code_context, comment)` accepts `rule`,
`code_context`, `comment` but the body ignores all three. Either (a) wire the
existing heuristic to actually consume them where useful, or (b) drop the
unused params to avoid a stub-shaped API. Decision rule: if Track B (NLP) is
implemented, these params become the seam for the embedder/reranker, so keep
them and have the heuristic use `comment` at minimum. If Track B is deferred,
drop `rule`/`code_context` and keep only `comment` to avoid lying in the
signature. The plan executes Track B, so **keep the params and make the
heuristic use `comment`**; the NLP path slots behind the same signature.

**A5. Add `check_if_meaningful` to `_base.pyi`.**
Declare the function in `src/python_setup_lint/checkers/_base.pyi` with the
real signature (matching `_base.py` post-A4) so type checkers see it.

**A6. Expose `__version__` in `src/python_setup_lint/__init__.py`.**
Add `__version__ = "0.7.0"` (read from package metadata via
`importlib.metadata.version("python-setup")` is preferred over a literal, to
keep a single source of truth). Keeps runtime version consistent with
pyproject 0.7.0.

### Track B — NLP semantic experiment, WS-7.2 (NOMINATED remaining item)

**B1. Add `[semantic]` optional-dependency extra to `pyproject.toml`.**
In `[project.optional-dependencies]` (currently only `dev`), add a `semantic`
extra with `sentence-transformers` (provides both the BGE embedder and the
Jina cross-encoder reranker via `CrossEncoder`). This is the opt-in gate: the
embedder/reranker code path imports these only when the extra is installed.

**B2. Implement a two-stage `check_if_meaningful` semantic backend.**
New module `src/python_setup_lint/checkers/_semantic.py` (opt-in):
- **Stage 1 — embedder**: `BAAI/bge-small-en-v1.5` via
  `sentence_transformers.SentenceTransformer`. Embeds the justification
  `comment` and a small set of "meaningful technical-justification" reference
  phrases; computes cosine similarity.
- **Stage 2 — reranker**: `jinaai/jina-reranker-v2-base-multilingual` via
  `sentence_transformers.CrossEncoder`. Reranks the candidate justification
  against the reference set for a final relevance score.
- A threshold (configurable, e.g. cosine ≥ 0.55 / rerank ≥ 0.5) decides
  "meaningful". Lazy-load models on first call; cache the model instances.

Design: `check_if_meaningful` keeps its current heuristic as the **default**
zero-dependency path; the semantic backend is selected when
`sentence_transformers` is importable (i.e. the `[semantic]` extra installed)
**and** an opt-in flag/env (`PYTHON_SETUP_LINT_SEMANTIC=1`) is set. Otherwise
fall back to the existing heuristic so default installs/tests are unchanged.
This preserves the "opt-in, gated behind `[semantic]`" requirement.

**B3. Make the semantic path import-safe and lazy.**
All `sentence_transformers` imports are inside the function / a lazy loader so
that without the extra, `import python_setup_lint` never imports it. Guard with
`ImportError` → fallback to heuristic. Models download on first use (cache in
HF cache); tests must not require network.

**B4. Tests for the semantic backend.**
- Unit tests gated on `sentence_transformers` being importable (use
  `pytest.importorskip("sentence_transformers")`); these are marked
  `@pytest.mark.slow` (model load/download) so they never run in the default
  suite.
- The default path (heuristic) keeps its existing 9 cases unchanged and
  passing.
- Add a test asserting that without the extra, `check_if_meaningful` falls back
  to the heuristic (import-safe).

**B5. Document the experiment.**
Add a short note to `docs/custom-checks.md` (or a new
`docs/semantic-justification.md`) describing the two-stage approach, the
opt-in mechanism, model choices (bge-small-en-v1.5, jina-reranker-v2), and that
this is a research track. Note results/threshold rationale once measured.

### Track C — WS-2.3 default-suite subprocess audit (NOMINATED remaining item)

**C1. Mark the pyright-live tests `slow`.**
`tests/runner/test_t9_7_compose_pyright_live.py` (lines ~130, ~172) runs real
`pyright --outputjson` subprocesses (~3s each) but is only gated on pyright
being installed — NOT marked `slow`. Add `@pytest.mark.slow` to these tests
(or the class) so the default suite stops paying pyright cost. This is the
clearest "expensive test not marked slow" case.

**C2. Audit and gate the remaining hidden-subprocess default tests.**
Rank from the perf scout, and apply `@pytest.mark.slow` where the cost is real
and the test is not fast-path-critical:
- `tests/checkers/_factories.py:_run_pylint` consumers —
  `test_stub_checker_class.py:test_integration_class_fidelity` (5 cases),
  `test_stub_checker_callable.py:test_integration_callable` (2 cases): real
  pylint subprocesses. Mark these integration tests `slow`; keep any pure
  in-process logic variants in the default suite.
- `tests/runner/test_setup_install.py:test_artifacts` (+ 2 related) and
  `test_setup.py:test_install`/`test_install_default_cwd`: real `uv add
  python-setup` subprocesses. Mark the install-path tests `slow`.
- `tests/conftest.py:configured_project` (function-scoped, runs `install()`
  → `uv add` per test): evaluate whether to make it `session`-scoped or mark
  dependent tests `slow`. Prefer session-scoping the fixture to amortize the
  install across the 7 dependent tests (bigger win than marking slow).

**C3. Verify the non-slow run stays under 30s and the slow tests still pass.**
After C1/C2, run `pytest -m 'not slow'` (target <30s, ideally faster than
25.97s since pyright + some install tests are now gated) and `pytest` (all,
target green). Re-measure and record the new default-suite time in the
iteration-2 summary.

---

## Sequence

1. **A1** (justify all bare suppressions) — independent, do first; it is the
   largest DoD gap and unblocks A2's verification.
2. **A2** (register 3 checkers in `.pylintrc`) + **A3** (migrate msgs to
   `MessageDef`) — after A1, so registering the suppression checker doesn't
   immediately fail on the codebase's own bare comments. A2/A3 are independent
   of each other and can be parallelized.
3. **A4/A5/A6** (wire `check_if_meaningful` params; update `.pyi`; `__version__`)
   — independent of A1–A3; parallelize.
4. **Track B** (semantic backend) — depends on A4's signature decision (keep
   the params). B1 (pyproject extra) first, then B2/B3 (module + lazy import),
   then B4 (tests), then B5 (docs). B is the bulk of new code.
5. **Track C** (perf audit + slow-marking) — fully independent of A and B;
   parallelize from the start. C2's `configured_project` session-scoping is
   the highest-leverage item.
6. **Final verification pass** — run the full suite, confirm DoD: non-slow
   <30s, all green, no unjustified suppressions in `src/`, 3 new checkers
   registered and self-passing, `__version__` correct.

Parallelization: Track A items, Track B, and Track C touch disjoint files
(except `_base.py` shared by A4/B2 and `.pylintrc` shared by A2 only) and can
largely run concurrently. Sequence only the A1→A2 dependency and the
A4→B2 signature dependency.

---

## Edge Cases & Error Conditions

- **NLP model download / network in CI**: B2/B3 must never require network for
  the default suite. Models download on first *opt-in* use only; tests use
  `pytest.importorskip` + `@pytest.mark.slow` + skip if no network. If
  download fails, fall back to the heuristic (never raise on missing models in
  the non-opt-in path).
- **`sentence_transformers` not installed**: the `[semantic]` extra is absent
  on default installs. `check_if_meaningful` MUST import-safe-fallback to the
  heuristic; an `ImportError` must not propagate. B3 guards this.
- **Circular import risk**: `_semantic.py` importing `sentence_transformers`
  at module top would break default installs. Imports MUST be inside the
  function or a lazy loader.
- **A1 over-suppression**: justification comments must be truthful and
  specific, not boilerplate ("needed for X") — the suppression checker itself
  should pass on them; if the checker's "meaningful" heuristic rejects a
  truthful but terse comment, tune the heuristic in A4 to accept genuine
  technical justifications.
- **C2 session-scoped `configured_project`**: changing scope from function to
  session risks test cross-contamination if tests mutate the installed state.
  Verify each dependent test is read-only w.r.t. the installed project, or
  scope the fixture per-class instead of session.
- **Marking tests `slow` shrinks the default suite** — ensure the gated tests
  are not silently untested in CI; CI should run the full suite separately
  (the `slow` marker only deselects the fast `-m 'not slow'` path).
- **`__version__` source of truth**: prefer `importlib.metadata.version` so
  pyproject is the single source; a literal `__version__` drifts from
  pyproject on the next bump.
- **`MessageDef` migration (A3)**: ensure the migrated `msgs` still matches the
  checker's `add_message` message IDs; a malformed `MessageDef` would break
  checker registration.

---

## Verification

1. **DoD / self-consistency**: run the linter (with the 3 new checkers now in
   `.pylintrc`) over `src/` and `tests/` — expect zero unjustified
   suppressions and zero new violations. Confirm the suppression checker
   passes on the A1 justification comments.
2. **Full suite green**: `pytest` (all tests including `slow`) passes —
   987 prior + new semantic/perf tests, all green.
3. **Default suite time**: `pytest -m 'not slow'` < 30s; record the new time
   (target: faster than 25.97s after C1/C2 gating).
4. **Semantic opt-in**: with `semantic` extra installed and
   `PYTHON_SETUP_LINT_SEMANTIC=1`, `check_if_meaningful` uses the
   embedder+reranker (unit tests pass under `@pytest.mark.slow`); without the
   extra, it falls back to the heuristic (default-path test passes, no
   network/import error).
5. **Import-safety**: `python -c "import python_setup_lint"` succeeds in a
   bare env without the `semantic` extra (no `sentence_transformers`
   import attempted).
6. **Type stub**: `pyright`/`mypy` over `src/` shows no missing-declaration for
   `check_if_meaningful` (A5); `__version__` resolvable (A6).
7. **Checker registration**: the 3 new checkers appear in the linter's loaded
   plugins and emit their message IDs on the planted violations in
   `test/data/minimal_sample_project` (WS-3 integration test still green).

---

## Critical Files

Implementer MUST read these before editing:

- `src/python_setup_lint/checkers/_base.py` — `check_if_meaningful`,
  `MessageDef`, `LintRuleId`, the bare `# noqa` line (A1/A4/A5).
- `src/python_setup_lint/checkers/conformance/suppression_justification_checker.py`
  — sole caller of `check_if_meaningful`; `msgs` tuple format (A3);
  `_is_suppression_line` / `_has_justification` (A1 tuning).
- `src/python_setup_lint/checkers/_base.pyi` — type stub missing
  `check_if_meaningful` (A5).
- `pyproject.toml` — `[project]` version 0.7.0, `[project.optional-dependencies]`
  (only `dev`), `[tool.pytest.ini_options]` `addopts`/`markers` (B1/C markers).
- `config/.pylintrc` — `load-plugins` lists 6 checkers, missing the 3 new ones
  (A2).
- `src/python_setup_lint/setup.py:79-110` — `_discover_checkers()`
  (registration contract; how `setup.py` writes load-plugins for consumers).
- `src/python_setup_lint/__init__.py` — missing `__version__` (A6).
- `src/python_setup_lint/checkers/conformance/unnamed_tuple_dict_checker.py`
  and `…/generic_key_dict_checker.py` — `MessageDef` form reference (A3).
- `tests/checkers/_factories.py` — `_run_pylint` subprocess helper (C2).
- `tests/conftest.py:~52` — `configured_project` fixture (C2 session-scoping).
- `tests/runner/test_t9_7_compose_pyright_live.py` — pyright subprocess tests
  (C1).
- `test/integration.py` — WS-3 E2E (marked `slow`); confirm still green after
  A2 registers new checkers.
- The bare-suppression sites enumerated in A1 (19 lines across
  `src/python_setup_lint/`).

---

## Priority & Scope Note

- **Track A (self-consistency/DoD) is mandatory** — it closes violations the
  project's own linter would flag, directly satisfying the DoD. It is mostly
  mechanical (comment authoring + registration + small migrations).
- **Track B (NLP experiment) is the nominated research item** — opt-in,
  lazy, never affects default installs/tests; delivered behind the
  `[semantic]` extra. The heuristic remains the default path.
- **Track C (perf audit) is the nominated optimization item** — current run is
  already under target, so C is about correctness of the `slow` boundary
  (expensive tests should be gated), not about hitting the target. Highest
  leverage is session-scoping `configured_project` + marking pyright-live slow.

If scope must shrink under time pressure, the order to drop is C (already
under target) → B (opt-in research) → keep A (DoD-critical).
