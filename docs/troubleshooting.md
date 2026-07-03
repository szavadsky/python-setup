# Troubleshooting

## Tool not found

`uv run <tool>` fails with "unknown command" or "not found":

```bash
# Install dev dependencies (includes all lint tools)
uv sync --group dev
```

The project's `pyproject.toml` declares lint tools under `[dependency-groups.dev]`. Without `uv sync --group dev` (or `uv sync --dev`), tools like `pylint`, `mypy`, `pyright`, `ruff`, `rumdl`, `ty`, `yamllint`, `tach`, and `detect-secrets` are not on `PATH`.

See [README.md](../README.md#quick-start) for the full install workflow.

---

## Config not applied standalone vs runner

Running a tool directly (`uv run pylint src/`) may produce different results than `uv run lint`:

1. **Check root symlinks** — the installer creates symlinks in the project root so standalone tools discover the shipped config:

   ```bash
   ls -la .pylintrc .yamllint
   # Expected: .pylintrc -> config/.pylintrc
   #           .yamllint -> config/.yamllint
   ```

   Missing symlinks? Re-run the installer:

   ```bash
   uv run python-setup install
   ```

2. **Use `--config-status`** — the lint runner prints per-tool config origin:

   ```bash
   uv run lint --config-status
   ```

   Output shows each tool's resolved config path and whether it's the shipped config, a project-local override, or auto-discovered. Useful for diagnosing why a tool behaves differently under the runner vs standalone.

See [docs/overlays.md](overlays.md) for per-tool overlay reference.

---

## Baseline regression blocks commit

A pre-commit hook or CI run fails with "new violations found" — but you intentionally changed the code:

```bash
# Accept current violation state as the new baseline
python-setup lint --overwrite-baseline --baseline lint.baseline
```

Commit the updated `lint.baseline` alongside your changes. The `--overwrite-baseline` flag replaces the existing baseline file with the current violation set, so only future regressions are flagged.

**When to re-baseline:**

- Adding a new lint tool or rule that fires on existing code
- Refactoring that legitimately changes violation counts
- Upgrading a tool version with new checks

**When NOT to re-baseline:**

- You introduced a real regression — fix the code instead
- The baseline file is missing or corrupted — re-run `uv run lint --rebaseline`

See [AGENTS.md](../AGENTS.md#pre-commit-hooks) for the pre-commit hook workflow.

---

## Sentence-transformer download failure -> heuristic fallback

The semantic justification checker downloads a cross-encoder model on first use. If the download fails (network, OOM, disk space), the pipeline falls back to the heuristic check — no crash, no error, just less accurate justification scoring.

To disable the semantic pipeline entirely (no import, no download attempt):

```bash
PYTHON_SETUP_LINT_SEMANTIC=0 uv run lint
```

Set the env var in CI or shell profile to avoid repeated download attempts in environments without internet access.

**Cached models** live in `~/.cache/python-setup/semantic/`. Delete this directory to force a fresh download.

See [docs/semantic-justification.md](semantic-justification.md) for the full pipeline description and opt-in mechanism.

---

## Pylint crash visibility

A pylint crash (segfault, signal, unhandled exception) produces a `[CRASH]` marker in the runner output:

```
[pylint] FAILED (exit=-6) [CRASH]
```

The runner detects crashes via:

- **Negative exit codes** (signals): `exit=-6` = SIGABRT, `exit=-11` = SIGSEGV
- **`__CRASH__` records**: crash violations are never baseline-absorbable — they always appear in the diff output
- **Pylint's F0002**: fatal error code emitted by pylint itself for internal failures

Crash records are formatted as:

```
[pylint] CRASH (exit=-6)
```

**Triage steps:**

1. Run pylint standalone to isolate: `uv run pylint --rcfile config/.pylintrc src/`
2. Check for plugin conflicts — disable custom checkers one by one
3. File an issue with the full crash output and `uv run pylint --version`

---

## Integration test as fit-for-purpose gate

The integration test suite (`tests/integration.py`) validates the full lint pipeline end-to-end on a planted-violation sample project. It is **not marked slow** — all tests are network-free, using programmatic `run_lint`/`install` calls (not subprocess), mocking `uv` calls, and skipping pre-commit if the binary is unavailable.

```bash
# Run integration tests
uv run pytest tests/integration.py -v
# Expected: 6 pass, ~39s
```

**What it covers:**

- All 13 lint tools fire on planted violations
- Config overlays work
- Setup is idempotent
- Pre-commit hooks validate

**When to run it:**

- After adding a new lint tool
- After modifying the runner or config resolution
- After changing the installer
- Before committing changes to the lint pipeline

See [AGENTS.md](../AGENTS.md) for the full test matrix (unit, integration, lint self-check).

---

## See Also

- [Tutorials](tutorials.md) — quick start, first lint pass, baseline workflow
- [Custom checks](custom-checks.md) — writing custom pylint checkers
- [Overlays](overlays.md) — per-tool config overlay reference
- [Semantic justification](semantic-justification.md) — semantic lint-justification system
- [AGENTS.md](../AGENTS.md) — agent context, test matrix, common patterns
