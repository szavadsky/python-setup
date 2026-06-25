# Repository Guidelines

## Project Overview

`python-setup` is a reusable Python package that encapsulates shared linting, formatting, and dev-tooling infrastructure for Python projects. It provides a unified lint pipeline (11 tools), custom pylint checkers, baseline-diffing for drift-resistant CI, and an idempotent installer that configures pre-commit hooks, pylint plugins, and config files in consumer projects.

The package is consumed as a git dependency (e.g., `consultant-mcp`) and is **not** published to PyPI.

## Architecture & Data Flow

### High-level structure

```text
pyproject.toml  ──→  [project.scripts] lint → runner.cli:main
                     [project.scripts] install → setup:main
                     [project.scripts] python-setup-test-checked → testing:test_checked_main

src/python_setup_lint/
├── runner/              # Lint pipeline orchestration
│   ├── cli.py           # Entry point (main, run_lint), autofix logic
│   ├── dispatch.py      # Tool strategy registry (11 built-in tools)
│   ├── types.py         # Core data types (ToolSpec, LintResult, RunnerConfig, ViolationCount)
│   ├── cmd_build.py     # Command construction, path discovery, config composition
│   ├── baseline.py      # Baseline capture + diff (drift-resistant)
│   ├── parsers.py       # Output parsers (statistics + violation records)
│   ├── extra_tools.py   # Declarative extra-tools loader (pyproject.toml [[extra-tools]])
│   ├── output.py        # Statistics aggregation, subprocess runner, formatting
│   └── __main__.py      # python -m shim
├── checkers/            # Custom pylint plugins
│   ├── stub_checker.py           # Orchestrator: coverage + import contract + fidelity
│   ├── stub_coverage.py          # Phase 1: every .py needs a .pyi
│   ├── stub_import_contract.py   # Phase 2: imports must reference declared stub symbols
│   ├── stub_fidelity/            # Phase 3: stub-impl annotation/signature/kind matching
│   │   ├── orchestrator.py       # Top-level dispatcher
│   │   ├── kind.py               # Symbol presence + kind mismatch
│   │   ├── annotation.py         # Variable + class annotation fidelity
│   │   ├── signature.py          # Callable signature + param/return comparison
│   │   ├── _ast_helpers.py       # Shared state types
│   ├── stub_normalizer.py        # Two-phase annotation normalizer (infer + AST walk)
│   ├── stub_docstring_checker.py # Docstring-in-.pyi verification
│   ├── beartype_checker.py       # @beartype coverage inventory
│   ├── asyncio_timeout_checker.py # Require asyncio.timeout() wrapping
│   ├── no_try_import_checker.py  # Ban try/except ImportError
│   └── tmp_path_checker.py       # Ban tempfile.* in tests
├── setup.py              # Idempotent install/update CLI
├── _setup_precommit.py   # Pre-commit template + AGENTS.md snippet
├── testing.py            # Shared test infrastructure + consumer-agnostic health checks
└── py.typed              # PEP 561 marker
```

### Data flow

1. **`uv run lint`** → `runner/cli.py:main()` parses args → `run_lint()` iterates over 11 built-in tools + any extras from `pyproject.toml [[tool.python-setup-lint.extra-tools]]`.
2. Each tool is a `ToolSpec` (name, command, flags) wrapped in a `LintTool` strategy that builds the CLI command via `cmd_build.py:_build_command()`.
3. Commands run via `output.py:_run_cmd()` → `LintResult` (exit_code, stdout, stderr, elapsed).
4. Results are optionally diffed against `lint.baseline` via `baseline.py:_diff_baseline()` — only new violations (regressions) fail.
5. `--statistics` aggregates per-rule counts via `parsers.py` dispatch table.
6. `--fix` mode runs autofix with conflict-tolerant skip + E999 parseability canary revert.

### Custom pylint checker lifecycle

1. `setup.py` discovers checkers via `_discover_checkers()` (introspects `python_setup_lint.checkers`).
2. Each checker module exports `register(linter)` → `linter.register_checker(CheckerClass(linter))`.
3. Checkers extend `pylint.checkers.BaseChecker` with `visit_*` AST visitors and `open()`/`close()` lifecycle hooks.
4. `StubChecker` is the orchestrator: `open()` → `visit_module/visit_import/visit_importfrom` → `close()` delegates to `emit_coverage_violations`, `emit_import_contract_violations`, `emit_fidelity_violations`.

## Key Directories

| Path | Purpose |
|------|---------|
| `src/python_setup_lint/` | Package root |
| `src/python_setup_lint/runner/` | Lint pipeline orchestration, CLI, baseline, parsers |
| `src/python_setup_lint/checkers/` | Custom pylint plugins (8 checkers) |
| `src/python_setup_lint/checkers/stub_fidelity/` | Stub-impl fidelity sub-package (5 modules) |
| `config/` | Shipped tool configs (ruff, pylint, mypy, pyright, rumdl, ty, yamllint) |
| `tests/` | Test suite |
| `tests/runner/` | Runner tests (pipeline, baseline, autofix, extras, setup) |
| `tests/checkers/` | Checker unit tests |
| `tests/fixtures/` | Test fixtures (dogfood-extra pyproject) |
| `integration/` | Integration docs/benchmarks |
| `reports/` | Analysis reports |

## Development Commands

```bash
# Run the full lint pipeline (all 11 tools)
uv run lint

# Run lint with path scoping
uv run lint --path src/python_setup_lint

# Run lint with autofix
uv run lint --fix

# Run lint with baseline diffing
uv run lint --baseline lint.baseline

# Run lint without fail-fast (report all, exit non-zero on any failure)
uv run lint --no-fail-fast

# Run lint with statistics
uv run lint --statistics

# Run lint with machine-readable statistics
uv run lint --statistics --format json

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=python_setup_lint

# Run a specific test file
uv run pytest tests/runner/test_lint_runner.py

# Run tests matching a marker
uv run pytest -m "not slow"

# Install python-setup into a consumer project
uv run python-setup install

# Update python-setup in a consumer project
uv run python-setup update

# Run pytest with typeguard enabled (consumer-agnostic health check)
uv run python-setup-test-checked
```

## Code Conventions & Common Patterns

### Formatting & Linting

- **Line length**: 130 (ruff config `line-length = 130`)
- **Quote style**: double quotes (ruff format `quote-style = "double"`)
- **Target**: Python 3.14+ (`target-version = "py314"`)
- **Ruff rules**: E, F, I, B, UP, SIM, TID + extended sets (N, W, C4, A, RET, PIE, FLY, PERF, PYI, selected PL, PT, S, ARG, ANN, TCH)
- **Pylint**: Custom checkers loaded via `load-plugins` in `.pylintrc`; complexity limits: 65 statements, 16 branches, 20 locals, 8 nested blocks, 30 public methods, 15 attributes
- **Mypy**: `strict = true` (excludes `tests/data/`)
- **Pyright**: Shipped config with most type-check reports set to `"none"` (used for `verifytypes` only)
- **Rumdl**: Markdown linting (enabled: MD012, MD022, MD031, MD032, MD034, MD047, MD009)
- **Ty**: Type checker with `unresolved-attribute`, `not-iterable`, `call-non-callable` ignored
- **Yamllint**: YAML linting
- **detect-secrets**: Secret scanning
- **tach**: Module dependency enforcement (source roots: `src`)

### Naming

- `_` prefix: file-private, imported only by tests
- No prefix: file surface (re-exported in `__init__.py`) or intra-module helper
- Test files: `test_<module>.py`
- Test functions: `test_<method>_given_<condition>_then_<expected>`
- Pylint checker names: kebab-case (e.g., `"stub-checker"`, `"asyncio-timeout"`)
- Pylint message codes: `W9xxx` (warning), `E9xxx` (error), `I9xxx` (info)

### Error handling

- External inputs validated at process boundary; trusted downstream
- Public API: types specify acceptable inputs; `@beartype` enforces `Annotated` predicates at runtime
- Helpers assume caller guarantees; document assumptions inline
- IPC/API failures: handled or propagated; `raise X from Y` for chain errors
- Expected control flow: prefer return types encoding failure (`Result`, `Optional`, union) over exceptions
- Every caught error path: `structlog` error with structured fields

### Async patterns

- Process-boundary-crossing calls (network, IPC, external APIs): async
- Structured concurrency (`TaskGroup`) over raw `asyncio.gather`
- Timeouts via `asyncio.timeout()` covering full operations
- `asyncio.Semaphore` for concurrency limits
- Graceful shutdown: signal handlers, drain-in-flight, close connection pools

### Dependency injection

- No DI framework. Dependencies are passed explicitly as function parameters or constructor args.
- Tests use `FakeRunCmd` (from `testing.py`) to replace `_run_cmd` in runner tests.
- `isolated_runner_registries` fixture snapshots/restores `LINT_TOOLS`/`STRATEGIES` around tests that mutate them.

### State management

- Checker state lives in dataclass fields on the checker instance (e.g., `StubChecker._coverage`, `StubChecker._fidelity`).
- Module-level caches for parsed pyproject.toml (`_PYPROJECT_CACHE` in `cmd_build.py`, `_EXTRA_TOOLS_CACHE` in `extra_tools.py`) keyed by `(path, mtime_ns)`.
- `_FALLBACK_TOOLS` set in `baseline.py` tracks which tools fell back to legacy rstrip-set comparison.

### .pyi stub conventions

- Every production `.py` needs a `.pyi` companion (enforced by `stub_checker`).
- `.pyi` exposes only public members (no `_`-prefix symbols).
- `.py` keeps implementation comments only; usage docstrings go in `.pyi`.
- `__init__.py` re-exports use `from .mod import name as name` idiom (PEP 484 explicit re-export).
- No `.pyi` for: `__init__.py` (unless `__getattr__` or logic present), test bodies, standalone scripts, `conftest.py`, trivial test data.

### Module layout

```text
mypackage/
├── __init__.py   # public API, __all__, module-level docs. No .pyi.
├── py.typed      # PEP 561 (empty, required)
├── feature.py    # implementation
├── feature.pyi   # public contract only
├── _helper.py    # file-private helper
└── _helper.pyi   # public contract only
```

## Important Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Package metadata, dependencies, scripts, pytest config |
| `config/ruff.toml` | Ruff lint/format rules (shipped to consumers) |
| `config/.pylintrc` | Pylint config with custom checker load-plugins |
| `config/pyrightconfig.json` | Pyright config (verifytypes only) |
| `config/mypy.ini` | Mypy strict config |
| `config/rumdl.toml` | Markdown lint rules |
| `config/ty.toml` | Ty type checker config |
| `config/.yamllint` | YAML lint config |
| `CodingRules.md` | Python coding conventions (shipped to consumers) |
| `lint.baseline` | Frozen baseline of pre-existing violations |
| `tach.toml` | Module dependency boundaries |
| `.secrets.baseline` | detect-secrets baseline |
| `src/python_setup_lint/runner/cli.py` | Main entry point (`main`, `run_lint`) |
| `src/python_setup_lint/runner/dispatch.py` | Tool strategy registry (11 built-in tools) |
| `src/python_setup_lint/runner/types.py` | Core data types |
| `src/python_setup_lint/runner/baseline.py` | Baseline capture + diff |
| `src/python_setup_lint/runner/parsers.py` | Output parsers |
| `src/python_setup_lint/runner/extra_tools.py` | Declarative extra-tools loader |
| `src/python_setup_lint/runner/cmd_build.py` | Command construction, config composition |
| `src/python_setup_lint/runner/output.py` | Statistics aggregation, subprocess runner |
| `src/python_setup_lint/setup.py` | Idempotent install/update CLI |
| `src/python_setup_lint/testing.py` | Shared test infrastructure |
| `src/python_setup_lint/checkers/stub_checker.py` | Stub checker orchestrator |
| `src/python_setup_lint/checkers/stub_coverage.py` | Phase 1: module coverage |
| `src/python_setup_lint/checkers/stub_import_contract.py` | Phase 2: import contract |
| `src/python_setup_lint/checkers/stub_fidelity/orchestrator.py` | Phase 3: stub-impl fidelity dispatcher |
| `src/python_setup_lint/checkers/stub_normalizer.py` | Two-phase annotation normalizer |
| `tests/conftest.py` | Shared pytest fixtures |

## Runtime/Tooling Preferences

- **Runtime**: Python 3.14+ (requires `>=3.14`)
- **Package manager**: `uv` (all commands use `uv run ...`)
- **Build system**: Hatchling (`hatchling.build`)
- **Type checkers**: mypy (strict), pyright (verifytypes), ty (concise)
- **Linters**: ruff, pylint (with custom plugins), rumdl, yamllint, detect-secrets, tach
- **Formatter**: ruff format
- **Test framework**: pytest 9.1+ with `pytest-asyncio` (`asyncio_mode = "auto"`)
- **Runtime type checking**: beartype (optional dev dependency, not a runtime dep of python-setup itself)
- **Pre-commit**: ruff-format, ruff-check, and full lint pipeline on `git commit`

## Testing & QA

### Test framework

- **pytest** with `pytest-asyncio` (`asyncio_mode = "auto"` in pyproject.toml)
- **pytest-cov** for coverage
- **typeguard** for runtime type checking in tests (`uv run python-setup-test-checked`)

### Test structure

- `tests/runner/` — runner tests (pipeline, baseline, autofix, extras, setup, health checks, coverage)
- `tests/checkers/` — checker unit tests (one file per checker)
- `tests/conftest.py` — shared fixtures: `tmp_baseline`, `runner_config_factory`, `isolated_runner_registries`, `empty_project`, `configured_project`
- `tests/runner/_factories.py` — pure factory functions for parametrized tests

### Test patterns

- **Mocking**: Mock only at true external boundaries (subprocess calls). Never mock first-party code.
  - `FakeRunCmd` (from `testing.py`) replaces `_run_cmd` in runner tests.
  - `isolated_runner_registries` fixture for tests that mutate `LINT_TOOLS`/`STRATEGIES`.
- **Parametrize**: `@pytest.mark.parametrize` for discrete input-variant tests.
- **Fixtures**: Shared fixtures in `conftest.py` only; never put shared fixtures in test files.
- **Async**: `pytest-asyncio` with `asyncio_mode = "auto"`.
- **Markers**: `@pytest.mark.slow` for intentionally slow tests (benchmarks or full pipeline runs); use `-m "not slow"` to exclude.

### Coverage expectations

- Near 100% for each layer + downstream (transitive).
- Each layer tested independently.
- Hard-to-inject failure paths and defensive behaviors annotated.
- `--statistics` aggregation tested across all 11 tool parsers.

### Baseline management

- `lint.baseline` freezes pre-existing violations; only new violations (regressions) fail CI.
- Shrinkage (fixing violations) auto-records silently — no human diff review needed.
- `--overwrite-baseline` is reserved for coordinated cleanup milestones only (documented in `decisions.md`).
- `decisions.md` records consciously baselined findings that cannot be fixed without redesign.
