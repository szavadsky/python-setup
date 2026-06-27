# python-setup

Shared linting, formatting, and dev-tooling infrastructure for Python projects.

## What it is

`python-setup` is a reusable Python package that encapsulates linting conventions,
custom checkers, and setup scripts used across multiple projects. It keeps tooling
DRY — one source of truth for rules, checkers, and config.

## Install

```bash
# From a local checkout
uv add /path/to/python-setup

# Or from the published git repository
uv add "python-setup @ git+https://github.com/szavadsky/python-setup.git@v0.8.0"
```

After adding the dependency, run the setup command:

```bash
uv run python-setup install
```

This is idempotent — running it twice is a no-op.

## Usage

```bash
# Run the full lint pipeline (all 11 tools with baseline diffing)
uv run lint

# Install python-setup tooling into a target project
uv run python-setup install
```

Both commands return exit code 0 on success, non-zero on failure.

## Using python-setup in another project

### 1. Add the dependency

```bash
uv add --dev "python-setup @ git+https://github.com/szavadsky/python-setup.git@v0.7.0"
```

### 2. Run the installer

```bash
uv run python-setup install
```

The installer adds the dependency, registers pylint plugins, writes pre-commit
config, copies `CodingRules.md`, and appends setup instructions to `AGENTS.md`.

### 3. Install pre-commit hooks

```bash
uv run pre-commit install
```

### 4. Run lint

```bash
uv run lint
```

Runs all 12 lint tools sequentially with baseline diffing, statistics aggregation,
and fail-fast / fail-fast-free modes.

### What you get

- **Config files** in `python-setup/config/` (ruff, mypy, pylint, pyright, rumdl, ty) — inherited via `extend` in your `pyproject.toml`.
- **Custom pylint checkers** — automatically registered by the installer.
- **Extra lint tools** — declare project-specific tools via `[[tool.python-setup-lint.extra-tools]]` in your `pyproject.toml` (see [docs/custom-checks.md](docs/custom-checks.md)).
- **Pre-commit hooks** — fast auto-fix on commit AND the full lint pipeline on the same `git commit` stage.
- **Baseline diffing** — only new violations block CI; pre-existing ones are frozen in `lint.baseline`.

### Update workflow

When lint rules or checkers change in `python-setup`:

1. Update the dependency: `uv add "python-setup @ git+https://github.com/szavadsky/python-setup.git@v0.9.0"`
2. Re-run the installer: `uv run python-setup install`
3. Commit the updated config in the consuming project.

## Configuration

### Rule overlays

Consumer projects can overlay their own rules on the shared base config.
See [docs/overlays.md](docs/overlays.md) for per-tool overlay reference.

### Custom lint steps

Declarative lint-step registration with zero Python code. Add a
`[[tool.python-setup-lint.extra-tools]]` entry to your `pyproject.toml`.
See [docs/custom-checks.md](docs/custom-checks.md) for the full field reference,
parse strategies, and examples.

### Re-baselining

The lint pipeline uses a baseline file (`lint.baseline`) to distinguish new
violations from pre-existing ones. See [docs/overlays.md](docs/overlays.md) for
re-baselining commands and workflow.

### Semantic justification

See [docs/semantic-justification.md](docs/semantic-justification.md) for the
semantic lint-justification system — how suppressed violations are tracked and
validated with meaningful explanations.

## License

MIT
