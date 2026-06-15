# python-setup

Shared linting, formatting, and dev-tooling infrastructure for Python projects.

## What it is

`python-setup` is a reusable Python package that encapsulates linting conventions,
custom checkers, and setup scripts used across multiple projects (starting with `consultant-mcp`).
It keeps tooling DRY — one source of truth for rules, checkers, and config.

## Install

```bash
# From a local checkout
uv add /path/to/python-setup

# Or direct from git (once hosted)
uv add git+https://github.com/<owner>/python-setup
```

## Usage

```bash
# Run the full lint pipeline
lint

# Install python-setup tooling into a target project
install
```

Both commands return exit code 0 on success, non-zero on failure.

## Update workflow

When lint rules or checkers change in `python-setup`:

1. Update the package: `uv add /path/to/python-setup`
2. Re-run `install` to propagate config updates to the consuming project:
   `install`
3. Commit the updated config in the consuming project.

## License

MIT