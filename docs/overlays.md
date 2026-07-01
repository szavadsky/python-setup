# Rule Overlay Configuration

Consumer projects can overlay their own rules on the shared base config. Each tool has its own mechanism — this document covers all 13 shipped tools.

## Per-tool overlay reference

### Ruff

Ruff uses `extend` in `pyproject.toml`:

```toml
[tool.ruff]
extend = "python_setup_lint/config/ruff.toml"
```

### Pylint

Pylint uses `--rcfile` pointing to the shared config:

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

The shared `config/pyrightconfig.json` is copied to `cwd/.pyrightconfig-composed.json` at runtime so pyright resolves relative `venvPath`/`exclude` against the project root. Add `.pyrightconfig-composed.json` to your project's `.gitignore`. The runner merges the shared config with any `pyproject.toml` settings.

### Other tools

Rumdl, ty, yamllint, and tach all follow the same pattern: shared config in ``python-setup/config/``, consumer overrides via ``extend`` or ``--config`` flags. (detect-secrets uses its own baseline file, not a shared config.)

## Custom checkers

See [docs/custom-checks.md](custom-checks.md) for writing custom pylint checkers that integrate with the python-setup runner.

## Re-baselining

To regenerate the baseline after intentional rule changes:

```bash
uv run lint --rebaseline
```

This updates `lint.baseline` with the current violation set. Commit the updated baseline alongside config changes.
