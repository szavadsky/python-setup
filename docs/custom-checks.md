# Writing Custom Pylint Checkers

`python-setup` provides a framework for custom pylint checkers that are automatically
discovered and registered. This document explains how to write and integrate new checkers.

## Checker structure

Each checker is a module in `src/python_setup_lint/checkers/` that:

1. Defines a `BaseChecker` subclass with a `msgs` dict and visitor methods.
2. Exports a `register(linter)` function that pylint calls at startup.

### Minimal checker

```python
"""Example custom checker."""

from __future__ import annotations

from astroid import nodes
from beartype import beartype
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter

from python_setup_lint.checkers._base import MessageDef


class ExampleChecker(BaseChecker):
    name: str = "example-checker"
    msgs: dict[str, MessageDef] = {
        "W9901": MessageDef(
            message="Example violation: '%s'",
            symbol="example-violation",
            description="Description of what this rule checks.",
        ),
    }

    @beartype
    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        if node.name == "bad_name":
            self.add_message("example-violation", node=node, args=(node.name,))


@beartype
def register(linter: PyLinter) -> None:
    linter.register_checker(ExampleChecker(linter))
```

## Message definition

Use `MessageDef` (a `NamedTuple` with `message`, `symbol`, `description` fields)
for all checker message definitions. This replaces the legacy bare-tuple pattern.

## Rule IDs

Custom checkers use `W` (warning) or `C` (convention) codes in the range `W97xx`–`W99xx`
and `C0xxx`. See `LintRuleId` in `checkers/_base.py` for the typed rule-id type.

## Registration

The installer automatically discovers all modules in `checkers/` that export a
`register` function. No manual plugin configuration is needed — the installer
writes the `load-plugins` entry to the consumer's `pyproject.toml`.

## Testing

Write tests using the `_make_tc` factory from `python_setup_lint.testing`:

```python
from python_setup_lint.checkers.conformance.example_checker import ExampleChecker
from python_setup_lint.testing import _make_tc as _make_tc_factory


def test_example_checker() -> None:
    tc = _make_tc_factory(ExampleChecker)
    module = astroid.parse("def bad_name(): pass")
    module.file = "/workspace/src/mod.py"
    tc.walk(module)
    msgs = tc.linter.release_messages()
    assert len(msgs) == 1
    assert msgs[0].msg_id == "example-violation"
```

## Available helpers

- `check_if_meaningful(text, *, rule, code_context, comment)` — heuristic check
  for meaningful suppression justifications (in `checkers/_base.py`).
- `_matches_path(str_path, patterns)` — glob/directory path matching.
- `_is_under_source_root(path, source_roots)` — source-root containment check.
- `_get_file_path(node)` — resolve a node's file path.
