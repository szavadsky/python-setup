# lint-goal — Iteration 3 Plan

## Summary

Iterations 1 and 2 both declared the DoD satisfied with only the opt-in NLP
experiment (Track B) remaining. A grounded re-audit of the actual codebase
contradicts that: **three rule-ID collisions** introduced by prior iterations
make the linter crash on its own project — a direct DoD violation ("perfectly
functional"). A read-only audit found these functional defects plus two
lower-priority self-consistency gaps. This plan fixes the functional bugs first
(Track D), closes the remaining self-consistency gaps, then — if scope allows —
pursues the opt-in NLP experiment (Track B). The project is **not** complete;
meaningful, DoD-blocking work remains.

### Evidence basis (read-only scouts)

- **CollisionImpactScout**: `config/.pylintrc` `load-plugins` loads all 9
  checkers in one pylint invocation; pylint 4.x raises on duplicate msgid.
  `setup.py:_discover_checkers` auto-loads all checkers into consumer projects
  too. No mitigation exists.
- **DoDSelfConsistencyScout**: bare `# type: ignore[union-attr]` in the
  justification checker itself; CodingRules.md missing the universal-test-
  exception bullet.
- **TrackBStatusScout**: Track B entirely unimplemented (no `_semantic.py`,
  no `[semantic]` extra, no `sentence_transformers`/`bge`/`jina` anywhere).

---

## Track D — Functional correctness fixes (HIGHEST priority, DoD-blocking)

### D1. Fix the three rule-ID collisions

Three pairs of checkers define the same pylint message ID. Because all are
loaded together, pylint crashes at registration. Renumber the **newer**
definitions (the ones iteration 1 introduced) onto free IDs, keeping the
original pre-existing IDs stable.

**Collision inventory** (verified verbatim):

| Msgid | Checker A (original — keep) | Checker B (newer — renumber) | New ID for B |
|-------|------------------------------|-----------------------------|--------------|
| W9701 | `conformance/beartype_checker.py:27` `missing-beartype` | `stub/docstring_checker.py:82` `generic-return-requires-returns` | **W9705** |
| W9702 | `conformance/tmp_path_checker.py:25` `tempfile-mkdtemp-in-test` | `stub/docstring_checker.py:89` `internal-helper-docstring-allowed` | **W9706** |
| W9720 | `conformance/unnamed_tuple_dict_checker.py:27` `unnamed-tuple-dict-value` | `conformance/generic_key_dict_checker.py:42` `generic-key-dict` | **W9721** |

Free IDs confirmed unused by full `src/python_setup_lint/checkers/` inventory:
W9700, W9703, W9704, W9710, W9711, W9001 are taken; **W9705, W9706, W9707,
W9721+** are free.

**Changes:**
1. `src/python_setup_lint/checkers/stub/docstring_checker.py:82` — change
   `"W9701"` → `"W9705"` (keep symbol `generic-return-requires-returns`).
2. `src/python_setup_lint/checkers/stub/docstring_checker.py:89` — change
   `"W9702"` → `"W9706"` (keep symbol `internal-helper-docstring-allowed`).
3. `src/python_setup_lint/checkers/conformance/generic_key_dict_checker.py:42`
   — change `"W9720"` → `"W9721"` (keep symbol `generic-key-dict`).
4. **Update every reference to the renumbered IDs**: search `tests/` and
   `src/` for the string literals `"W9701"`, `"W9702"`, `"W9720"` in contexts
   that target the docstring/generic-key rules (NOT the beartype/tmp_path rules,
   which keep those IDs). Use LSP `references` / `search` to find: assertion
   strings in `tests/checkers/test_stub_docstring_checker.py`,
   `tests/checkers/test_generic_key_dict_checker.py`, any planted violations
   in `test/data/minimal_sample_project/` and its `violations.txt`, and any
   baseline entries (`lint.baseline` or `test/data/.../lint.baseline`).
5. **Update `_base.pyi`** if any renumbered ID appears in stub declarations.

**Why renumber the newer ones:** beartype_checker and tmp_path_checker are
foundational, long-standing checkers whose IDs may be referenced by baselines
and consumer configs. The docstring rules and generic-key rule were added in
iteration 1; renaming those minimizes external breakage.

**Depends on:** nothing. Do first.

### D2. Fix the bare suppression in the justification checker itself

`src/python_setup_lint/checkers/conformance/suppression_justification_checker.py:50`
contains a bare suppression — the checker that enforces justification has an
unjustified suppression itself. Verbatim:

```python
    def visit_module(self, node: object) -> None:
        """Walk the module's source lines looking for bare suppressions."""
        try:
            stream = node.stream()  # type: ignore[union-attr]
        except (AttributeError, OSError):
            return
```

The `node: object` param is typed `object` (the real astroid module node has
`.stream()`, but the signature uses `object` to avoid importing astroid at the
type level). Add a trailing justification:

```python
            stream = node.stream()  # type: ignore[union-attr]  # astroid Module.stream() not in object type; runtime check guards AttributeError
```

This satisfies the checker's own rule (trailing reason comment that
`check_if_meaningful` accepts). Verify the checker no longer flags its own
file.

**Depends on:** nothing. Independent of D1.

### D3. Add the universal-test-exception CodingRules bullet (goal req #11)

Goal requirement #11: *"specify universal exception number of parameters for
test only."* The DoD scout confirmed CodingRules.md has **no** such rule. The
Tests section (`CodingRules.md:238-324`) has subsections: Metrics, Mocking
Strategy, Test Categories, Coverage, Test Code Quality, Naming, Isolation,
Fixture Scope, conftest.py Scope.

**Change:** add a bullet to the **Test Code Quality** subsection (the natural
home for test-only relaxations), matching the dense-bullet style. The rule
exempts test functions from the parameter-count / complexity heuristics that
apply to production code — tests may legitimately take many fixtures/params:

```markdown
- Test functions are exempt from the max-argument-count heuristic that applies
  to production code; tests may legitimately accept many fixtures/params.
  This is the universal test-only exception — it does NOT extend to production
  or `_`-prefixed helper code.
```

**Depends on:** nothing.

---

## Track B — NLP semantic experiment, WS-7.2 (LOWEST priority, opt-in)

Per the goal: *"Experiment with best way checkIfMeangful given our code base —
try some NLP not LLM python library, embedder (bge-small), reranker (jina)."*
Per the mid-session override: all `sentence_transformers` imports must be lazy
inside the function so that without the extra, `import python_setup_lint`
never imports it; guard with `ImportError` → fallback to heuristic; models
download on first use (HF cache); tests must not require network.

This is explicitly opt-in research, gated behind `[semantic]`. It is NOT
required for DoD. Pursue only after Track D lands.

### B1. Add `[semantic]` optional-dependency extra to `pyproject.toml`

In `[project.optional-dependencies]` (currently only `dev`), add:

```toml
semantic = [
    "sentence-transformers>=2.7.0",
]
```

`sentence-transformers` provides both the BGE embedder and the Jina
cross-encoder reranker via `CrossEncoder`. This is the opt-in gate — the
embedder/reranker path imports these only when the extra is installed.

### B2. Implement a two-stage `check_if_meaningful` semantic backend

New module `src/python_setup_lint/checkers/_semantic.py` (opt-in):

- **Stage 1 — embedder**: `BAAI/bge-small-en-v1.5` via `sentence_transformers`.
  Embed the justification text and the rule's description; compute cosine
  similarity. Threshold (e.g. ≥0.5) → candidate "meaningful".
- **Stage 2 — reranker**: `jinaai/jina-reranker-v2-base-multilingual` via
  `CrossEncoder`. Cross-encode (justification, rule description) → relevance
  score; threshold (e.g. ≥0.3) → "meaningful".

Design: `check_if_meaningful` keeps its current heuristic as the **default**
zero-dependency path; the semantic backend is selected when
`sentence_transformers` is importable **and** opt-in flag/env
(`PYTHON_SETUP_LINT_SEMANTIC=1`) is set. Otherwise fall back to the existing
heuristic so default installs/tests are unchanged. Current body (verbatim):

```python
def check_if_meaningful(
    text: str,
    *,
    rule: str | None = None,
    code_context: str | None = None,
    comment: str | None = None,
) -> bool:
    """..."""
    primary = (comment or text).strip()
    if not primary or len(primary) < 5:
        return False
    primary_lower = primary.lower()
    boilerplate = {"noqa", "ignore", "suppress", "disable", "skip", "todo", "fixme", "hack"}
    if primary_lower in boilerplate:
        return False
    return True
```

The two callsites in `suppression_justification_checker.py` (lines ~104, ~113)
currently call `check_if_meaningful(reason)` positionally — they pass neither
`rule` nor `comment`. To make Track B's semantic path usable, at least one
callsite must pass `rule=<symbol>` so Stage 1/2 can compare against the rule
description. Wire `rule=self.msgs[msgid].symbol` (or the rule description) into
the callsites. The `comment` param becomes the primary text for the semantic
path; keep `text` as the positional fallback.

### B3. Make the semantic path import-safe and lazy

All `sentence_transformers` imports inside the function / a lazy loader so that
without the extra, `import python_setup_lint` never imports it. Guard with
`ImportError` → fallback to heuristic. Models download on first use (HF cache);
tests must not require network. Concretely: `_semantic.py` does
`from sentence_transformers import ...` inside its functions, never at module
top level; `_base.py`'s `check_if_meaningful` does
`try: from ._semantic import semantic_check ... except ImportError: pass`.

### B4. Tests for the semantic backend

- Unit tests gated on `sentence_transformers` being importable
  (`pytest.importorskip('sentence_transformers')`) AND
  `PYTHON_SETUP_LINT_SEMANTIC=1` env set. Skip otherwise (no network).
- Mark `@pytest.mark.slow` (model load is expensive).
- Test the fallback path (no extra): `check_if_meaningful` returns the
  heuristic result unchanged when `sentence_transformers` is absent — assert
  no import of `sentence_transformers` occurs (`sys.modules` has no such key).
- Do NOT test actual model inference in CI (network); test the wiring/dispatch
  with a stub or with the import-skip guard.

### B5. Document the experiment

Add `docs/semantic-justification.md`: two-stage approach, opt-in mechanism
(`[semantic]` extra + `PYTHON_SETUP_LINT_SEMANTIC=1`), model choices
(bge-small-en-v1.5, jina-reranker-v2-base-multilingual), that this is a
research track, and that default shipped behavior = heuristic. Note
threshold rationale once measured.

**Depends on:** B2 wires into `check_if_meaningful` which is shared; sequence
B1 → B2 → B3 → B4 → B5. Disjoint from Track D files except `_base.py`.

---

## Sequence

1. **D1** (fix 3 rule-ID collisions) — Do first; highest priority, blocks
   "linter runs on its own project." Renumber + update all references.
2. **D2** (justify bare suppression in justification checker) — independent,
   do in parallel with D1.
3. **D3** (CodingRules universal-test-exception bullet) — independent, do in
   parallel with D1/D2.
4. **Track B** (NLP experiment) — only after D1-D3 verify clean. Opt-in,
   lowest priority. May be deferred to a later iteration if scope pressure.

Parallelization: D1, D2, D3 touch disjoint files (D1: docstring_checker,
generic_key_dict_checker, tests, baseline; D2: suppression_justification_checker;
D3: CodingRules.md) and can run concurrently. Track B touches `_base.py`,
`_semantic.py`, `pyproject.toml`, `docs/`, `tests/` — disjoint from D1-D3
except `_base.py` (shared by B2 with nothing in D1-D3).

---

## Edge Cases & Error Conditions

- **D1 reference misses**: renumbering a msgid without updating every
  assertion/baseline/planted-violation string causes test failures or, worse,
  silently passes a stale check. MUST search `tests/`, `test/data/`, and any
  `*.baseline` for the old ID strings before declaring D1 done.
- **D1 symbol stability**: renumber the ID only, never the `symbol` field —
  `symbol` is the `# pylint: disable=<symbol>` handle consumers cite; changing
  it breaks suppressions. Keep `generic-return-requires-returns`,
  `internal-helper-docstring-allowed`, `generic-key-dict` unchanged.
- **D2 self-reference**: the justification checker scanning its own file must
  now pass (the new trailing comment must satisfy `check_if_meaningful` —
  length ≥5 and not in the boilerplate set). Verify by running the checker on
  its own source.
- **B3 import safety**: a module-top-level `import sentence_transformers`
  anywhere in the import graph breaks the "without the extra,
  `import python_setup_lint` works" contract. Grep the whole package after B2
  to confirm all such imports are inside functions.
- **B4 network**: any test that triggers model download fails in offline CI.
  Gate on both `importorskip` AND the env flag; never let the default suite
  import the models.

---

## Verification

1. **D1 — linter runs on its own project**: after renumbering, run pylint
   with `config/.pylintrc` (all 9 plugins) against `src/python_setup_lint/`.
   It must load without a duplicate-msgid error. Assert no `W9701/W9702/W9720`
   collision remains by grepping `msgs` dicts for unique IDs.
2. **D2 — self-consistency**: run `suppression_justification_checker` on
   `src/python_setup_lint/checkers/conformance/suppression_justification_checker.py`;
   it must report zero violations (its own suppression is now justified).
3. **D1 reference sweep**: `search` for the old IDs in tests/baselines must
   return zero stray references to the renumbered rules.
4. **Full test suite**: `pytest -m 'not slow'` stays green and under 30s (the
   perf work from iteration 2 must not regress). `pytest` (all) green.
5. **Track B (if implemented)**: `import python_setup_lint` succeeds with
   no `sentence_transformers` installed; `pytest -m 'not slow'` unchanged;
   semantic tests skip cleanly when the extra/env is absent.

---

## Critical Files

Implementer MUST read these before editing:

- `src/python_setup_lint/checkers/stub/docstring_checker.py` — W9701/W9702
  msgs (lines 82, 89) to renumber to W9705/W9706.
- `src/python_setup_lint/checkers/conformance/generic_key_dict_checker.py`
  — W9720 msg (line 42) to renumber to W9721.
- `src/python_setup_lint/checkers/conformance/unnamed_tuple_dict_checker.py`
  — W9720 msg (line 27) — KEEP this ID.
- `src/python_setup_lint/checkers/conformance/beartype_checker.py` — W9701
  (line 27) — KEEP this ID.
- `src/python_setup_lint/checkers/conformance/tmp_path_checker.py` — W9702
  (line 25) — KEEP this ID.
- `src/python_setup_lint/checkers/conformance/suppression_justification_checker.py`
  — bare suppression line 50; `check_if_meaningful` callsites lines ~104, ~113.
- `src/python_setup_lint/checkers/_base.py` — `check_if_meaningful` body
  (lines 67-89); Track B seam.
- `src/python_setup_lint/checkers/_base.pyi` — stub declaration (lines 43-52).
- `config/.pylintrc` — `load-plugins` line (loads all 9 checkers together).
- `CodingRules.md` — Tests section (lines 238-324) for D3 bullet placement.
- `pyproject.toml` — `[project.optional-dependencies]` (only `dev` today),
  version 0.7.0, `[tool.pytest.ini_options]` addopts/markers.
- `test/data/minimal_sample_project/` + `violations.txt` + any `lint.baseline`
  — planted violation IDs that D1 must update.
- `tests/checkers/test_stub_docstring_checker.py`,
  `tests/checkers/test_generic_key_dict_checker.py` — assertion strings.

---

## Priority & Scope Note

- **Track D (functional correctness) is MANDATORY and DoD-blocking.** The three
  rule-ID collisions make the linter crash on its own project — the project is
  not "perfectly functional" until D1 lands. D2 and D3 close self-consistency
  gaps the goal explicitly requires.
- **Track B (NLP experiment) is optional, opt-in research, lowest priority.**
  It is explicitly gated behind `[semantic]` and not required for DoD. If scope
  must shrink, drop Track B entirely and deliver D1-D3.
- This is iteration 3 of 5. Track D is small, focused, and high-value; it should
  leave 2 iterations of headroom for Track B and any post-verification cleanup.
