from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from .setup import SetupState

# ── Constants ───────────────────────────────────────────────────────

_AGENTS_SENTINEL: str = "<!-- python-setup:pre-commit -->"
_AGENTS_SENTINEL_END: str = "<!-- /python-setup:pre-commit -->"

_PRECOMMIT_TEMPLATE: str = """\
# See https://pre-commit.com for more information
# See https://pre-commit.com/hooks.html for more hooks
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: {ruff_rev}
    hooks:
      - id: ruff-format
      - id: ruff-check
        args: [--fix, --exit-non-zero-on-fix]
  - repo: local
    hooks:
      - id: lint
        name: lint
        entry: python-setup lint --fix --baseline lint.baseline
        language: system
        types: [python]
        pass_filenames: false
"""

_RUFF_FALLBACK_REV: str = "v0.14.10"

_AGENTS_SNIPPET: str = """\

{open_sentinel}
## Pre-commit hooks

Install git hooks after cloning:

```bash
uv run pre-commit install
```

- **`git commit`** triggers fast hooks: `ruff-format` (auto-format) and `ruff-check` (auto-fix). Both run silently and apply changes automatically.
- **`git commit`** also triggers the full lint pipeline (`python-setup lint --fix --baseline lint.baseline`). The `lint` hook autofixes ALL tools that support it (ruff, rumdl, ty) via the wrapper's `--fix` route, then re-runs the baseline-gated verification pass. Autofix is **courtesy**: it skips files where staged AND unstaged changes overlap (avoids conflicts with the staged blob), reverts any file a tool's fix breaks parseability on (E999 canary), and never blocks — only NEW violations (regressions) vs the baseline fail the hook. Autofix never blocks the commit; files with both staged and unstaged changes are skipped, and any file a fix breaks parseability on is reverted in-memory.
- **Autofix opt-out**: set `PYTHON_SETUP_LINT_NO_AUTOFIX=1` to disable autofix for the run (the `--fix` CLI flag still parses; the runner flips autofix off internally before the loop). Useful when you want only the verification pass to run.
- **Baseline regeneration**: When you intentionally want to accept the current violation state, run:

  ```bash
  python-setup lint --overwrite-baseline --baseline lint.baseline
  ```

  Commit the updated `lint.baseline` alongside your changes.
{close_sentinel}
"""


# ── Helpers ─────────────────────────────────────────────────────────


def _atomic_write(path: Path, content: str) -> None:
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp_path = tempfile.NamedTemporaryFile(  # noqa: SIM115  # pylint: disable=consider-using-with  # intentional: need delete=False + manual cleanup in finally
        dir=tempfile.gettempdir(), prefix="psl_setup_", suffix=path.suffix, delete=False
    ).name
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
        shutil.move(tmp_path, str(path))
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)


# ── Install steps ────────────────────────────────────────────────────


def _step_precommit(state: SetupState, project_dir: Path) -> None:
    precommit_path = project_dir / ".pre-commit-config.yaml"
    if precommit_path.exists():
        state.precommit_skipped = True
        print("  [pre-commit] .pre-commit-config.yaml already exists — not overwriting")
        return

    # Resolve installed ruff version for the pre-commit hook rev.
    ruff_rev = _RUFF_FALLBACK_REV
    try:
        proc = subprocess.run(  # noqa: S603  # ruff is a trusted project tool
            ["ruff", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            # ruff --version output: "ruff 0.15.17" or similar
            version_str = proc.stdout.strip()
            # Parse the version number from the output
            for part in version_str.split():
                # Find the first part that looks like a version number
                if part[0].isdigit() or (part[0] == "v" and len(part) > 1 and part[1].isdigit()):
                    version = part.lstrip("v")
                    ruff_rev = f"v{version}"
                    break
    except FileNotFoundError:
        pass

    content = _PRECOMMIT_TEMPLATE.format(ruff_rev=ruff_rev)
    _atomic_write(precommit_path, content)
    state.precommit_written = True
    print("  [pre-commit] Wrote .pre-commit-config.yaml")


def _step_agents_snippet(state: SetupState, project_dir: Path) -> None:
    agents_path = project_dir / "AGENTS.md"
    if not agents_path.exists():
        state.agents_skipped = True
        print("  [agents] AGENTS.md not found — skipping snippet append")
        return

    content = agents_path.read_text(encoding="utf-8")
    if _AGENTS_SENTINEL in content:
        state.agents_skipped = True
        print("  [agents] AGENTS.md already contains python-setup snippet — skipping")
        return

    snippet = _AGENTS_SNIPPET.format(
        open_sentinel=_AGENTS_SENTINEL,
        close_sentinel=_AGENTS_SENTINEL_END,
    )
    new_content = content.rstrip("\n") + snippet
    _atomic_write(agents_path, new_content)
    state.agents_appended = True
    print("  [agents] Appended pre-commit setup instructions to AGENTS.md")
