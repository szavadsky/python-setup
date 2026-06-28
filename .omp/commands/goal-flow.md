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

### 2–5. Iterate (plan → orchestrate → loop)

Steps 2–5 are purely mechanical. Run them as a single `eval` code block: a `for` loop over iterations, spawning the two schema-checked subagents with the **target plan path** as their only argument and branching on their structured `status`.

Both subagents accept only `{F}/plan{pIt}.md` (the plan path). The planner reads `{F}/goal.md` + prior `summary{1..pIt-1}.md` and writes that plan path; the orchestrator reads it and writes `{F}/summary{pIt}.md`. `{pIt}` is owned by the caller and baked into the path — no scanning, no races.

The loop is crash-resilient and restart-aware: it resumes from the highest existing `summary{K}.md`; each `agent()` call retries twice on subagent glitches; the loop halts on `failed`/`blocked` status.
After orchestration, a `plan-completeness-checker` agent verifies completeness against the plan. If gaps are found, the orchestrator is relaunched with fresh context up to 2 times, passing the concerns forward as a follow-up message. Remaining concerns after 2 follow-ups are appended non-destructively to the summary.

```python
import shutil
from pathlib import Path

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
        "status": {"type": "string", "enum": ["implemented", "partial", "failed", "blocked"]},
        "summary_path": {"type": "string"},
        "concerns": {"type": "string"},
        "committed": {"type": "boolean"},
    },
    "required": ["status", "summary_path", "concerns", "committed"],
}
CHECK_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["complete", "concerns"]},
        "concerns": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": ["status", "concerns", "summary"],
}
MAX_FOLLOWUPS = 2

def call_agent(plan_path, agent_name, schema, retries=2):
    last_err = None
    for attempt in range(retries + 1):
        try:
            res = agent(plan_path, agent=agent_name, schema=schema)
            if not isinstance(res, dict) or res.get("status") not in schema["properties"]["status"]["enum"]:
                raise ValueError(f"bad structured output: {res!r}")
            return res
        except Exception as e:
            last_err = e
            if attempt < retries:
                continue
    raise last_err

goal_file = Path(f"{F}/goal.md")
if not goal_file.is_file():
    raise ValueError(f"goal file not found: {F}/goal.md")

# Restart-aware: resume after the highest completed summary.
start_pIt = 1
for k in range(N, 0, -1):
    if Path(f"{F}/summary{k}.md").is_file():
        start_pIt = max(1, k + 1)
        break

final = "incomplete"
for pIt in range(start_pIt, N + 1):
    plan_path = f"{F}/plan{pIt}.md"

    # Back up before overwrite (RCA-F).
    if Path(plan_path).is_file():
        shutil.copy2(plan_path, plan_path + ".bak")

    # Step 2 — plan (planner reads {F}/goal.md + prior summaries, writes plan_path).
    plan_result = call_agent(plan_path, "plan-goal-execution", PLAN_SCHEMA)

    # Step 3 — termination check.
    if plan_result["status"] == "goal_complete":
        final = f"goal complete after {pIt} planning pass(es)"
        break

    # Step 4 — orchestrate (orchestrator reads plan_path, writes {F}/summary{pIt}.md).
    summary_path = f"{F}/summary{pIt}.md"
    if Path(summary_path).is_file():
        shutil.copy2(summary_path, summary_path + ".bak")
    impl_result = call_agent(plan_path, "orchestrate-goal-execution", IMPL_SCHEMA)

    # --- Follow-up completeness loop (relaunch orchestrator on checker concerns) ---
    if impl_result["status"] not in {"failed", "blocked"}:
        followup_count = 0
        while followup_count <= MAX_FOLLOWUPS:
            check_result = call_agent(plan_path, "plan-completeness-checker", CHECK_SCHEMA)
            if check_result["status"] == "complete":
                break
            # Concerns found — relaunch orchestrator with follow-up message (fresh context).
            if followup_count < MAX_FOLLOWUPS:
                followup_msg = plan_path + "\n\nFollow-up launch — plan completeness checker had these concerns:\n" + check_result["concerns"]
                impl_result = call_agent(followup_msg, "orchestrate-goal-execution", IMPL_SCHEMA)
                followup_count += 1
                if impl_result["status"] in {"failed", "blocked"}:
                    break
            else:
                # Follow-up budget exceeded — append concerns non-destructively to summary.
                summary_path = impl_result.get("summary_path", f"{F}/summary{pIt}.md")
                with open(summary_path, "a") as f:
                    f.write("\n\n## Extra concerns from plan completeness checker\n\n" + check_result["concerns"])
                break

    # Step 5 — halt on failure states (RCA-E: loop never inspected concerns).
    if impl_result["status"] in {"failed", "blocked"}:
        final = f"halted at iteration {pIt}: {impl_result['status']} — {impl_result.get('concerns','')}"
        break

    if pIt == N:
        final = f"max iterations ({N}) reached; last summary: {impl_result['summary_path']}"
        break
    # else: loop — planner re-evaluates remaining work against the new summary.

print(final)
```

The `agent()` calls pass only the plan path (a file name). The `schema=` args activate structured-output path (parsed object returned + schema rendered into the subagent's system prompt).
