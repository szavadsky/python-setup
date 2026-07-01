# Contributing

## Setup

```bash
uv sync
```

## Development workflow

- `uv run lint` — run all linters
- `uv run pytest` — run all tests
- `uv run pytest tests/integration.py -v` — fit-for-purpose integration test (NOT marked slow)

## Pull request expectations

- Lint clean, tests pass, baseline regenerated
- Follow [CodingRules.md](CodingRules.md) for code style and conventions
- See [docs/custom-checks.md](docs/custom-checks.md) for checker development
