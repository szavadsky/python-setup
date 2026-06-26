---
name: goal-flow
description: Execute iterative goal workflow from goal.md — plan, implement, verify, iterate
model: task
thinking: high
---

# Goal Execution Workflow

Execute goal from `{F}/{goal}.md`. Iterative workflow.

## Variables

| Var | Meaning |
|-----|---------|
| `{F}` | Folder containing goal file |
| `{goal}` | Goal filename (without `.md`) |
| `{pIt}` | Current plan iteration number |
| `{N}` | Max iterations before final report |

## Workflow

### 1. Locate goal file

Locate `{F}/{goal}.md`. Do NOT read or understand content — delegate to plan agent (higher reasoning capability).

### 2. Spawn plan agent

Delegate full user prompt (DO NOT ENRICH/INTERPRET) + filename (not content) of `{F}/{goal}.md`. Use this template:

```text
Goal: {F}/{goal}.md (iteration {pIt}, max {N})

Read applicable {F}/summary{pIt-1}.md files (not previous plans).
Review code quality and intent match of prior iterations. Identify improvements.

Produce written plan: concrete sub-tasks, file paths, dependencies, sequence.
Write plan to {F}/plan{pIt}.md.


Planner MUST limit DIY searching, test running, reading. Launch `explore`/`task` subagents instead.
MUST START from launching `explore` subagent(s) and add more as needed
```
WAIT for plan job to complete
Plan agent writes `{F}/plan{pIt}.md`. Reads applicable `{F}/summary{pIt}.md` files (not previous plans).


### 3. Read plan

Load `{F}/plan{pIt}.md`. Plan agent reports goal already complete (and nothing delayed till next Phase) → report final status, exit.

### 4. Execute sub-tasks

Per sub-task, spawn 2 sequential `task` agents:

- **Implementer** — implements sub-task per plan. Full tool access.
- **Checker** — after implementer finishes, review changes, independently execute lint/test. Decide:
  - Commit (git commit) if correct, no technical debt, no regression
  - Minor touch-ups then commit
  - Require more `task`/`checker` iterations or rollback (git restore) if wrong. Report decision.

**Parallel sub-tasks**: spawn in isolation. Launch third `task` agent to merge results while no other agents working. Regression check after each merge.

### 5. Iterate

Repeat step 4 until plan exhausted.

### 6. Summary report

Write plan execution + remaining work to `{F}/summary{pIt}.md`.

### 7. Check iteration count

- Fewer than `{N}` iterations → return to step 1. Planning agent re-evaluates remaining work.
- `{N}` iterations done → report final status.

## Rules

- Each iteration spawns fresh `plan` agent to re-evaluate remaining work.
- Implementer and checker run sequentially per sub-task.
- Checker MUST verify correctness, lack of regressions before committing. Wrong implementation → rollback, report what went wrong.
