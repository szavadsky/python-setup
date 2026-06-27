
# Goal Execution Workflow

Role: **mechanical** orchestration. All technical work delegated to subagents.
Achieve goal from `{F}/{goal}.md`. Iterative.

## Variables

| Var | Meaning |
|-----|---------|
| `{F}` | Goal file folder |
| `{goal}` | Goal filename (no `.md`) |
| `{pIt}` | Current plan iteration |
| `{N}` | Max iterations before final report |

## Workflow

### 1. Locate goal file

Find `{F}/{goal}.md`. Do NOT read or interpret — delegate to plan agent (higher reasoning).

### 2. Spawn plan agent

Pass filename (not content) of `{F}/{goal}.md` + raw user instructions (no enrichment) except iteration count. Template:

```text
Goal: {F}/{goal}.md (iteration {pIt}, max {N})
{{Additional user instructions if any}}
Read applicable {F}/summary{pIt-1}.md files (not previous plans).
Review code quality and intent match of prior iterations. Be adversarial. Catch and rectify brush-offs, slops, and technical debt. Identify improvements.

Produce written plan: concrete sub-tasks, file paths, dependencies, sequence.
Write plan to {F}/plan{pIt}.md.

Planner MUST limit DIY searching, test running, reading. Launch `explore`/`task`/`librtarian` subagents instead.
MUST START from launching `explore` subagent(s) and add more as needed.
Consult high-reasoning `oracle` agent on uncertainties/alternatives/LOO.
Specify scope of each workstream/task.
Return only `plan created, work to do` or `Plan explains no material improvements needed, goal fully achieved`.
Provide  plan that fully implements goal.
```
WAIT for plan job. Do not poll.

### 3. Check termination

Plan agent reports goal complete (nothing delayed) → report final status, exit.

### 4. Use task agent to implement plan

Launch single `task` agent. Template:

```
Your role: orchestrate (no DIY) implementation of `{F}/plan{pIt}.md` via focused `task` subagents.

## 1. Load `{F}/plan{pIt}.md`
## 2. Plan execution
   - Split into manageable (1..3 files, <200 LoC changes) tasks. Avoid scope creep.
   - Do not override planner's technical decisions (high-reasoning).
## 3. Execute plan
   - ≥2 subagents per identified subtask.
   - **Implementer** — implements per plan. Full tool access. Verify tests + lint pass.
   - **Checker** — after implementer, review changes, independently run lint/test. Verify bona fide completion without regression. Decide:
     - Commit if correct, no tech debt, no regression.
     - Minor touch-ups then commit.
     - More `task`/`checker` iterations or rollback (`git restore`) if wrong. Report decision.
   - **Parallel sub-tasks**: spawn in isolation. Launch third `task` agent to merge results while no other agents active. Regression check after each merge.
   - When additional subagents needed: checker identifies fix, or work + resolve merge conflict.
   - Use `explore` subagent to understand status / define delta.
## 4. Keep executing until plan fully implemented.
## 5. Summary report

Write execution summary + concerns to `{F}/summary{pIt}.md`.
```

### 5. Check iteration count

Once task subagent from step 4 done: 

- Fewer than `{N}` iterations → return to step 1. Planner re-evaluates remaining work.
- `{N}` iterations done → report final status.

