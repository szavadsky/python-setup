# lint-goal — Iteration 1 Plan

> Plan for the goal in `.tmpoutput/lint-goal/goal.md`. Written from a read-only
> codebase survey (no prior `summaryN.md` exists — this is iteration 1).
> No source edits have been made; this is a concrete, sequenced execution plan.

## Summary

`python-setup-lint` is a reusable lint/format/dev-tooling package (`src/python_setup_lint/`)
built on a unified 11-tool runner (`runner/`) plus custom pylint checkers (`checkers/`),
an idempotent installer (`setup.py`), and shipped config (`config/`). The goal asks for a
batch of cross-cutting hardening work, grouped into **eight workstreams**:

1. Codify the `_`-symbol test-import convention in `CodingRules.md` and reinforce the
   `test_runner_private_imports.py` guard.
2. Optimize non-slow test runs back **under 30 s** (slow tests currently run by default;
   unmarked benchmarks add overhead).
3. Seed a minimal sample project with planted violations + a single large
   `test/integration.py` exercising setup→lint→violation-check→overlay→resetup/update→
   git-hook dry-run; gitignore everything setup generates.
4. Reorganize `src/python_setup_lint/checkers/` into a proper folder architecture.
5. Prohibit **unnamed-tuple** dict values (e.g. checker `msgs`) — require named
   tuple/dataclass/protocol with named fields; add custom linter; fix all instances.
6. Prohibit **generic-key dict** annotations (`dict[str, X]`) for bona-fide generics —
   require a named type (e.g. `LintRuleId`) / enum / literal; add rule; fix instances.
7. Require **suppression comments** (`# pylint: disable`, `# noqa`, `# type: ignore`) to
   carry a **technical justification**; add a common `check_if_meaningful` helper; lint it.
8. Tighten **docstring** rules: generic returns OK *only if* a `Returns {meaningful}`
   clause exists; allow `_`-prefixed internal helpers to have docstrings. Extend the
   existing docstring custom linter. Plus: bump version, slim README, move overlays/
   custom-checks to linked `docs/`.

Final state (DoD): project is perfectly functional and installable, code is well
organized with minimal LoC, and **zero linting violations except a small, explicit,
CodingRules-justified exception set**.

---

## Grounding facts (from survey)

| Fact | Evidence |
|---|---|
| Version defined in `pyproject.toml:2` as `version = "0.5.0"`; `CHANGELOG.md` latest header is `v0.6.0 (2026-06-23)` — **divergent**. No `__version__`/`_version.py` exists. | direct read |
| 3 console_scripts (`pyproject.toml:14-16`): `lint`→`runner.cli.main`, `install`→`setup.main`, `python-setup-test-checked`→`testing.test_checked_main`. | direct read |
| `[tool.pytest.ini_options]` (`pyproject.toml:~57`) defines 4 markers (`slow`, `no_external_api`, `with_real_api`, `implementation_detail`) but has **NO `addopts`, NO `testpaths`, NO default `-m "not slow"`** → bare `pytest` runs *everything* incl. slow. | direct read |
| 5 `@pytest.mark.slow` tests spawn real subprocesses/installs: `test_consolidated_real_pipeline_smoke` (runs all 11 tools via real `run_lint()`), `test_install_then_lint`, `TestHealthChecksAgainstInstalledTemplate`, `test_run_lint_with_extras_startup_overhead_within_10_percent` (perf), `test_run_lint_fix_does_not_crash` (real repo `--fix`). | TestScout + direct read of `test_real_pipeline_smoke.py` |
| **Unmarked** `TestPerfBenchmark` in `tests/runner/test_baseline_diff_edge.py:64-108` builds 50k-record lists and asserts `<200ms` / `<1s`; runs in the default suite (no marker). | direct read + search |
| Private-imports guard exists: `tests/runner/test_runner_private_imports.py` — asserts `runner.__all__` has no `_`-names, namespace exposes none, `__init__` imports no `_`-submodules. | direct read |
| `tests/` layout: root `conftest.py`; `tests/runner/` (28 test files + `_factories.py` + `_autofix_helpers.py`); `tests/checkers/` (12 files + `_factories.py`). **No `test/` dir; no `test/integration.py`; no sample project with planted violations** — tests synthesize projects in `tmp_path`. | TestScout |
| `.gitignore` has **no entries for setup-generated artifacts**. Only `tests/fixtures/dogfood-extra/` exists as a fixture project (minimal extra-tools config). | TestScout |
| `checkers/` is **flat**: 8 checker modules at root (`asyncio_timeout_checker`, `beartype_checker`, `no_try_import_checker`, `structlog_checker`, `stub_checker`, `stub_coverage`, `stub_normalizer`, `stub_docstring_checker`, `stub_import_contract`, `tmp_path_checker`) + `stub_fidelity/` subpkg (`orchestrator.py`, `annotation.py`, `kind.py`, `signature.py`, `_ast_helpers.py`, `__init__.py`). Each `.py` has a paired `.pyi`. `_checker_base.py` holds shared helpers (`_matches_path`, `_is_under_source_root`, `_get_file_path`). `__init__.py` exports `register(linter)` per module. | direct read of dir |
| Every checker declares `msgs = ClassVar[dict[str, tuple[str,str,str]]]` with **unnamed 3-tuple values** `(message_template, symbol, description)` — the canonical P1 anti-pattern. Example: `beartype_checker.py:18-24` (`"W9701": ("Public function '%s'...", "missing-beartype", "All public functions...")`). | PatternScout + direct read |
| P2 generic-key dicts pervasive: `dict[str, tuple[str,str,str]]` (checker msgs), `dict[str,Any]` across `runner/baseline.py` (17+ sites), `runner/_record_types`, `stub_fidelity/_ast_helpers.py`. No `LintRuleId` named type exists yet. | PatternScout |
| P3 suppressions: `# noqa: TC001/002/003` (TYPE_CHECKING imports — justified), `# pylint: disable=missing-beartype` on `register()`/visit methods (some carry `# circular import — ...` justification, many **bare**), `# type: ignore` in `stub_fidelity/_ast_helpers.py` & `kind.py`. | PatternScout |
| P5 example given verbatim in goal: `StubChecker.normalize(...)->str` with a "phase 1/2" docstring lacking a `Returns` clause (from `stub_normalizer.py`). Existing `stub_docstring_checker.py` already enforces some docstring rules. | goal + PatternScout |
| `CodingRules.md` (318 lines, 7 sections: Platform/Typing/Module Layout/Symbol Convention/.pyi Rules/Documentation/Simplification/Logging/Sync-Async/Timeouts/Error Handling/Schema/Tests) uses **dense bullet style, no `####` headings**. New rules MUST match that compression style. Symbol Convention currently says only "`_` prefix: file-private, imported only by tests." | direct read |
| **No `docs/` directory exists.** Wheel (`[tool.hatch.build.targets.wheel.force-include]`, `pyproject.toml:~31`) includes `config/` and `CodingRules.md` only. README (11.2 KB, 10 sections) inlines install/usage/overlays/custom-steps with **no links to docs/**. | StructureScout + GapScout |
| `python_setup_lint` depends on `astroid>=4.0.4`, `pylint>=4.0.6`, `pytest>=9.1.0` (core). No NLP/embedder libs (bge-small, jina, sentence-transformers) present. | StructureScout |

---

## Changes (concrete, by file)

### WS-1 — `_`-symbol test-import convention + guard

**G1.1** `CodingRules.md` — append to **Symbol Convention** section (match dense-bullet style):
> - Tests import `_`-prefixed symbols only from their defining submodule, never through the
>   package `__init__`. (Reason: keeps `__init__` public surface lean; prevents accidental
>   re-export of file-private helpers.)

**G1.2** `tests/runner/test_runner_private_imports.py` — extend the existing guard to also
assert the *import path* contract: scan test files for `from python_setup_lint.runner import`
statements that bind a `_`-prefixed name (currently the guard only checks `__all__` /
namespace / `__init__` imports). Add `test_tests_import_privates_only_from_defining_submodule`
that AST-walks `tests/` for `ImportFrom` nodes where `module` resolves to the runner package
root (not a submodule) and the bound name starts with `_`.

**Depends on:** nothing. **Files:** `CodingRules.md`, `tests/runner/test_runner_private_imports.py`.

---

### WS-2 — Test perf under 30 s (non-slow runs)

Root cause: bare `pytest` runs slow + unmarked benchmarks. Three coordinated fixes:

**G2.1** `pyproject.toml` `[tool.pytest.ini_options]` — add `addopts = "-m 'not slow'"` so the
default run excludes `@pytest.mark.slow` (CI runs `pytest -m slow` separately for integration).
This single change removes the 5 real-subprocess tests from the default suite.

**G2.2** `tests/runner/test_baseline_diff_edge.py:67` — mark `TestPerfBenchmark` with
`@pytest.mark.slow` (the class). The 50k-record builders (`test_50k_line_baseline_compares_under_200ms`,
`test_diff_baseline_50k_end_to_end_under_1s`) are benchmarks, belong behind the slow gate.

**G2.3** Audit remaining default-suite tests for hidden subprocess/real-install cost (run
`pytest --durations=10 -m "not slow"` to find the slow ten; convert any that spawn real
processes to `FakeRunCmd`/in-process + mark `slow`, per the established pattern in
`tests/runner/_factories.py` `install_fake_runner`). Ensure `no_external_api` marker is
applied consistently (currently defined but under-used).

**Files:** `pyproject.toml`, `tests/runner/test_baseline_diff_edge.py`, possibly more test
files + `tests/conftest.py`. **Depends on:** WS-3 partially (sample project) for integration
suite placement, but G2.1/G2.2 are independent and should land first.

---

### WS-3 — Sample project + `test/integration.py` + gitignore

**G3.1** Create `test/data/minimal_sample_project/` — a **minimal, standalone python project
NOT subject to the project's own linting** (place under a path excluded by the lint config;
confirm `config/ruff.toml`/`.pylintrc` source roots exclude `test/`). Contents:
- `pyproject.toml` (`name = "minimal-sample"`, `version = "0.1.0"`)
- `src/minimal_sample/__init__.py`, `src/minimal_sample/main.py`
- **Planted violations**: ≥1 per custom linter rule + 1–2 per critical upstream rule. Concretely
  plant: a public func missing `@beartype` (W9701), an unnamed-tuple `msgs`-style dict (new rule),
  a `dict[str, X]` generic-key annotation (new rule), a bare `# noqa` (new rule), a
  `def f()->str:` with a phase-style docstring lacking `Returns` (docstring rule), plus
  upstream: a `W0611` unused-import (ruff F401), a missing-module-docstring (pylint C0114).
- A `violations.txt` listing every planted violation with expected (tool, rule, file:line).

**G3.2** Create `test/integration.py` — **single large test file** (per goal wording) with
scenario functions (use the `test_<verb>_given_<condition>_then_<expected>` naming from
CodingRules.Tests.Naming):
1. `test_setup_given_clean_project_then_installs_and_runs_lint` — run `install`, then `run_lint`;
   assert setup correct + all configured tools run.
2. `test_lint_given_planted_violations_then_reports_each_expected` — run linter on the sample
   project, assert every planted violation in `violations.txt` appears.
3. `test_overlay_given_config_change_then_lint_result_changes` — edit config (rule overlay:
   enable/disable a rule, adjust severity), re-lint, assert diff.
4. `test_resetup_given_existing_install_then_idempotent_update` — re-run `install`, assert
   idempotent (checksums unchanged unless config drifted); simulate update path.
5. `test_git_hooks_given_dry_run_then_expected_results` — run pre-commit hook in dry-run mode,
   assert expected pass/fail without mutating the repo.
Mark the whole file `@pytest.mark.slow` (real subprocess exercise) so WS-2 default suite stays
fast. Drive via in-process `run_lint`/`install` where possible; real subprocess only for the
git-hook dry-run scenario.

**G3.3** `.gitignore` — add the setup-generated artifacts the installer writes to a consumer
project (discover exact filenames from `setup.py` install targets): `.pre-commit-config.yaml`,
`lint.baseline`, `.secrets.baseline`, copied `config/` tree, `pyrightconfig.json`,
`mypy.ini`, `.pylintrc`, `ruff.toml`, `rumdl.toml`, `ty.toml`, `.yamllint` as applicable.
Add a guarded block (e.g. `/test/data/minimal_sample_project/<generated>`) so repo stays clean.
Confirm the sample project's *planted* source is committed (not gitignored).

**Files:** `test/data/minimal_sample_project/**`, `test/integration.py`, `.gitignore`.
**Depends on:** WS-5/6/7 new rules must exist so their planted violations are detectable. Land the
scaffolding first (G3.1 structure, G3.2 skeletons), wire the violation assertions once rules exist.

---

### WS-4 — Reorganize `checkers/` folder architecture

Current `checkers/` mixes top-level single-purpose checkers with the multi-file `stub_fidelity`
subpackage. "Proper structure" = group by concern and separate engine glue from rule logic.

**G4.1** Propose the target layout (confirm against AGENTS.md conventions before moving):
```
src/python_setup_lint/checkers/
  __init__.py            # register-all aggregator (unchanged contract)
  _base.py               # shared helpers (renamed from _checker_base.py)
  _registry.py           # NEW (extract): checker discovery/register wiring now in setup.py
  conformance/           # single-purpose conformance checkers
    asyncio_timeout.py
    beartype.py
    no_try_import.py
    structlog.py
    tmp_path.py
  stub/                  # stub-fidelity family (moved from stub_fidelity/)
    __init__.py
    checker.py           # StubChecker (from stub_checker.py)
    coverage.py
    import_contract.py
    docstring.py
    normalizer.py
    orchestrator.py      # from stub_fidelity/orchestrator.py
    annotation.py        # from stub_fidelity/
    kind.py              # from stub_fidelity/
    signature.py         # from stub_fidelity/
    _ast_helpers.py      # from stub_fidelity/
```
Each module keeps its `.pyi`. Update `__init__.py` imports + the auto-discovery in
`setup.py` (which walks `checkers/` for `register`) to the new paths. Update all test
imports in `tests/checkers/` to the new module paths.

**G4.2** Decide naming: keep snake_case module names matching CodingRules. Prefer moving over
renaming where the existing name is descriptive; only `stub_checker.py→stub/checker.py` and
`stub_coverage.py→stub/coverage.py` drop the redundant `stub_` prefix (they're now under `stub/`).

**Risk:** the `StubChecker` type is imported by `stub_import_contract.py`, `stub_coverage.py`,
and `stub_fidelity/orchestrator.py` (cross-references). Use LSP `references` on `StubChecker` +
each moved symbol before moving; move in dependency order (helpers → leaf modules →
orchestrator → checker). Update `.pyi` in lockstep. Keep `register(linter)` export per module.
**Files:** entire `checkers/` tree + `setup.py` discover path + `tests/checkers/**`.
**Depends on:** nothing strictly; but do this BEFORE WS-5/6/7 add new checker modules so new
rules land in the final locations. Sequence: WS-4 → WS-5/6/7.

---

### WS-5 — Prohibit unnamed-tuple dict values (P1)

**G5.1** Define a named representation. The checker `msgs` shape `(message, symbol, description)`
becomes a `NamedTuple` or frozen dataclass, e.g. `MessageDef(NamedTuple): message: str; symbol:
str; description: str` (place in `checkers/_base.py` or a new `checkers/_msgtypes.py`). For rule
ids, see WS-6 (`LintRuleId`). Migrate all checker `msgs` dicts to use the named type.

**G5.2** New custom linter **`unnamed_tuple_dict_checker`** (place under `checkers/conformance/`
post-WS-4): flags any `dict` literal whose values are bare `tuple`/`Tuple[...]` literals with >1
unnamed positional fields, suggesting they should be a NamedTuple/dataclass. Heuristic: trigger
when a dict value is a `tuple` literal of length≥2 with all-str/elem-typed members AND the dict
is annotated `dict[str, tuple[...]]` or assigned to a `ClassVar[dict[str,...]]`. Provide an
inline disable with justification (consistent with WS-7). Register in `__init__.py`.

**G5.3** Fix all existing instances (PatternScout enumerated every checker's `msgs`):
`asyncio_timeout_checker.py:48`, `beartype_checker.py:18-24`, `no_try_import_checker.py:17`,
`structlog_checker.py:24-35`, `stub_checker.py:52-155`, `stub_docstring_checker.py:?`,
`tmp_path_checker.py:20`, plus any in `stub_fidelity/`. Convert each to the named type from G5.1.

**Files:** new checker + `checkers/_base.py`(or `_msgtypes.py`) + all checker `.py`/`.pyi`.
**Depends on:** WS-4 (placement). **Tests:** add `tests/checkers/test_unnamed_tuple_dict_checker.py`
using FakeRunCmd-style AST fixtures (no real subprocess); plant a violating dict and a passing
named-tuple dict.

---

### WS-6 — Prohibit generic-key dict annotations (P2)

**G6.1** Introduce `LintRuleId` — a typed rule-id type (e.g. `StrEnum`/`Literal` of the existing
`W9701`/`C0xxx` codes, or a branded `NewType`-backed dataclass) defined in a typed module (e.g.
`checkers/_msgtypes.py`). Replace `dict[str, ...]` generic keys where the key is a bona-fide
domain type with `dict[LintRuleId, ...]`. For genuine string-keyed maps (filename→record), keep
`dict[str, ...]` but justify in CodingRules as an allowed category (filenames, identifiers,
display strings).

**G6.2** New custom linter **`generic_key_dict_checker`**: flags `dict[str, X]`/`Dict[str, X]`
annotations where the key semantically represents a *typed domain value* (heuristic: the dict is
named like a registry/ruleset, or X is itself a domain type) and recommends `LintRuleId`/enum/
literal. Tunable via config option `allow-string-keys-for: {filenames,identifiers,paths,display}`.
Provide escape hatch with justification (WS-7).

**G6.3** Fix instances enumerated by PatternScout: checker `msgs` dicts (now keyed by `LintRuleId`
after WS-5), `runner/baseline.py` (17+ `dict[str,Any]`/`dict[str,...]` — classify each: keep if
keyed by filename/identifier, migrate if keyed by tool/rule), `stub_fidelity/_ast_helpers.py`,
`runner/_record_types`. Add a CodingRules `.pyi Rules` / `Typing` bullet documenting the allowed
generic-key categories (filenames, identifiers, paths, display strings).

**Files:** new checker + `checkers/_msgtypes.py` + `CodingRules.md` + `runner/baseline.py` +
`runner/_record_types.py` + `stub_fidelity/_ast_helpers.py` + migrated checkers.
**Depends on:** WS-5 (shares `_msgtypes` / `LintRuleId`). **Tests:**
`tests/checkers/test_generic_key_dict_checker.py` (passing: `dict[LintRuleId, X]`, `dict[str, Path]`
allowed-as-path; failing: `dict[str, RuleEntry]`).

---

### WS-7 — Justified-suppression linter + `check_if_meaningful` helper

**G7.1** New **`suppression_justification_checker`** (under `checkers/conformance/` post-WS-4):
flags any `# pylint: disable=...`, `# noqa: <code>`, `# type: ignore` whose line lacks a
technical justification. Detection: the suppression comment must be followed by (same line or a
trailing comment) a `# <reason>` phrase, OR the preceding line is a comment with a reason.
Reuse a shared helper (G7.2) to judge whether the trailing text is "meaningful" (non-empty,
non-boilerplate). Already-justified cases to preserve: `# noqa: TC002` paired with
`# TYPE_CHECKING import` reasons, `# pylint: disable=missing-beartype  # circular import — PyLinter not available at runtime` (already has reason).

**G7.2** Implement **`check_if_meaningful(text, *, rule=None, code_context=None, comment=None)
-> bool`** common helper — place in `checkers/_base.py` (or a new `checkers/_semantic.py`).
Start with a deterministic heuristic (length floor, stop-word/boilerplate filter, "contains a noun
not equal to the rule symbol"). **Experiment track** (per goal: "try NLP not LLM"): evaluate a
small embedder/reranker offline — `bge-small-en` (sentence-transformers) for embedding + `jina`
reranker — to score relevance of justification text to the rule. NOTE: no such libs present
today; the experiment is **opt-in research**, gated behind a `[tool.python-setup-lint.semantic]`
flag, default OFF. Do NOT add heavy deps to core; if pursued, put behind optional-dependency
group `[semantic]`. Document the experiment outcome; default shipped behavior = heuristic.

**G7.3** Fix all unjustified suppressions enumerated by PatternScout: add a technical reason to
each bare `# pylint: disable=missing-beartype` (e.g. `# circular import — <Type> not importable
at runtime` where true; where genuinely missing @beartype, ADD `@beartype` instead of suppressing).
For `# type: ignore` in `stub_fidelity/_ast_helpers.py` / `kind.py`, add the astroid/mypy
version-specific reason or fix the typing. Leave justified `noqa: TC00x` intact but ensure the
paired reason comment exists.

**Files:** new checker + `checkers/_base.py`(+`_semantic.py`) + all files with bare suppressions
(`runner/dispatch.py:8 LintTool methods`, `runner/baseline.py:~53`, `stub_import_contract.py:80`,
`stub_fidelity/orchestrator.py:29`, `stub_coverage.py:246`, checker `register()`s).
**Depends on:** WS-4 (placement). **Tests:** `tests/checkers/test_suppression_justification_checker.py`
(passing: justified noqa; failing: bare `# noqa: E501`).

---

### WS-8 — Docstring rules + version + README + docs/

**G8.1** Extend the **existing** `stub_docstring_checker.py` (don't create a duplicate) with two
new rules:
- **Generic-return-requires-Returns**: for `def`/`async def` with a non-None concrete return
  annotation (`-> int/str/bool/list[...]`/etc.), require the docstring to contain a `Returns`
  clause describing the returned value (allow `Returns: {meaningful}`, `Return: ...`). Reuse
  `check_if_meaningful` (WS-7) to verify the Returns text is meaningful, not boilerplate.
  Allow `_`-prefixed/internal helpers to be exempt (see next rule). Flag the goal's example
  (`StubChecker.normalize(...)->str` phase-1/2 docstring) as a violation.
- **Internal-helper-docstring-allowed**: explicitly permit `_`-prefixed functions/methods to
  carry a docstring (overrides any "no docstring on private" rule if one exists; the goal says
  "_pyInternalHelper may have a docstring"). Codify in `CodingRules.md` Documentation.

**G8.2** Fix offenders: `stub_normalizer.py` `normalize()` (add a `Returns` clause or rename the
docstring to describe the returned normalized annotation string); audit PatternScout's P5 list
(`runner/` helpers with generic returns + no Returns). Either add `Returns` or, if trivial, the
docstring should not describe "phases" without saying what's returned.

**G8.3** `CodingRules.md` Documentation — add bullets (dense style):
> - Generic-typed returns (`-> int/str/bool/...`) require a `Returns` clause describing the value.
> - `_`-prefixed helpers may carry a docstring.
> - Suppression comments MUST carry a technical justification (same line or preceding comment).

**G8.4** **Version bump**: `pyproject.toml:2` `0.5.0 → 0.6.0` to match `CHANGELOG.md` (or, since
this is a feature batch, `0.7.0` if semver-major-per the project's cadence — check CHANGELOG for
whether minor = feature). Add a `CHANGELOG.md` entry summarizing WS-1..8 under the bumped version.

**G8.5** **README.md** — slim to short, user-focused (what/install/configure), and **move
overlays + custom-checks detail to `docs/`** with links:
- Create `docs/overlays.md` (rule overlay configuration) and `docs/custom-checks.md` (writing
  custom pylint checkers for python-setup-lint). Move the inlined overlay/custom-step sections out.
- README keeps install + quickstart + links to `docs/overlays.md`, `docs/custom-checks.md`,
  `CodingRules.md`, `CHANGELOG.md`.
- Add `docs/` to the wheel `force-include` (`pyproject.toml` `[tool.hatch...]`) so docs ship.

**Files:** `stub_docstring_checker.py`(+`.pyi`) + offending `.py` files + `CodingRules.md` +
`pyproject.toml` + `CHANGELOG.md` + `README.md` + new `docs/overlays.md`, `docs/custom-checks.md`.
**Depends on:** WS-7 (`check_if_meaningful` reused here). **Tests:** extend
`tests/checkers/test_stub_docstring_checker.py` (or equivalent) with returns-clause cases.

---

## Sequence & dependencies

```
WS-1 (coding rule + guard)        ─┐
WS-4 (reorg checkers/)            ─┼─► WS-5 (unnamed-tuple rule) ─┐
                                   │   WS-6 (generic-key rule)     ├─► WS-3 (sample+integration) ─┐
WS-2.1/2.2 (perf gate)            ─┤   WS-7 (suppression rule)    ─┘                             │
                                   │                                                                │
WS-8.1/8.2/8.3 (docstring rules) ◄─┴── WS-7.2 (check_if_meaningful)                                │
                                                                                                  ▼
                                                            WS-8.4 (version) ◄── all rule work done
                                                            WS-8.5 (README+docs/) ◄── final polish
                                                            Final: fix all remaining lint violations project-wide,
                                                            establish the explicit-exception set, dogfood run green.
```

Recommended order:
1. **WS-4** (reorg) — move first so all new checkers land in final paths.
2. **WS-5 → WS-6 → WS-7** (parallel after WS-4; WS-6 needs WS-5's `_msgtypes`).
3. **WS-1, WS-2.1, WS-2.2** (independent config/guard tweaks — parallel).
4. **WS-8.1–8.3** docstring rules (needs WS-7's helper).
5. **WS-3** sample + integration (needs new rules so planted violations are detectable).
6. **WS-8.4** version bump (after all functional work).
7. **WS-8.5** README/docs split (final, after content stabilizes).
8. **Final sweep**: `python-setup lint` dogfood run on the project itself, fix every
   violation except the explicitly-justified exception set (record in CodingRules /
   a per-file `# justified: <reason>` where WS-7 allows). Re-baseline if needed.

---

## Edge cases & error conditions

- **WS-4 move risks**: `StubChecker` is imported across `stub_import_contract`, `stub_coverage`,
  `stub_fidelity/orchestrator`, and tests. Circular import hazard — keep TYPE_CHECKING imports
  for `StubChecker` exactly as today. Run LSP `references` on every moved symbol before moving;
  move in leaf-first order; update `.pyi` together with `.py`. The `setup.py` auto-discovery
  must still find `register(linter)` in new paths (walks `checkers/` recursively — verify).
- **WS-2 perf gate**: adding `addopts = "-m 'not slow'"` changes default test surface; ensure
  CI config (pre-commit / AGENTS.md dev commands) explicitly runs `pytest -m slow` for
  integration so coverage isn't silently lost. Verify the slow gate doesn't hide a required test.
- **WS-3 sample project lint-exclusion**: confirm `config/*` source-roots (`src`) exclude
  `test/`; otherwise the dogfood linter will flag the planted violations *in our own repo*.
  The sample project must be a lint target, not a lint participant.
- **WS-5/6 linter false positives**: the new checkers will run on the *project's own* code —
  iterate the rule until the project is clean (this IS the dogfood requirement). Avoid
  over-triggering on legitimate `dict[str, Path]` (filename keys) — use the allow-list config.
- **WS-7 `check_if_meaningful` semantic experiment**: heavy-NLP path must stay optional and
  default-OFF; if it adds import cost at checker-load time it will regress WS-2's 30s budget.
  Gate imports inside the optional flag.
- **WS-8 version**: pick minor vs major consistent with CHANGELOG cadence (v0.5→v0.6 was a
  feature release per the v0.6.0 header). Likely `0.7.0` for this feature batch.
- **Exception set**: CodingRules says tests and `.py` vs `.pyi` may have justified exceptions.
  Document the universal test-only exception (e.g. relaxed param count) explicitly; don't leave
  exceptions implicit.

---

## Verification

- **Per-workstream unit**: run each new checker's dedicated test (FastRunCmd/in-process AST
  fixtures — no real subprocess). E.g. `pytest tests/checkers/test_unnamed_tuple_dict_checker.py
  tests/checkers/test_generic_key_dict_checker.py tests/checkers/test_suppression_justification_checker.py`.
- **WS-2 perf**: `time pytest -m "not slow"` < 30 s; `pytest --durations=10 -m "not slow"`
  shows no real-subprocess test in top 10. `pytest -m slow` still green (integration preserved).
- **WS-3 integration**: `pytest -m slow test/integration.py` — all 5 scenarios pass; manually
  `git status` after a dry-run hook scenario shows no uncommitted changes (dry-run honored).
- **WS-4 regression**: `pytest tests/checkers tests/runner` green after reorg; `setup.py`
  still discovers all checkers (`python -c "import python_setup_lint.checkers; print([...])"`).
- **Dogfood (DoD)**: `python-setup lint` (the project linting itself) exits 0 except for the
  documented exception set; `python-setup lint --fix` produces no unfixable leftovers.
- **Type/stub**: `mypy --strict src` + `pyright` clean on changed `.py`/`.pyi` (the project
  mandates `.pyi` for non-trivial `.py`); run `python-setup-test-checked` (the shipped test
  helper) to confirm stub/impl fidelity across moved modules.
- **Build/install**: `uv build` + `uv pip install dist/*.whl` into a throwaway venv; `lint
  --help` and `install --help` work; version reports the bumped number.

---

## Critical files (implementer must read)

- `pyproject.toml` — version (L2), scripts (L14-16), pytest config (L~57), wheel includes.
- `CodingRules.md` — convention style to match; Symbol Convention / Documentation / Typing /
  .pyi Rules sections are the targets for new bullets.
- `src/python_setup_lint/checkers/__init__.py` — checker registration contract.
- `src/python_setup_lint/checkers/_checker_base.py` (+`.pyi`) — shared helpers; home for new
  `_msgtypes` / `_semantic` / `check_if_meaningful`.
- `src/python_setup_lint/checkers/beartype_checker.py` — representative checker (msgs shape,
  `register(linter)`, BaseChecker, beartype usage, suppression pattern).
- `src/python_setup_lint/checkers/stub_docstring_checker.py` — existing docstring linter to extend.
- `src/python_setup_lint/checkers/stub_checker.py` + `stub_fidelity/` — StubChecker hub; cross-refs
  to honor during WS-4 reorg; `stub_normalizer.py` `normalize()` is the WS-8 returns-example.
- `src/python_setup_lint/setup.py` — idempotent installer; auto-discovers checkers; install
  targets inform WS-3 `.gitignore`.
- `src/python_setup_lint/runner/baseline.py` — dense P2 generic-dict population (WS-6 fix site).
- `src/python_setup_lint/runner/dispatch.py` — LintTool methods missing @beartype (WS-7 fix).
- `tests/runner/test_runner_private_imports.py` — the guard to extend (WS-1).
- `tests/conftest.py` + `tests/runner/_factories.py` — FakeRunCmd/fixture patterns to reuse.
- `tests/runner/test_baseline_diff_edge.py` — unmarked benchmarks to gate slow (WS-2.2).
- `README.md`, `CHANGELOG.md`, `AGENTS.md` — docs/version/user-doc context (WS-8.4/8.5).
