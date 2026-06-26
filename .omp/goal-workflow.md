## Goal Execution Workflow

When asked to execute a goal from a file (e.g., `goal.md`), follow this iterative workflow.

### Workflow

1. **Read the goal file** — load `goal.md` to understand the objective, subgoals, and token budget.

2. **Spawn `plan` agent** — delegate to the `plan` agent with the full goal text. Tell it to produce a written plan breaking the goal into concrete sub-tasks with file paths, dependencies, and sequence. The plan agent writes the plan to `plan{pIt}.md` and reads all applicable `summary{pIt}.md` files to understand what has been done so far (do not read previous plans).

3. **Read `plan{pIt}.md`** — load the written plan. If plan agent believe goal is complete, report final status and exit.

4. **Spawn 2 sequential `task` agents** for the current sub-task:
   - **Implementer** — implements the sub-task per the plan. Full tool access.
   - **Checker** — after the implementer finishes, reviews the changes and indepednetly executes lint/test. Decides: commit the changes (via git commit) if correct, no technical debt, no regression OR minor touch-ups and commit, OR require more `task`/`checker` iterations or rollback (via git restore) if wrong . Reports the decision.

5. Iterate with step 4 till plan is exhausted .
6. Produce a summary report of the plan execution, including any remaining work, and write it to `summary{pIt}.md`.
7. Check pIt — if fewer than {N} iterations have run - go top step 1. It will up to planning agent to re-evaluate remaining work. If {N} iterations are done - report final status.

### Rules

- Each iteration spawns a fresh `plan` agent to re-evaluate remaining work.
- The implementer and checker run sequentially per sub-task.
- The checker MUST verify correctness before committing. If the implementation is wrong, rollback and report what went wrong.
- Track progress: call `goal create` / `goal complete` / `goal get` to manage the goal lifecycle.
- When the goal is complete, call `goal complete` and report the result.
