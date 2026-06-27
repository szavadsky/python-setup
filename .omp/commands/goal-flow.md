# Goal Execution Workflow

Role: **mechanical** orchestration. All technical work delegated to subagents.
Achieve goal from `{F}/goal.md`. Iterative.

## Variables

| Var | Meaning |
|-----|---------|
| `{F}` | Goal file folder (contains `goal.md`) |
| `{N}` | Max iterations before final report |

## Workflow

### 1. Locate goal file

Confirm `{F}/goal.md` exists. Do NOT read or interpret — delegate to `plan-goal-execution` (higher reasoning).

### 2–5. Iterate (plan → check → orchestrate → loop)

Steps 2–5 are purely mechanical. Run them as a single `eval` code block: a `for` loop over iterations, spawning the two schema-checked subagents with the **target plan path** as their only argument and branching on their structured `status`.

Both subagents accept only `{F}/plan{pIt}.md` (the plan path). The planner reads `{F}/goal.md` + prior `summary{1..pIt-1}.md` and writes that plan path; the orchestrator reads it and writes `{F}/summary{pIt}.md`. `{pIt}` is owned by the caller and baked into the path — no scanning, no races.

```python
F, N = "{F}", {N}

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["plan_created", "goal_complete"]},
        "plan_path": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": ["status", "plan_path", "summary"],
}
IMPL_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["implemented", "partial"]},
        "summary_path": {"type": "string"},
        "concerns": {"type": "string"},
    },
    "required": ["status", "summary_path", "concerns"],
}

final = "incomplete"
for pIt in range(1, N + 1):
    plan_path = f"{F}/plan{pIt}.md"

    # Step 2 — plan (planner reads {F}/goal.md + prior summaries, writes plan_path).
    plan_result = agent(plan_path, agent_type="plan-goal-execution", schema=PLAN_SCHEMA)

    # Step 3 — termination check.
    if plan_result["status"] == "goal_complete":
        final = f"goal complete after {pIt} planning pass(es)"
        break

    # Step 4 — orchestrate (orchestrator reads plan_path, writes {F}/summary{pIt}.md).
    impl_result = agent(plan_path, agent_type="orchestrate-goal-execution", schema=IMPL_SCHEMA)

    # Step 5 — iteration count check.
    if pIt == N:
        final = f"max iterations ({N}) reached; last summary: {impl_result['summary_path']}"
        break
    # else: loop — planner re-evaluates remaining work against the new summary.

print(final)
```

The `agent()` calls pass only the plan path (a file name). The `schema=` args activate  structured-output path (parsed object returned + schema rendered into the subagent's system prompt);