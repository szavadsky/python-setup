# Rule Overlay Configuration

`python-setup` ships with shared config files for all 11 lint tools. Consumer projects
can overlay their own rules on top of the shared base via `extend` in their
`pyproject.toml`.

## How overlays work

The installer copies config files from `python-setup/config/` into the consumer project.
Each config file uses the tool's native `extends`/`inherit` mechanism so the consumer
can add project-specific rules without forking the shared config.

## Per-tool overlay reference

### Ruff

The shared `config/ruff.toml` is extended by the consumer's `pyproject.toml`:

```toml
[tool.ruff]
extend = "python_setup_lint/config/ruff.toml"

# Project-specific rules
[tool.ruff.lint]
select = ["I", "N", "D"]
```

### Pylint

The shared `.pylintrc` is loaded via `--rcfile`. The installer registers custom checkers
in `[tool.pylint.main] load-plugins`. Consumers add project-specific overrides in their
own `.pylintrc` or `pyproject.toml`:

```toml
[tool.pylint.main]
load-plugins = ["python_setup_lint.checkers"]
```

### Mypy

The shared `config/mypy.ini` is extended by the consumer's `pyproject.toml`:

```toml
[tool.mypy]
config_file = "python_setup_lint/config/mypy.ini"
```

### Pyright

The shared `config/pyrightconfig.json` is composed with project-specific settings
at runtime. The runner merges the shared config with any `pyproject.toml` settings.

### Other tools

Rumdl, ty, yamllint, and detect-secrets all follow the same pattern: shared config
in `python-setup/config/`, consumer overrides via `extend` or `--config` flags.

## Custom checkers

See [docs/custom-checks.md](custom-checks.md) for writing custom pylint checkers
that integrate with the python-setup runner.
