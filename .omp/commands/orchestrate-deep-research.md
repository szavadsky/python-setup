# Deep Research Orchestrator

Role: **mechanical** orchestration of a 5-stage deep research pipeline.
Accepts a research prompt from the user, bootstraps a project directory,
and runs through prelim research → heavy research → drafting → illustration → final production.

## Variables

| Var | Meaning |
|-----|---------|
| `{P}` | User research prompt (the full description of what to research) |

## Workflow

### 1. Confirm prompt

`{P}` MUST be non-empty. If empty, exit with error message.

### 2. Run the eval

Run the Python code block below in an `eval` cell. It handles all logic —
project bootstrap, state machine with resume, stage delegation, atomic state
persistence, and infer_stage fallback. Do NOT reason about file content or
stage transitions: the code handles it.

```python
import json, os, re, shutil
from datetime import datetime
from pathlib import Path

user_prompt = "{P}"

# ── Helpers ───────────────────────────────────────────────────────────

def slugify(text):
    """Convert free-form text to a filesystem-safe directory name."""
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:64]

STAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["complete", "partial", "failed"]},
        "summary": {"type": "string"},
        "errors": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "summary"],
}

DIRECTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "researchDirections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "topic": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["slug", "topic", "rationale"],
            },
        }
    },
    "required": ["researchDirections"],
}

def call_agent(prompt, agent_name, schema, retries=2):
    for attempt in range(1, retries + 2):
        try:
            res = agent(prompt, agent=agent_name, schema=schema)
            if not isinstance(res, dict):
                raise ValueError(f"bad output: {res!r}")
            return res
        except Exception as e:
            log(f"call_agent: {agent_name} glitch attempt {attempt}: {e}")
    raise RuntimeError(f"{agent_name} failed after {retries + 1} attempts")


def save_state(p_dir, state):
    """Atomic state write: .tmp then os.rename."""
    tmp = p_dir / ".research-state.json.tmp"
    tmp.write_text(json.dumps(state, indent=2))
    os.rename(str(tmp), str(p_dir / ".research-state.json"))


def load_state(p_dir):
    """Load state, returning None if missing or corrupt."""
    f = p_dir / ".research-state.json"
    if f.is_file():
        try:
            return json.loads(f.read_text())
        except Exception:
            pass
    return None


def infer_stage(p_dir):
    """F21 fallback: infer current stage from file artifacts."""
    if (p_dir / "output" / f"{p_dir.name}.pdf").exists():
        return "final"
    if (p_dir / "diagram_guide.tex").is_file():
        return "illustration"  # guide exists → illustration started
    if (p_dir / "reportOutline.md").is_file() and (p_dir / "sections").is_dir():
        return "illustration"  # outline + sections → past drafting
    if (p_dir / "reportOutline.md").is_file():
        return "drafting"
    if any(p_dir.rglob("*.jsonl")):
        return "drafting"  # research exists but no outline yet
    if (p_dir / "task.md").is_file():
        return "prelim"
    return "prelim"


# ── Bootstrap (Stage 0) ───────────────────────────────────────────────

p_slug = slugify(user_prompt)
p_dir = Path("research") / p_slug
p_dir.mkdir(parents=True, exist_ok=True)

for d in ["sections", "figures", "output", "build/pages", "build/figures"]:
    (p_dir / d).mkdir(parents=True, exist_ok=True)

if not (p_dir / "task.md").exists():
    (p_dir / "task.md").write_text(user_prompt.strip())

# Copy assets (styles/, tools/, Makefile) if not already present
for name in ["styles", "tools", "Makefile"]:
    src = Path("assets") / name
    dst = p_dir / name
    if not dst.exists() and src.exists():
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)


# ── State machine ─────────────────────────────────────────────────────

stage_order = ["prelim", "heavy", "drafting", "illustration", "final"]

# Load or initialize state
state = load_state(p_dir)
if state is None:
    state = {
        "stage": "prelim",
        "completed_stages": [],
        "current_stage": "prelim",
        "directions": {},
        "outline_status": "pending",
        "compile_status": "pending",
        "page_count": 0,
        "subagent_outputs": {},
        "errors": [],
    }

# Infer current_stage if state is corrupt but files exist
if not isinstance(state.get("current_stage"), str) or state["current_stage"] not in stage_order:
    inferred = infer_stage(p_dir)
    state["current_stage"] = inferred
    log(f"infer_stage → {inferred}")

# Determine where to start
start_idx = stage_order.index(state["current_stage"])

# ── Stage 1: Prelim research (inline) ─────────────────────────────────
if start_idx <= 0 and "prelim" not in state["completed_stages"]:
    log("Stage 1: prelim research")
    try:
        result = call_agent(
            f"Read {p_dir}/task.md, then launch prelim_research_assistants "
            f"to identify 8-25 research directions. Return structured directions.",
            "prelim_research_planner",
            DIRECTIONS_SCHEMA,
        )
        for d in result["researchDirections"]:
            state["directions"][d["slug"]] = {
                "status": "pending",
                "assignment_files": [],
            }
        state["completed_stages"].append("prelim")
        state["current_stage"] = "heavy"
        state["stage"] = "heavy"
        save_state(p_dir, state)
        log("Stage 1 complete")
    except Exception as e:
        err = {"stage": "prelim", "agent": "prelim_research_planner", "message": str(e), "timestamp": str(datetime.now())}
        state["errors"].append(err)
        save_state(p_dir, state)
        raise

# ── Stage 2: Heavy research (delegated) ───────────────────────────────
if start_idx <= 1 and "heavy" not in state["completed_stages"]:
    log("Stage 2: heavy research")
    try:
        result = call_agent(
            f"Orchestrate Stage 2 for {p_dir}. "
            f"Directions: {json.dumps(state.get('directions', {}))}",
            "heavy-research-director",
            STAGE_SCHEMA,
        )
        state["outline_status"] = "complete"
        state["completed_stages"].append("heavy")
        state["current_stage"] = "drafting"
        state["stage"] = "drafting"
        save_state(p_dir, state)
        log("Stage 2 complete")
    except Exception as e:
        err = {"stage": "heavy", "agent": "heavy-research-director", "message": str(e), "timestamp": str(datetime.now())}
        state["errors"].append(err)
        save_state(p_dir, state)
        raise

# ── Stage 3: Drafting (delegated) ─────────────────────────────────────
if start_idx <= 2 and "drafting" not in state["completed_stages"]:
    log("Stage 3: drafting")
    try:
        result = call_agent(
            f"Orchestrate Stage 3 for {p_dir}. "
            f"Outline at {p_dir}/reportOutline.md",
            "drafting-director",
            STAGE_SCHEMA,
        )
        state["compile_status"] = "complete"
        state["completed_stages"].append("drafting")
        state["current_stage"] = "illustration"
        state["stage"] = "illustration"
        save_state(p_dir, state)
        log("Stage 3 complete")
    except Exception as e:
        err = {"stage": "drafting", "agent": "drafting-director", "message": str(e), "timestamp": str(datetime.now())}
        state["errors"].append(err)
        save_state(p_dir, state)
        raise

# ── Stage 4: Illustration (delegated) ─────────────────────────────────
if start_idx <= 3 and "illustration" not in state["completed_stages"]:
    log("Stage 4: illustration")
    try:
        result = call_agent(
            f"Orchestrate Stage 4 for {p_dir}",
            "illustration-director",
            STAGE_SCHEMA,
        )
        state["completed_stages"].append("illustration")
        state["current_stage"] = "final"
        state["stage"] = "final"
        save_state(p_dir, state)
        log("Stage 4 complete")
    except Exception as e:
        err = {"stage": "illustration", "agent": "illustration-director", "message": str(e), "timestamp": str(datetime.now())}
        state["errors"].append(err)
        save_state(p_dir, state)
        raise

# ── Stage 5: Final production (inline) ────────────────────────────────
if start_idx <= 4 and "final" not in state["completed_stages"]:
    log("Stage 5: final production")
    try:
        # Compile LaTeX -> PDF
        ret = os.system(f"scripts/container-run.sh make {p_slug}-pdf")
        if ret != 0:
            raise RuntimeError(f"make {p_slug}-pdf failed with exit code {ret}")

        # Copy PDF from build/ to output/ for master command consumption
        os.makedirs(f"{p_dir}/output", exist_ok=True)
        shutil.copy2(f"{p_dir}/build/{p_slug}/{p_slug}.pdf", f"{p_dir}/output/{p_slug}.pdf")

        # Compile DOCX
        os.system(f"scripts/container-run.sh make {p_slug}-docx")

        # Extract page count
        page_count_str = os.popen(
            f"scripts/container-run.sh pdfinfo {p_dir}/output/{p_slug}.pdf"
            " | awk '/^Pages:/{print $2}'"
        ).read().strip()
        page_count = int(page_count_str) if page_count_str else 0

        # Render pages as PNG for formatting-agent (one page at a time)
        if page_count > 0:
            (p_dir / "build" / "pages").mkdir(parents=True, exist_ok=True)
            for i in range(1, page_count + 1):
                os.system(
                    f"scripts/container-run.sh pdftoppm -png -r 100 -f {i} -l {i} "
                    f"{p_dir}/output/{p_slug}.pdf {p_dir}/build/pages/page-{i}"
                )

        FORMAT_SCHEMA = {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "status": {"type": "string", "enum": ["perfect", "improved", "failed"]},
            },
            "required": ["summary", "status"],
        }

        # Per-page formatting (sequential)
        for i in range(1, page_count + 1):
            call_agent(
                f"Review page {i} of {p_dir}/build/pages/page-{i}.png. "
                f"Doc slug: {p_slug}. Project dir: {p_dir}. "
                f"Apply layout fixes to {p_dir}/sections/",
                "formatting-agent",
                FORMAT_SCHEMA,
            )

        # Re-compile after formatting adjustments
        os.system(f"scripts/container-run.sh make {p_slug}-pdf")

        state["page_count"] = page_count
        state["completed_stages"].append("final")
        state["current_stage"] = "complete"
        state["stage"] = "complete"
        save_state(p_dir, state)
        log("Stage 5 complete")
    except Exception as e:
        err = {"stage": "final", "agent": "N/A (inline)", "message": str(e), "timestamp": str(datetime.now())}
        state["errors"].append(err)
        save_state(p_dir, state)
        raise

print(f"Complete: {p_dir}/output/{p_slug}.pdf ({state.get('page_count', 0)} pages)")
```
