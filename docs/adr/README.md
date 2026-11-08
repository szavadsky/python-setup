# Architecture Decision Records

This directory is the modernization decision register for python-setup. Every file is a
single-topic ADR. The active records use `## Context`, `## Decision`, and `## Consequences`;
legacy problem statements carry a `## Status` note recording whether they are stale,
superseded, or still current.

## Locations

Per [`CodingRules.md`](../../CodingRules.md) (Project Documentation Layout → Contributor /
Agent), ongoing architecture decisions, data flow, and design notes belong in
[`../../design/`](../../design/) as one-topic-per-file ADRs. This directory holds the
decision register created during the modernization epic; both locations use the same ADR
format, and new contributor or agent architecture notes should be added under `design/`.

## Index

| ADR | Title | Status |
|---|---|---|
| [ADR-001](ADR-001.md) | Golden findings snapshot as the behavior-preservation contract | Stale — resolved at HEAD |
| [ADR-002](ADR-002.md) | Heuristic-gated local decision model for justification checks | Superseded by ADR-009 |
| [ADR-003](ADR-003.md) | Git-stored, self-cleaning decision cache | Superseded by ADR-010 |
| [ADR-004](ADR-004.md) | Progressive saga decomposition with disjoint file ownership | Superseded by ADR-011 |
| [ADR-005](ADR-005.md) | Ruff format check-only contract with shipped config | Stale — resolved at HEAD |
| [ADR-006](ADR-006.md) | Golden contract hardening on merged implementation | Stale — hardened at HEAD |
| [ADR-007](ADR-007.md) | Read-only lint with explicit cache refresh | Superseded by ADR-010 |
| [ADR-008](ADR-008.md) | Progressive epic decomposition after audits | Current |
| [ADR-009](ADR-009.md) | No-go-gated semantic implementation with infrastructure-first delivery | Accepted |
| [ADR-010](ADR-010.md) | Adopt iteration-2 semantic spike contracts as build baseline | Accepted |
| [ADR-011](ADR-011.md) | Validated-map epic decomposition with defined AGENTS split and shift handoff | Accepted |
| [ADR-012](ADR-012.md) | register() missing-beartype exemption for PyLinter circular import | Accepted |

## Design notes

Contributor- and agent-facing architecture notes live under `design/`:

| Design note | Title |
|---|---|
| [0001](../../design/0001-compose-config-temp-dir.md) | Config composers — pyright writes to cwd, ruff writes to temp-dir |
| [0002](../../design/0002-ty-src-only-exception.md) | ty src-only exception |
