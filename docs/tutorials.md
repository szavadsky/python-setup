# Tutorials

## 1. Install

Add the dependency and run the installer:

```bash
uv add python-setup
uv run python-setup install
```

The installer writes relative config symlinks (portable across git checkouts and worktrees), registers custom pylint checkers, and creates the `lint.baseline` file. For the optional semantic justification rerunner:

```bash
uv add "python-setup[semantic]"
```

See [troubleshooting.md](troubleshooting.md) if `uv run python-setup install` fails with a tool-not-found error.

## 2. First lint

```bash
uv run lint
```

Runs all 13 lint tools sequentially. On a fresh project the first run may produce violations — that's expected.

## 3. Read output

Output is grouped per tool with a summary header:

```
── ruff ──────────────────────────────────────
src/mod.py:3:1: F401 [*] `os` imported but unused
Found 1 error.
── ruff ────────────────────────────────────── PASSED

── pylint ────────────────────────────────────
src/mod.py:1:0: W0611: Unused import os (unused-import)
────────────────────────────────────────────── FAILED (1 violation)

── mypy ──────────────────────────────────────
src/mod.py:1: error: Module has no attribute "x"
────────────────────────────────────────────── FAILED (1 violation)
```

Each tool section shows:

- **Tool name** in a banner line.
- **Violations** with file, line, code, and message.
- **PASSED** / **FAILED** status with violation count.

At the end a summary table:

```
╔══════════════════════╤════════╤══════════════╗
║ Tool                 │ Status │ Violations    ║
╠══════════════════════╪════════╪══════════════╡
║ ruff                 │ PASSED │             0 ║
║ pylint               │ FAILED │             1 ║
║ mypy                 │ FAILED │             1 ║
║ ...                  │   ...  │           ... ║
╚══════════════════════╧════════╧══════════════╝
```

New violations (not in `lint.baseline`) cause a non-zero exit. Pre-existing violations are reported but do not block CI.

## 4. Fix a violation

Example: pylint reports `W0611: Unused import os (unused-import)`.

1. Open the file and remove the unused import.
2. Re-run lint:

```bash
uv run lint
```

The pylint section now shows `PASSED` with 0 violations. Repeat for each failing tool until the summary table is all green.

For violations you intend to keep (e.g. a false positive), add a suppression comment:

```python
import os  # pylint: disable=unused-import
```

See [semantic-justification.md](semantic-justification.md) for the justification validation system.

## 5. Baseline workflow

When you add new code with pre-existing violations (e.g. after a large refactor), freeze them into the baseline so only *new* violations block CI:

```bash
uv run lint --overwrite-baseline
```

This updates `lint.baseline` with the current violation set. Commit the updated baseline alongside your changes.

To regenerate the baseline after intentional rule changes:

```bash
uv run lint --overwrite-baseline --baseline lint.baseline
```

See [overlays.md](overlays.md) for re-baselining details and [troubleshooting.md](troubleshooting.md) for baseline regression scenarios.

## Further reading

- [Overlays guide](overlays.md) — per-tool config overrides
- [Custom checks guide](custom-checks.md) — writing custom pylint checkers
- [Semantic justification guide](semantic-justification.md) — suppression justification validation
- [Troubleshooting guide](troubleshooting.md) — common issues and fixes
