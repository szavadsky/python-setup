# decisions.md — python-setup lint-baseline conscious decisions

Records lint findings that are **consciously baselined** (not fixed) with the
reason, per the T9 family gate ("`uv run lint --no-fail-fast` exits 0 OR every
remaining finding has a decisions.md entry"). Each entry below is a
**rule-wrongness** or **intrinsic-typing-limitation** finding that cannot be
fixed without a redesign (T6 follow-up) or a dependency/policy change — inline
suppression is forbidden per the T9 envelope ("Do NOT disable/mask a rule to
clear a finding").

## D1 — `missing-beartype` (pylint W9701, custom `beartype_checker`)

- **Findings baselined:** 46 prod occurrences on the linter's own
  `checkers/*`, `runner/*`, top-level public functions (`visit_*`, `register`,
  `open`, `close`, `emit_*`, `install`, `update`, `all_ok`, `normalize`, …).
- **Why not fixed:** `beartype` is **not a declared dependency** of
  python-setup (`pyproject.toml` deps: `astroid`, `pylint`, `pytest` only) and
  is **not installed** in either the python-setup `.venv` or the
  consultant.mcp `.venv` that runs the pipeline (`ModuleNotFoundError: No
  module named 'beartype'`). Adding `@beartype` decorators to satisfy the rule
  would require `from beartype import beartype` at the top of every flagged
  `.py`, breaking import (`ImportError`) since the package is absent.
- **Root cause:** the rule demands a decorator from a package that isn't a
  dependency. The `beartype_checker` tests use `from beartype import beartype`
  only as **input source strings** to verify the detector recognises the
  decorator syntactically — beartype is never imported at runtime by the
  package.
- **Redesign options (T6 follow-up):** (a) add `beartype` as a runtime
  dependency and decorate every public function, OR (b) exempt the linter's
  own source from `missing-beartype` (the rule is **self-referential** — the
  linter checking itself, where beartype isn't its own dep). Either is a
  policy/dependency decision owned by T6, not a per-file T9 fix.
- **Action:** baseline; raise as T6 follow-up. No inline `# pylint: disable`.

## D2 — `useless-import-alias` (pylint C0414, builtin) on `__init__.py` re-exports

- **Findings baselined:** 103 occurrences in `runner/__init__.py` (84) and
  `checkers/stub_fidelity/__init__.py` (19), all on the `from .mod import name
  as name` idiom.
- **Why not fixed:** the `import X as X` / `from .mod import name as name`
  pattern is the **canonical PEP 484 explicit-re-export idiom** — it marks a
  name as a re-export so type checkers (mypy/pyright/ty) and ruff F401 treat
  it as intentionally exported (silencing "imported but unused"). Both
  `__init__.py` files contain an explicit comment block documenting this
  intent ("All names re-exported via redundant ``as`` aliases so ruff F401
  treats them as intentional re-exports"). Pylint `useless-import-alias`
  false-positives on this idiom by design.
- **Redesign options (T6 follow-up):** either (a) configure pylint to disable
  `useless-import-alias` for `__init__.py` files (per-file/per-path disable in
  the shipped `config/.pylintrc`), or (b) accept the idiom and the baseline.
  Disabling the rule **project-wide** would mask legitimate cases; a scoped
  `__init__`-only disable is a config-policy decision owned by T6.
- **Action:** baseline; raise as T6 follow-up. No inline `# pylint: disable`.

## D3 — ty `invalid-argument-type` / mypy `arg-type` on astroid circular-import typing

- **Findings baselined:** ty `invalid-argument-type` on cross-module helper
  calls in `stub_checker.py` (L209/213/229/233/305/306/307 —
  `_is_under_source_root(self,…)`, `emit_coverage_violations(self)`, etc.),
  `stub_import_contract.py` L117/127/138 (`BaseChecker.add_message`),
  `stub_fidelity/signature.py` L64/66/90 (`len`/`enumerate` on
  `nodes.Arguments` attrs), `stub_normalizer.py` L107/110/114/117
  (`AnnotationNormalizer._ast_string` arg + `str.join` overload), and
  `annotation.py` L106/107 (`_normalize_bases([base.value])`). mypy mirrors:
  `stub_normalizer.py` L107/114 `arg-type` (`NodeNG | Proxy` vs `NodeNG`).
- **Why not fixed:** these arise from the **circular import structure** of the
  stub-checker family (`stub_checker` imports `stub_coverage`/`stub_fidelity`/
  `stub_import_contract`, which import `StubChecker` back under
  `TYPE_CHECKING`). With `from __future__ import annotations`, the
  `checker: StubChecker` params are forward-ref strings; ty/mypy resolve
  `StubChecker` to a partial/`Proxy` type at analysis time and flag
  `self`/concrete-`StubChecker` arguments as incompatible. This is an
  **intrinsic astroid-typing + circular-import limitation** of ty/mypy, not a
  code defect — the code is correct at runtime.
- **Genuine fix attempted where tractable:** `_ast_helpers`/`annotation`
  `impl_annotations` value type widened to
  `tuple[NodeNG|None, AnnAssign|Assign|None]` (the Assign branch genuinely
  stores `Assign` nodes) — cleared ty `invalid-assignment` at
  `stub_checker.py:341` and `annotation.py:184`.
- **Redesign option (T6 follow-up):** introduce a structural `Protocol`
  capturing the `StubChecker` attributes the helpers actually use
  (`_coverage`, `_fidelity`) and type the helper params as that Protocol,
  breaking the circular-type dependency cleanly. This is a non-trivial
  refactor (6+ signatures + `.pyi` updates) and a redesign concern, out of
  T9's "fix the violation, don't redesign the checker" scope.
- **Action:** baseline the remaining ty/mypy astroid-typing findings; raise
  the Protocol refactor as T6 follow-up.

## D4 — ruff `S603` (subprocess-run-untrusted-input) on `setup._run_uv`

- **Finding baselined:** `src/python_setup_lint/setup.py` `_run_uv`
  `subprocess.run(["uv"] + args, …)` — S603 flags subprocess with a
  non-literal command.
- **Why not fixed:** `args` is a `list[str]` constructed locally from
  hard-coded literals (`["add", "--dev", dev_path]` / `["add", "--dev", f"…"]`
  in `_step_add_dep`) — the command input is **trusted and locally-built**,
  not user/external-supplied. S603 is a false-positive for this controlled
  local invocation. Adding a `# noqa: S603` would be an inline mask
  (forbidden); the legitimate general fix (mark args as trusted) has no ruff
  idiom short of a project-level allow.
- **Companion fix applied:** explicit `check=False` added to the same
  `subprocess.run` to clear `PLW1510`/`subprocess-run-check` (intent: the
  wrapper captures the return code and must NOT raise on non-zero exit).
- **Redesign option (T6 follow-up):** scope `S603` to genuinely-untrusted
  subprocess sites via per-file config, or accept the baseline for the
  trusted-local-`uv`-invocation case.
- **Action:** baseline S603; raise as T6 follow-up.

## D5 — pylint complexity rules (`too-many-{instance-attributes,branches,locals,statements,lines,positional-arguments}`)

- **Findings baselined (intrinsically-structured sites):**
  - `stub_coverage._CoverageState` `too-many-instance-attributes` (16/15) —
    the dataclass deliberately aggregates all Phase-1+shared state for the
    StubChecker; splitting would scatter correlated state across dataclasses
    and complicate the cross-module access (`checker._coverage.<field>`).
  - `stub_normalizer.AnnotationNormalizer.normalize` `too-many-branches`
    (21/16) — the `_ast_string`/`normalize` dispatch over astroid node kinds
    is an exhaustive `isinstance` ladder over `nodes.{Name,Subscript,BinOp,
    Attribute,Tuple,Const,List,UnaryOp,Starred,Dict,IfExp}`; each branch is a
    one-line canonical-string form. Collapsing to a dispatch table is a
    redesign of the normalizer, out of T9 scope.
  - `stub_fidelity.kind._emit_stub_symbol_check` `too-many-locals` (21/20) —
    local dicts (`stub_kinds`, `impl_kinds`) are the natural shape of the
    stub-vs-impl kind comparison.
- **Why not fixed inline:** the envelope forbids rule-disable/mask; the
  genuine fix for each is a structural refactor (split dataclass / dispatch
  table / extract method) that redesigns the checker, which T9 explicitly
  scopes out ("Re-implementing checkers … out of scope").
- **Redesign option (T6 follow-up):** either raise the per-rule complexity
  thresholds in the shipped `config/.pylintrc` (policy) or undertake the
  checker refactors. Both are T6-owned.
- **Action:** baseline; raise as T6 follow-up.

## D6 — `missing-final-newline` / ruff `W292` — FIXED (not baselined)

All 15 src files lacking a trailing newline were fixed in T9-1 (newline
appended). Listed here only to record the category is **resolved**, not
baselined.

## D7 — `docstring-in-impl` (pylint W9700, custom `stub_docstring_checker`) — FIXED (not baselined)

All prod `docstring-in-impl` findings (149) were fixed across T9-1..T9-4 by
moving usage docstrings to companion `.pyi` stubs (public members) or
converting private-helper docstrings to implementation `#` comments (per
CodingRules: `.py` keeps implementation comments only; `.pyi` exposes only
public members, no `_`-prefix symbols). Verified: `pylint
--load-plugins=…stub_docstring_checker… --enable=docstring-in-impl` reports
0 W9700 on edited files. Listed here only to record the category is
**resolved**, not baselined.
