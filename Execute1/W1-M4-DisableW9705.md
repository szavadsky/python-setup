Implement M4 — Disable W9705 (`generic-return-requires-returns`) in both projects

Read {F}/plan1.md:51-52 for the full spec.

## What to do

W9705 fires when a `.py` function with a companion `.pyi` has a non-None return annotation and a docstring lacking a `Returns:` clause. CodingRules L11 (`Types > names > docstrings`) and L68 (`.py` implementation comments only; `help()` empty is intentional) mean a `Returns:` clause is redundant when the return type is already annotated — the rule contradicts the ruleset it claims to enforce.

1. **Remove `generic-return-requires-returns` from the `enable=` list** in:
   - `config/.pylintrc`
   - `config/.pylintrc-pyi`
   (It is not in `.pylintrc-tests` — no change needed there.)

2. **Do NOT disable the whole `StubDocstringChecker`** — the W9700 `docstring-in-impl` rule remains valid and enabled. Only the W9705 message is disabled.

3. **Regenerate `lint.baseline`**: After disabling, run `uv run lint --overwrite-baseline --baseline lint.baseline` then `uv run lint --baseline lint.baseline` to confirm zero new violations.

## Acceptance
- `grep generic-return-requires-returns config/.pylintrc config/.pylintrc-pyi` → none
- `uv run lint` exits 0
- `uv run pylint src/python_setup_lint/` has no new warnings (existing baselined warnings OK)
- All changes committed with descriptive message
