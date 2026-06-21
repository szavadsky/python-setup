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

# Or from the published git repository
uv add "python-setup @ git+https://github.com/szavadsky/python-setup.git@v0.5.0"
```

After adding the dependency, run the setup command to install pre-commit hooks,
copy config files, and register pylint plugins:

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
uv add --dev "python-setup @ git+https://github.com/szavadsky/python-setup.git@v0.5.0"
```

### 2. Run the installer

```bash
uv run python-setup install
```

The installer does the following (all idempotent):

| Step | What it does |
|------|-------------|
| Dependency | Adds `python-setup` to `[dependency-groups] dev` if missing |
| Pylint plugins | Discovers custom checkers and adds them to `[tool.pylint.main] load-plugins` |
| Pre-commit config | Writes `.pre-commit-config.yaml` with ruff-format, ruff-fix, and a local lint hook |
| Coding rules | Copies `CodingRules.md` to the project root |
| AGENTS.md snippet | Appends pre-commit setup instructions to `AGENTS.md` (if it exists) |

### 3. Install pre-commit hooks

```bash
uv run pre-commit install
```

This installs the git hooks defined in `.pre-commit-config.yaml`:
- **`git commit`** triggers `ruff-format` and `ruff-fix` (fast, auto-apply).
- **`git push`** triggers the full lint pipeline with baseline diffing.

### 4. Run lint

```bash
uv run lint
```

Runs all 11 lint tools sequentially with baseline diffing, statistics aggregation,
and fail-fast / fail-fast-free modes. See [Re-baselining](#re-baselining) for how
to manage the baseline file.

### What you get

- **Config files** in `python-setup/config/` (ruff, mypy, pylint, pyright, rumdl, ty) — inherited via `extend` in your `pyproject.toml`.
- **Custom pylint checkers** — e.g. the `asyncio-timeout-checker` (T37) that flags `await client.{get,post,...}` calls missing an enclosing `asyncio.timeout(...)` / `anyio.fail_after(...)`. These are automatically registered by the installer.
- **Extra lint tools** — declare project-specific tools via `[[tool.python-setup-lint.extra-tools]]` in your `pyproject.toml` (see [Custom lint steps via pyproject.toml](#custom-lint-steps-via-pyprojecttoml)).
- **Pre-commit hooks** — fast auto-fix on commit, full pipeline on push.
- **Baseline diffing** — only new violations block CI; pre-existing ones are frozen in `lint.baseline`.

### Worked example

The `consultant-mcp` project uses python-setup v0.2.0. Its `AGENTS.md` documents
the full setup — see the `<!-- python-setup:pre-commit -->` section for the
canonical pre-commit + baseline workflow.

### Update workflow

When lint rules or checkers change in `python-setup`:

1. Update the dependency: `uv add "python-setup @ git+https://github.com/szavadsky/python-setup.git@v0.5.0"`
2. Re-run the installer: `uv run python-setup install`
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

## Re-baselining

The lint pipeline uses a baseline file (`lint.baseline`) to distinguish new
violations from pre-existing ones. The runner's `_diff_baseline` compares
current output against the saved baseline — any delta (addition OR removal)
flags a regression.

### Shrinkage auto-records silently

When you delete files, fix violations, or remove duplicates, the baseline
signature shrinks. The runner detects this delta but does **not** block the
change — shrinkage auto-records silently via the `_diff_baseline` mechanism
(T0). No human diff review is needed for shrinkage; the next `--baseline`
invocation accepts the smaller signature.

### `--overwrite-baseline` for milestone-justified additions

The `--overwrite-baseline` flag is reserved for coordinated cleanup milestones
where the baseline must advance past legitimate additions (e.g. surfacing
previously-masked debt after shrinking a broad per-file-ignore). It is **never**
used for routine per-violation suppression (anti-pattern "Broad pre-existing
exclusions").

Exact command:

```bash
uv run lint --no-fail-fast --overwrite-baseline --baseline lint.baseline
```

Permitted milestones (from ANALYSIS-1 §4):

| Milestone | Trigger | Justification |
|-----------|---------|---------------|
| **R-M6** | Installed-path metadata shift after dep switch | T16: consultant dep `path=` → `git+https` tag |
| **R-M7** | Surfaced debt from broad-ignore shrink | T17: portable per-file-ignores moved to python-setup |
| **R-M11** | Final integration lock | T32: absorbing all deferred M8+M9 shrinkage + fix resolutions |

After **R-M11**, no further `--overwrite-baseline` is permitted without a new
ANALYSIS-`<n>` milestone authorising it.

### Statistics aggregation caveat (T38)

The `--statistics` flag aggregates violation counts across all tools. As of
v0.5.0, the parsers correctly handle all output shapes — including pylint's
`{"messages": [...]}` dict format, pyright's `generalDiagnostics`, and rumdl
per-violation output. The runner also passes `--rcfile config/.pylintrc` to
pylint, so the project's pylint configuration is respected during baseline
capture.

## License

MIT