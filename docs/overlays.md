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

#### Pylint rcfile variants

The project ships three pylintrc files, each scoped to a different code category:

- **`.pylintrc`** — for source code under `src/`
- **`.pylintrc-pyi`** — for `.pyi` stub files
- **`.pylintrc-tests`** — for test files

Pylint rcfiles do not support inheritance, so the runner dispatches each file to the appropriate rcfile based on its path. The `--rcfile` flag is set per-file, not per-project.

### Mypy

The shared `config/mypy.ini` is extended by the consumer's `pyproject.toml`:

```toml
[tool.mypy]
config_file = "python_setup_lint/config/mypy.ini"
```

### Pyright

The shared `config/pyrightconfig.json` is copied to `cwd/.pyrightconfig-composed.json` at runtime so pyright resolves relative `venvPath`/`exclude` against the project root (see design/0001 for the cwd-vs-tmp asymmetry). Add `.pyrightconfig-composed.json` to your project's `.gitignore`. The runner merges the shared config with any `pyproject.toml` settings.

### Tool timeouts and memory limits

Each tool has a default timeout (120 seconds) and memory limit (2048 MB). These can be overridden per tool via ``tool_timeouts`` and ``tool_memory_limits`` in ``pyproject.toml``:

```toml
[tool.python-setup-lint]
tool_timeouts = { "pyright check" = 300, "mypy" = 180 }
tool_memory_limits = { "pyright check" = 4096 }
```

The overlay value wins over the :class:`ToolSpec` default. A value of ``0`` disables the limit entirely (use with caution).

### Other tools

Rumdl, ty, and yamllint follow the same pattern: shared config in ``config/``, consumer overrides via ``extend`` or ``--config`` flags. Tach auto-discovers ``tach.toml`` from the repo root — no ``--config`` flag is supported. The installer skips symlinking ``tach.toml`` if the consumer already has one (``_SKIP_SYMLINK_IF_EXISTS``), so the consumer's own module boundaries are preserved. (detect-secrets uses its own baseline file, not a shared config.)

## Custom checkers

See [docs/custom-checks.md](custom-checks.md) for writing custom pylint checkers that integrate with the python-setup runner.

## Re-baselining

To regenerate the baseline after intentional rule changes:

```bash
uv run lint --overwrite-baseline --baseline lint.baseline
```

This updates `lint.baseline` with the current violation set. Commit the updated baseline alongside config changes.
