# python-setup

Shared Python project setup — lint runner, config, checkers, and CI integration.

## Quick start

```bash
uv add python-setup
uv run python-setup install
uv run lint
```

## What is python-setup?

A reusable Python project template that ships:

- **13 lint tools** — tach, ruff, rumdl, mypy, yamllint, ty, mypy.stubtest, pyright (check + verify types), pylint, pylint-pyi, pylint tests, detect-secrets.
- **Shared config** — tool configs live in `python-setup/config/` and are inherited by consumer projects.
- **Custom pylint checkers** — automatically registered; no manual plugin loading.
- **Baseline diffing** — `lint.baseline` freezes pre-existing violations; CI only flags new ones.
- **Pre-commit hooks** — auto-fix on commit + full lint pipeline on the same `git commit` stage.
- **Config drift detection** — `python-setup update` warns when shared configs have changed upstream.

## Installation

```bash
uv add python-setup
uv run python-setup install
uv add "python-setup[semantic]"  # optional: enables sentence-transformer-powered justification scoring
```

See [Using python-setup in another project](#using-python-setup-in-another-project) for details.

## Using python-setup in another project

### 1. Add dependency

```bash
uv add python-setup
```

### 2. Run installer

```bash
uv run python-setup install
```

### 3. Configure tools

Override any shared config via `pyproject.toml` `[tool.*]` sections. See [docs/overlays.md](docs/overlays.md) for per-tool overlay reference.

### 4. Run lint

```bash
uv run lint
```

Runs all 13 lint tools sequentially with baseline diffing and statistics aggregation.

### What you get

- **Config files** in `python-setup/config/` (ruff, mypy, pylint, pyright, rumdl, ty, yamllint, tach) — inherited via `extend` in your `pyproject.toml`.
- **Custom pylint checkers** — automatically registered by the installer.
- **Extra lint tools** — declare project-specific tools via `[[tool.python-setup-lint.extra-tools]]` in your `pyproject.toml` (see [docs/custom-checks.md](docs/custom-checks.md)).
- **Pre-commit hooks** — fast auto-fix on commit AND the full lint pipeline on the same `git commit` stage.
- **Baseline diffing** — only new violations block CI; pre-existing ones are frozen in `lint.baseline`.

### Update workflow

When lint rules or checkers change in `python-setup`:

1. Update the dependency: `uv add "python-setup @ git+https://github.com/szavadsky/python-setup.git@v0.17.0"`
2. Re-run the installer: `uv run python-setup install`
3. Commit the updated config in the consuming project.

## Configuration

### Rule overlays

Consumer projects can overlay their own rules on the shared base config. See [docs/overlays.md](docs/overlays.md) for per-tool overlay reference.

### Custom lint steps

Declarative lint-step registration with zero Python code. Add a `[[tool.python-setup-lint.extra-tools]]` entry to your `pyproject.toml`. See [docs/custom-checks.md](docs/custom-checks.md) for the full field reference, parse strategies, and examples.

### Re-baselining

The lint pipeline uses a baseline file (`lint.baseline`) to distinguish new violations from pre-existing ones. See [docs/overlays.md](docs/overlays.md) for re-baselining commands and workflow.

### Semantic justification

See [docs/semantic-justification.md](docs/semantic-justification.md) for the semantic lint-justification system — how suppressed violations are tracked and validated with meaningful explanations.

## License

MIT
