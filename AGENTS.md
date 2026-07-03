# AGENTS.md — python-setup agent context

This file is the entry point for all AI agents working on python-setup. Read this first, then follow links for details.

## Quick Commands

| Command | What it does |
|---------|-------------|
 | `uv run lint` | Full 13-tool lint pipeline (baseline diffing, ~80s typical, 120s/tool cap) |
| `uv run pytest -q` | Unit tests (1264 pass, 4 skip, 15 deselected, ~44s) |
| `uv run pytest tests/integration.py -v` | Integration tests (6 pass, ~32s) |
| `uv run lint --rebaseline` | Regenerate `lint.baseline` after intentional rule changes |
| `uv run python-setup install` | Install configs in consumer project |
| `uv run python-setup update` | Update configs + drift detection |
 
 ## Tool Scope
 
 | Tool | Scope |
 |------|-------|
 | ty check | `src/` only (oracle-reviewed exception, see [design/0002](design/0002-ty-src-only-exception.md)) |

## Key Files

| Path | Purpose |
|------|---------|
| `pyproject.toml` | Package metadata, deps, scripts, pytest config |
| `config/` | Shipped tool configs (ruff, pylint, mypy, pyright, rumdl, ty, yamllint, tach) |
| `CodingRules.md` | Python coding conventions (shipped to consumers) |
| `lint.baseline` | Frozen baseline of pre-existing violations |
| `src/python_setup_lint/runner/cli.py` | Main entry point (`main`, `run_lint`) |
| `src/python_setup_lint/runner/dispatch.py` | Tool strategy registry (13 built-in tools) |
| `src/python_setup_lint/checkers/_base.py` | Shared checker utilities |
| `tests/conftest.py` | Shared pytest fixtures |
| `tests/integration.py` | Fit-for-purpose integration test |
| `docs/custom-checks.md` | Writing custom pylint checkers |
| `docs/overlays.md` | Config overlay mechanism per tool |

## Architecture & Data Flow

See `docs/custom-checks.md` (checker writing, message defs, rule IDs, registration, testing, helpers, semantic pipeline) and `docs/overlays.md` (config overlay mechanism per tool).

### Runner pipeline

```
pyproject.toml → ToolSpec[] → dispatch.run() → per-tool subprocess → results → baseline diff → report
```

Each tool is a `ToolSpec` with name, command, args, config path, and parse strategy. The runner:

1. Loads `pyproject.toml` for extra tools and config overrides
2. Builds the tool list (13 built-in + any extras)
3. Runs each tool sequentially (some tools share resources)
4. Parses output per-tool (regex, JSON, lines)
5. Filters against `lint.baseline` (only new violations fail)
6. Aggregates statistics (files, violations, time per tool)

### Config overlay flow

```
config/<tool>.<ext>  ← shared (shipped)
       ↓
consumer pyproject.toml  ← overrides (extend / --config)
       ↓
runner composes final config at runtime
```

### Semantic justification pipeline

```
suppressed violation → _semantic.py → LLM reranker → score cached → reused on re-lint
```

The semantic checker (`W9704`) detects `Any` in function signatures, unjustified suppressions (`# type: ignore`, `# noqa`, `# pylint: disable`), standalone `Any` assignments, and `Any` in returns. Uses an optional LLM reranker to validate cached scores against the suppressed code context. The reranker is lazy-loaded and configurable via `PYTHON_SETUP_LINT_RERANKER_MODEL`.

## Testing Strategy

| Layer | Command | Scope |
|-------|---------|-------|
| Unit | `uv run pytest -q` | Individual checkers, runner logic, config parsing |
| Integration | `uv run pytest tests/integration.py -v` | End-to-end: install, lint, update on a sample project. Validates ALL 13 tools + custom checkers fire on planted violations; NOT marked slow; key fit-for-purpose gate. |
| Lint | `uv run lint` | Self-lint: all 13 tools on python-setup itself |

## Common Patterns

### Adding a new lint tool

1. Add config file to `config/`
2. Add `ToolSpec` to `dispatch.py`
3. Add config to `_BUNDLED_CONFIGS` in `setup.py` (if shipped to consumers)
4. Add test coverage in `tests/runner/`
5. Update `lint.baseline` via `--rebaseline`

### Modifying a checker

1. Edit the checker in `src/python_setup_lint/checkers/`
2. Update tests in `tests/checkers/`
3. Run `uv run pytest tests/checkers/ -q` to verify
4. Run `uv run lint` to self-lint

## See Also

- `CONTRIBUTING.md` — dev workflow, PR expectations
- `CodingRules.md` — Python coding conventions
- `docs/custom-checks.md` — checker writing guide
- `docs/overlays.md` — config overlay reference
- `docs/semantic-justification.md` — semantic justification system
