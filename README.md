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

## Custom lint steps via pyproject.toml

Declarative lint-step registration with zero Python code. Add a
`[[tool.python-setup-lint.extra-tools]]` array-of-tables entry to your
project's `pyproject.toml`, and the loader registers your extra at
`run_lint` startup — no subclassing, no import hook, no plugin system.

### v1 field table

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | `str` | yes | — | Unique tool name across extras and built-ins |
| `command` | `list[str]` | yes | — | Base argument vector (no shell wrapper) |
| `supports_fix` | `bool` | no | `false` | Tool accepts `--fix` flag |
| `supports_path` | `bool` | no | `false` | Tool accepts path arguments |
| `supports_exclude` | `bool` | no | `false` | Tool accepts `--exclude` flag |
| `default_paths` | `list[str]` | no | `[]` | Globs/dirs passed when no explicit paths given |
| `config_flag` | `str \| list[str]` | no | — | Flag inserted before config path from `--config` |
| `parse_strategy` | `enum` | no | `"none"` | Parser for `--statistics` aggregation (see table below) |
| `parse_regex` | `str` | iff `parse_strategy == "regex_count"` | — | Regex with exactly **one** capture group |

### `parse_strategy` enum

| Value | Parser | Description |
|-------|--------|-------------|
| `none` | skip | Omitted from `--statistics` aggregation |
| `ruff_statistics` | built-in | Reuses `ruff` statistics parser |
| `rumdl_statistics` | built-in | Reuses `rumdl` statistics parser |
| `pylint_json2` | built-in | Reuses `pylint` JSON2 parser |
| `pyright_outputjson` | built-in | Reuses `pyright` output parser |
| `pyright_verify_types` | built-in | Reuses `pyright --verifytypes` parser |
| `mypy_stderr` | built-in | Reuses `mypy` stderr parser |
| `ty_concise` | built-in | Reuses `ty` concise parser |
| `tach_json` | built-in | Reuses `tach` JSON parser |
| `yamllint_parsable` | built-in | Reuses `yamllint` parsable parser |
| `stubtest_stderr` | built-in | Reuses `stubtest` parser |
| `detect_secrets_json` | built-in | Reuses `detect-secrets` parser |
| `regex_count` | generic | Count distinct values of the one capture group in `parse_regex` |
| `raw_lines` | generic | Count non-empty `stdout` lines as a single synthetic rule `"line"` |

The two generic parsers (`regex_count`, `raw_lines`) cover arbitrary CLI
output shapes without Python code. The 11 built-in reuses mean
consumer-declared tools sharing an output format with a built-in need
no custom parsing logic.

### Example

The dogfood `grep-noqa-scan` extra — counts `# noqa:` codes in the
source tree. A working copy lives at
`tests/fixtures/dogfood-extra/pyproject.toml`.

```toml
[[tool.python-setup-lint.extra-tools]]
name = "grep-noqa-scan"
command = ["grep", "-rnE", "--exclude-dir=__pycache__", "--include=*.py", "noqa: "]
supports_path = true
default_paths = ["src/", "tests/"]
parse_strategy = "regex_count"
parse_regex = '^[^:]+:\d+:.*# noqa: (\S+)'
```

### Failure contract

A malformed entry raises `ExtraToolsConfigError` (a typed exception
distinct from raw TOML-parse failures — NOT `SystemExit`). The error
carries `location` (the pyproject path) and `reason` (a stable one-line
identifier). `run_lint` does not catch it; the exception propagates
uncaught → traceback + non-zero exit. Failure shapes:

- Missing required field (`name`, `command`)
- Wrong type (e.g. `command` not a list of strings)
- Empty / whitespace-only `name`
- Duplicate `name` within the same file
- Duplicate `name` colliding with a built-in tool
- Unrecognised `parse_strategy` value
- `parse_regex` missing or not exactly 1 capture group when strategy is
  `regex_count`
- Unknown field (not in the v1 allowed set)
- Unreadable pyproject (TOML decode error)

### What's not in v1

Deferred to a later build, gated by real consumer demand (not a v2
regression — v1 covers the declarative-TOML-configured-lint-step user
story end-to-end). The six deferred candidates (T8 R7):

- Custom `fix_flag` — extras rely on the strategy's own default;
  explicit override flag is a power-user future.
- Custom `statistics_flag` — extras rely on the strategy's own default;
  explicit override flag is a power-user future.
- `path_expansion_strategy` enum (`"dir" | "expanded_glob_files" |
  "explicit_list"`) — extras use glob expansion via `default_paths`;
  pylint-style file-list expansion is deferred.
- Per-tool environment variable overrides.
- `requires_package` gating — skip an extra when a runtime package is
  absent.
- Pluggy-style entry-point hook for scripted parsing (power-user escape
  hatch; the declarative enum covers all current use cases).

## License

MIT