# 0002 — ty src-only exception

## Status
Accepted.

## Context
ty uses `# ty: ignore` syntax, not mypy's `# type: ignore[code]`. MyPy suppressions in tests/ are invisible to ty. Re-enabling ty on tests/ would require ~38 duplicate ty-specific ignore comments.

## Decision
Keep `default_paths=["src"]` for ty. Exception documented by oracle review.

## Evidence
- Syntax incompatibility: ty honors `# ty: ignore` only, not `# type: ignore[code]`
- 38 false positives on test-fixture patterns (monkeypatch, dict-invariance, isinstance-narrowing)
- 67 mypy `# type: ignore` suppressions in tests/ (independent coverage)
- mypy + pyright both certify tests clean
- Zero marginal type-safety gain from re-enabling ty on tests

## Date
2026-07-03