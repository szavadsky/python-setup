# .omp/ Agents — TLDR

## Purpose

Goal-execution agentic system: **plan → orchestrate → verify**. A command (`goal-flow.md`) drives
iterative cycles where a planner produces an implementation plan and an orchestrator delegates
execution across waves of subtasks. Role-based tool assignment enforces least privilege — each
agent gets only the tools its role requires.

## Call tree

```
goal-flow.md (command, eval loop)
├── plan-goal-execution          [full_read_only + plan-write]
│   ├── fact-finder              [full_read_only + web_search]
│   ├── librarian                (bundled)
│   ├── oracle                   (bundled)
│   ├── designer                 (bundled)
│   └── task                     (bundled, generic)
├── orchestrate-goal-execution   [minimum_orchestrator]
│   ├── orchestrate-subtask      [minimum_orchestrator]  (per subtask)
│   │   ├── implement-subtask    [full_developer]
│   │   │   ├── task             (bundled)
│   │   │   ├── fact-finder       [full_read_only + web_search]
│   │   │   ├── quick_task        (bundled)
│   │   │   └── librarian         (bundled)
│   │   └── check-and-commit-subtask [reviewer_committer]
│   │       ├── quick_task        (bundled)
│   │       └── librarian         (bundled)
│   ├── wave-end-checkpoint       [full_developer]  (per wave end)
│   ├── fact-finder              [full_read_only + web_search]
│   └── oracle                   (bundled)
└── plan-completeness-checker    [full_read_only + delegation]
    ├── task                     (bundled)
    ├── fact-finder              [full_read_only + web_search]
    └── oracle                   (bundled)
```

## Tool-assignment principles

1. **Least privilege** — each agent gets only the tools its role requires; no blanket access.
2. **Read-only agents get bash for measurement only** — investigation agents (fact-finder,
   plan-completeness-checker) have `bash` but prompt instructions enforce non-changing use only.
3. **Orchestrators get minimal tools** — read + spawn + status write + track. No bash, no edit,
   no LSP, no debug, no eval. They delegate all project work.
4. **Web search via webmcp** — when an agent needs web search, it uses `mcp__webmcp_scrape_batch`
   and `mcp__webmcp_search_engine_batch`. The built-in `web_search` tool is NEVER used.
5. **Implementers get full developer toolset** — the doer (implement-subtask, wave-end-checkpoint)
   gets all software/dev tools including edit, write, bash, eval, LSP, AST, debug.
6. **Planners get read-only + plan-write** — exploration tools (read, grep, glob, lsp, ast_grep)
   plus `write` for the plan artifact. No bash (enforces delegation).

## Roles → tools

Tools auto-added by the runtime (not listed in agent frontmatter): `yield` (when `tools:` is
specified), `task` (when `spawns:` is non-empty and depth allows), `irc` (ensured in explicit
tool lists).

| Role | Explicit tools |
|------|---------------|
| `full_developer` | read, bash, edit, write, ast_grep, ast_edit, eval, glob, grep, lsp, inspect_image, debug, todo, resolve, report_tool_issue, generate_image, checkpoint, rewind, yield |
| `full_read_only` | read, bash, grep, glob, lsp, ast_grep, inspect_image, debug, todo, checkpoint, rewind, yield, report_tool_issue |
| `web_search` | mcp__webmcp_scrape_batch, mcp__webmcp_search_engine_batch |
| `docs_edit` | read, edit, write, grep, glob, yield |
| `status_edit` | read, write, yield |
| `status_report` | write, yield |
| `minimum_orchestrator` | read, grep, glob, write, job, todo, yield |
| `reviewer_committer` | read, bash, grep, glob, lsp, ast_grep, inspect_image, todo, yield |

## Agents → roles

| Agent | Role | Spawns |
|-------|------|--------|
| `orchestrate-goal-execution` | minimum_orchestrator | orchestrate-subtask, wave-end-checkpoint, fact-finder, oracle |
| `plan-goal-execution` | full_read_only + plan-write | fact-finder, librarian, oracle, designer, task |
| `orchestrate-subtask` | minimum_orchestrator | implement-subtask, check-and-commit-subtask |
| `implement-subtask` | full_developer | task, fact-finder, quick_task, librarian |
| `check-and-commit-subtask` | reviewer_committer | quick_task, librarian |
| `plan-completeness-checker` | full_read_only + delegation | task, fact-finder, oracle |
| `fact-finder` | full_read_only + web_search | — |
| `wave-end-checkpoint` | full_developer (full edit access) | — |

## Critical files & anchors

- `.omp/agents/orchestrate-goal-execution.md` — frontmatter `tools:` (lines 4–13) and `spawns:` (lines 15–19); prompt body step 3.4 (lines 82–88). Three edits: trim tools, swap spawns, rewrite step 3.4.
- `.omp/agents/plan-goal-execution.md` — frontmatter between `description` (line 3) and `spawns:` (line 4). Insert `tools:` block. No prompt body change.
- `.omp/agents/implement-subtask.md` — frontmatter `tools:` list (lines 4–25). Insert `- eval` after `- debug` (line 15).
- `.omp/agents/wave-end-checkpoint.md` — new file. Full agent definition with frontmatter + prompt body.
- `.omp/README.md` — new file. TLDR with call tree, principles, role/agent tables.
