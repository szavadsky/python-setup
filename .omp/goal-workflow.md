## Goal Execution Workflow

When asked to execute a goal from a file (e.g., `goal.md`), follow this iterative workflow.

### Workflow

1. **Read the goal file** — load `goal.md` to understand the objective, subgoals, and token budget.

2. **Spawn `plan` agent** — delegate to the `plan` agent with the full goal text. Tell it to produce a written plan breaking the goal into concrete sub-tasks with file paths, dependencies, and sequence. The plan agent writes the plan to `plan.md`.

3. **Read `plan.md`** — load the written plan.

4. **Spawn 2 sequential `task` agents** for the current sub-task:
   - **Implementer** — implements the sub-task per the plan. Full tool access.
   - **Checker** — after the implementer finishes, reviews the changes and executes lint/test. Decides: commit the changes (via git commit) if correct, minor touch-ups and commit, or rollback (via git restore) if wrong. Reports the decision.

5. **Check iteration count** — if fewer than 5 iterations have run and the goal is not complete, go to step 2 (re-plan remaining work). If 5 iterations are done or the goal is complete, report final status.

### Rules

- Each iteration spawns a fresh `plan` agent to re-evaluate remaining work.
- The implementer and checker run sequentially per sub-task.
- The checker MUST verify correctness before committing. If the implementation is wrong, rollback and report what went wrong.
- Track progress: call `goal create` / `goal complete` / `goal get` to manage the goal lifecycle.
- When the goal is complete, call `goal complete` and report the result.
