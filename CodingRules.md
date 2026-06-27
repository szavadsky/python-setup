# Python Coding Rules

## Platform

- Python 3.14+

## Typing

- First-party code: fully typed. `Any` only with documented technical justification.
- Types from defining module; define only at origin. Untyped only at untyped third-party boundaries.
- Types > names > docstrings.
- Use: `Literal`, `Enum`, `TypedDict`, `Protocol`, `NewType`, `TypeVar`,
  `TypeAlias`, `Final`, `Annotated` + `annotated-types` predicates (`Gt`, `Lt`,
  `MinLen`…), `Unpack`, `assert_never`, `Self` (fluent APIs, classmethod
  constructors), `ParamSpec`, `Concatenate` (preserve call signatures in
  decorators), `TYPE_CHECKING` guard for import-cycle-breaking imports.
  - Generic-key dict annotations: `dict[str, X]` is allowed when the key is a filename, identifier, path, or display string. Domain-typed values (e.g. `dict[str, MessageDef]`) should use `LintRuleId`, an enum, or a `Literal` type instead.
  - Unnamed-tuple dict values: `dict[str, tuple[str, ...]]` values should use a `NamedTuple`, dataclass, or `Protocol` with named fields instead of bare tuple literals.
  - Suppression comments (`# pylint: disable=...`, `# noqa`, `# type: ignore`) must carry a trailing technical justification comment explaining why the rule is suppressed.
- Runtime enforcement: `@beartype` on all first-party public functions/methods.
  Validates `Annotated` predicates at call boundary. No manual `if` guards for
  type contracts.


## Universal Exceptions

- Tests may have functions with more parameters than production code would
  normally allow (e.g., for parametrize fixtures), and this is an accepted
  exception.
## Module Layout

```text
mypackage/
├── __init__.py   # public API, __all__, module-level docs. No .pyi.
├── py.typed      # PEP 561 (empty, required)
├── auth.py       # feature implementation
├── auth.pyi      # public contract only
├── _parsing.py   # file-private helper
└── _parsing.pyi  # public contract only
```

## Symbol Convention

- `_` prefix: file-private, imported only by tests.
- No prefix: file surface (re-exported in `__init__.py`) or intra-module helper.
  Prefer moving intra-module helpers to dedicated `_` files.
  Tests import `_`-prefixed symbols only from their defining submodule, never through the package `__init__`.

## .pyi Rules

**No .pyi for:** `__init__.py` (unless `__getattr__` or logic present), test
bodies, standalone scripts, `conftest.py`, trivial test data.

**Required for all other `.py` files.**

**Scope:** Annotate everything in `.py`. Expose only public members in `.pyi` —
stub wins for consumers, `.py` wins internally.

```python
# thing.py
class Thing:
    _x: int
    def __init__(self, v: int) -> None: self._x = v
    def get(self) -> int: return self._x
    def _help(self) -> int: return self._x * 2  # typed, private

# thing.pyi
class Thing:
    def __init__(self, v: int) -> None: ...
    def get(self) -> int: ...          # _help and _x invisible to consumers
```

**Content:** Self-sufficient: params, returns, `@overload`, exceptions, generator
yields, context manager semantics. No `_`-prefix symbols.

**Re-exports in `__init__.py`:** explicit `from .module import Symbol`. No
`import *`. Dynamic `__getattr__` requires `.pyi`.

## Documentation

### Python Docstrings

- `__init__.py`: module-level docs — purpose, quick-start. Agents and users see
  contract without opening implementation.
- Typing > names > docstrings. Comments must not duplicate signatures.
- `.pyi` only: all usage docstrings (params, raises, edge cases) not apparent
  from names/types. Stub is sole contract file — read it, not the implementation.
- `.py`: implementation comments only (why, tricks). `help()` / `.__doc__` empty
  — intentional.

### Docstring Rules

- Generic-typed returns (`-> int/str/bool/...`) require a `Returns` clause describing the value.
- `_`-prefixed helpers MAY have a docstring (not required).

## Project Documentation Layout

### End User

- `{projectRoot}/README.md` — entry point. What, install, configure. Link to
  `docs/`.
- `docs/` — tutorials, config reference, troubleshooting.
- `docs/CHANGELOG.md` — user-visible changes only. No internal refactors.

### Contributor / Agent

- `AGENTS.md` — short index. Context for all agents. Link out, don't inline.
- `CONTRIBUTING.md` — setup, dev workflow, PR expectations, code style pointer.
- `design/` — architecture, decisions, data flow. One topic per file. ADR format.
- No dev changelog. Use git.

## Simplification

- Clarity over cleverness unless needed for performance.
- **Wrappers:** justified if removing them forces callers to understand an
  internal dependency's interface. Otherwise, inline.

  ```python
  # Justified — hides transport, narrows interface
  def get_user(id: UserId) -> User: ...

  # Trivial — inline into caller
  def log_info(msg: str) -> None: logger.info(msg)
  ```

- Use idioms to reduce LoC. Limit DIY — prefer pydantic, httpx, attrs.
- Duplicated logic → extract. Evaluate next abstraction level.
- Over-engineered patterns → direct approach.
- Remove checks redundant over type annotations / `@beartype`.
- Remove fallbacks for hard-declared dependencies.

### Idiom Examples

```python
# Dict comprehension
result = {item.id: item.name for item in items}

# Guard clause early returns
def process(data):
    if data is None: raise TypeError("Data is None")
    if not data.is_valid(): raise ValueError("Invalid data")
    if not data.has_permission(): raise PermissionError("No permission")
    return _do_work_data_checked(data)

# Walrus in comprehensions
filtered = [y for x in items if (y := transform(x)) > threshold]

# itertools
from itertools import groupby, chain
from operator import attrgetter

grouped = {
    k: list(v)
    for k, v in groupby(
        sorted(items, key=attrgetter("category")),
        key=attrgetter("category"),
    )
}
flat = list(chain.from_iterable(nested))
```

## Logging

- `structlog` throughout.
- No string formatting in log calls — use bound logger kwargs.
- Levels: `debug` diagnostic, `info` business events, `warning`
  degraded-but-continuing, `error` handled failure, `critical` service-stopping.
- Async: `structlog.contextvars` for request-scoped fields (request_id,
  user_id).

## Sync, Async, Timeouts, Parallelism

### Async

- Process-boundary-crossing calls (network, IPC, external APIs): async.
- Caller chain from boundary inward: all async.
  - Exception: local compute / io-bound shell cmds remain sync.
- Structured concurrency (`TaskGroup`) over raw `asyncio.gather`.
- Timeouts via `asyncio.timeout()` covering full operations.
- `asyncio.Semaphore` for concurrency limits.
- `asyncio.create_task` → store reference. Cancel all on shutdown. No orphaned
  tasks.
- Graceful shutdown: signal handlers, drain-in-flight, close connection pools.

### Sync

- In-process compute, file I/O, in-process DB: sync.
- No threading/multiprocessing without architect approval.

### Parallelism

Parallelize same-API calls only when:

1. Documented product feature.
2. Max concurrent call count guardrails in place.

Proxy: one inbound → one outbound unless parallelism is explicit product
feature.

### External Call Requirements

1. Timeout via `asyncio.timeout()`. Separate connect/read. Configurable,
   documented in `.pyi`. Neither `None` nor `0` in production.
2. Keepalive where applicable.
3. Connection pooling.
4. At least one retry for transient failures.
5. Circuit-breaker for APIs with documented failure modes.

### Backpressure

Proxy services: signal 429/503 when outbound capacity exhausted.

## Error Handling

### Boundaries

- External inputs (user, network, file, IPC, config): validated at process
  boundary. Trusted downstream.
- Public API: types specify acceptable inputs. `@beartype` enforces `Annotated`
  predicates at runtime. Validate beyond type contract (ranges, emptiness,
  format) with `annotated-types` predicates where possible, explicit checks
  otherwise.
- Helpers: may assume caller guarantees. Document assumptions inline.

### Failures

- IPC/API failures: handled or propagated. `except` without re-raise must
  comment why.
- Chain errors: `raise X from Y`.
- Expected → caller-facing error type. Unexpected → log internals, generic
  surface.
- Messages: human-diagnostic, include context (what, expected, got).
- Every caught error path: `structlog` error with structured fields.
- Prefer return types encoding failure (`Result`, `Optional`, union) over
  exceptions for expected control flow.

## Schema

- Structured files under git (config, YAML, JSON, frontmatter MD): validate
  against schema in lint.
- Schema is source of truth (pydantic model, TypedDict, JSON Schema, protobuf).
  Derive validators; no hand-duplicated constraints.
- Runtime boundary data (IPC, external input): validated at ingestion. Internal
  code trusts validated data.

## Tests

### Metrics

All request/response handlers and task processors maintain perf/stat counters:

- Usable and resettable by tests.
- Observable via health endpoints and logs.
- Typed contract (`TestMetricsProtocol`) for reset/read.

### Mocking Strategy

Mock only at true external boundaries. Never mock first-party code or local
compute libraries.

```text
L3 + L3Helper                      # internal logic
L2 depends on ImportedPackage      # third-party package
L1 + L1Helper depends on ExtAPI    # external API boundary

Mock boundary: ExtAPI only
ImportedPackage: real impl, verify assumptions in dedicated tests
First-party (L1, L2, L3, helpers): always real
```

Wrapping first-party code for injection acceptable; mocking not.
Verify DB/file content directly instead of mocking local layers.

### Test Categories

**`@pytest.mark.no_external_api`** — unit + local integration, ExtAPI mocked:

- `TestImportedPackageBehavior`: verify third-party assumptions.
- `@pytest.mark.implementation_detail`: `TestL1Helper`, `TestL3Helper`.
- `TestL1PublicApi`: L1 public API, ExtAPI mocked.
- `TestL2PublicApi`: L2 public API, no mocking ImportedPackage or L1.
- `TestL3PublicApi`: L3 public API, no mocking L2.

**`@pytest.mark.with_real_api`** — integration against real external APIs:

- `TestL1WithRealApi`: L1 (external interaction layer).
- `TestL3EndToEnd`: full end-to-end integration.
- `TestL2WithRealApi`: include if L2 complexity warrants.

### Coverage

Each layer tested independently. Near 100% layer + downstream (transitive).
Annotate hard-to-inject failure paths and defensive behaviors.

### Test Code Quality

- Optimize test LoC and complexity vigorously.
- Prefer long end-to-end scenario tests with meaningful intermediate assertions
  over narrow coverage-only tests.
- Reuse test code across success and failure injection paths.
- `@pytest.mark.parametrize` for discrete input-variant tests.
- `pytest.approx` for all float assertions.
- `hypothesis` for: parsers, serialization round-trips, data-transformation
  invariants — any input space that is continuous, combinatorial, or poorly
  bounded.
- Snapshot/golden-file testing for serialization and output-format tests.
- Test data factories for complex domain objects.
- Async: `pytest-asyncio` with `asyncio_mode = "auto"` in `pyproject.toml`.
  `anyio` + `@pytest.mark.anyio` for framework-agnostic tests.
  Tests are exempt from production-code parameter-count and complexity heuristics
  (e.g. many fixtures/params in a single test function is acceptable).

### Naming

`test_<method>_given_<condition>_then_<expected>`

### Isolation

- Every test independently runnable. No ordering dependencies.
- No shared mutable state without explicit fixture control.

### Fixture Scope

- `function`: mutable state (default).
- `session`: expensive setup (containers, DB engine). Prefer session-scoped
  engine with function-scoped transaction rollback for DB tests.
- `module`: mutable shared state expensive to re-create per module (e.g.,
  per-module schema migration).

### conftest.py Scope

- Directory-level shared fixtures → directory `conftest.py`.
- Project-wide fixtures → root `conftest.py`.
- Never put shared fixtures in test files.
