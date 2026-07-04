Fix all lint gate failures in python-setup so `uv run lint` exits 0.

Read {F}/plan1.md:33-37, 46-49, 51-55, 72-73, 93-101 for context.

## Changes needed

### 1. Fix ruff check errors (5 errors blocking `uv run lint`)

Read `config/ruff.toml` for the actual lint config used by the runner.

a) **`_setup_precommit.py:98`** — `# noqa: S603` is unused (S603 is in per-file-ignores for `src/`). Remove the noqa comment. Also fix S607: replace `["ruff", "--version"]` with `["uv", "run", "ruff", "--version"]` or use `shutil.which("ruff")` to get full path.

b) **`baseline.py:19`** — `from pathlib import Path` is a reimport (already imported on line 6). Remove the duplicate import in the TYPE_CHECKING block.

c) **`_cli_helpers.pyi`** — I001 unsorted imports. Fix import order: standard library first, then third-party.

d) **`tests/integration.py`** — I001 unsorted imports. Fix import order.

### 2. Fix stubtest failure

Read `src/python_setup_lint/setup.py` (the `SetupState` dataclass) and `src/python_setup_lint/setup.pyi` (the stub). The stubtest reports parameter order mismatch for `SetupState.__init__`. Ensure the field order in the .pyi matches the runtime .py exactly. The fields are:
- dep_added, dep_skipped, pylint_plugins_added, pylint_plugins_skipped, precommit_written, precommit_skipped, coding_rules_copied, coding_rules_skipped, config_symlinks_created, config_symlinks_skipped, agents_appended, agents_skipped, errors

### 3. Fix pylint silent-except warnings (5 warnings)

Read the actual source files to see the exact lines:

a) **`_setup_precommit.py:114`** — `except FileNotFoundError: pass`. Add justification comment.

b) **`baseline.py:177`** — `except ValueError: pass`. Add justification comment.

c) **`setup.py:329, 336, 348`** — `except OSError: pass`. Add justification comments.

For all: add `# pylint: disable=...` with a justification comment explaining why silent catch is correct (fallback behavior).

### 4. Fix `_setup_update.pyi` docstring

Read `src/python_setup_lint/_setup_update.pyi` and `src/python_setup_lint/_setup_update.py`. The docstring for `_run_update_steps` says "Run uv sync and uv add --refresh-package python-setup" but the implementation also runs Step 3: re-verify config symlinks. Update the docstring to reflect this.

## Acceptance
- `uv run lint` exits 0
- `uv run stubtest` exits 0
- `uv run ruff check src/` exits 0
- `uv run pylint src/python_setup_lint/` has no new warnings (existing baselined warnings OK)
- All changes committed with descriptive message
