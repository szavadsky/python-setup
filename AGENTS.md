# Agent Index

## Project

`python-setup` is a reusable Python package that encapsulates shared linting, formatting, and dev-tooling infrastructure for Python projects. It provides a unified lint pipeline (13 tools), custom pylint checkers, baseline-diffing for drift-resistant CI, and an idempotent installer that configures pre-commit hooks, pylint plugins, and config files in consumer projects.

Consumed as a git dependency (e.g., `consultant-mcp`), **not** published to PyPI.

## Quick Commands

| Command | What it does |
|---------|-------------|
| `uv run lint` | Full lint pipeline (all 13 tools) |
| `uv run pytest` | Run test suite |
| `uv run python-setup install` | Install into consumer project |
| `uv run python-setup update` | Update consumer project |
| `uv run python-setup-test-checked` | Run pytest with typeguard |

## Key Files

| Path | Purpose |
|------|---------|
| `pyproject.toml` | Package metadata, deps, scripts, pytest config |
| `config/` | Shipped tool configs (ruff, pylint, mypy, pyright, rumdl, ty, yamllint) |
| `CodingRules.md` | Python coding conventions (shipped to consumers) |
| `lint.baseline` | Frozen baseline of pre-existing violations |
| `tach.toml` | Module dependency boundaries |
| `src/python_setup_lint/runner/cli.py` | Main entry point (`main`, `run_lint`) |
| `src/python_setup_lint/runner/dispatch.py` | Tool strategy registry (13 built-in tools) |
| `src/python_setup_lint/checkers/_base.py` | Shared checker utilities |
| `tests/conftest.py` | Shared pytest fixtures |
| `tests/integration.py` | Fit-for-purpose integration test |
| `docs/custom-checks.md` | Writing custom pylint checkers |
| `docs/overlays.md` | Config overlay mechanism per tool |

## Architecture & Data Flow

See `docs/custom-checks.md` (checker writing, message defs, rule IDs, registration, testing, helpers, semantic pipeline) and `docs/overlays.md` (config overlay mechanism per tool).

## Code Conventions

See `CodingRules.md` — typing, module layout, .pyi rules, docstrings, error handling, async patterns, complexity rules, logging.

## Runtime / Tooling

Python 3.14+, `uv` package manager, Hatchling build. Type checkers: mypy (strict), pyright (verifytypes), ty. Linters: ruff, pylint (custom plugins), rumdl, yamllint, detect-secrets, tach. Formatter: ruff format. Test: pytest 9.1+ with pytest-asyncio. Runtime type checking: beartype. Pre-commit: ruff-format, ruff-check, full lint pipeline.

## Testing & QA

Integration test (`tests/integration.py`) is the fit-for-purpose gate — runs all 13 tools on planted-violation sample project, NOT marked slow. Verifies: all planted violations detected, brush-off "pre-existing" → W9704, carry-from external library → passes, install→lint E2E, pre-commit dry-run. Key regression catcher.

See `tests/` for full test suite structure, `pyproject.toml` for pytest config.
