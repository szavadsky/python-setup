"""Declarative extra-tools loader (T11 v1) + T8 fail-fast machinery.

Loads ``[[tool.python-setup-lint.extra-tools]]`` entries from
``pyproject.toml`` and registers each as a live lint tool via
:func:`python_setup_lint.runner.dispatch.register_lint_tool`.  Purely
declarative: a consumer project adds a new lint step with NO Python code.

Per :data:`python_setup_lint.runner.parsers.PARSE_STRATEGIES`, the parser
for an extra is either a built-in (one of the 11 verbatim names) or one of
the two generic parsers (``regex_count`` / ``raw_lines``).

T8 fail-fast: malformed pyproject, unreadable ``pyproject.toml``, and
unknown tool names in :attr:`~python_setup_lint.runner.types.RunnerConfig.tools_override`
all raise :class:`ExtraToolsConfigError` — no silent fallback.
"""

from __future__ import annotations

import functools
import re
import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .dispatch import TOOLS_BY_NAME, register_lint_tool
from .parsers import _BUILTIN_PARSE_STRATEGY_TO_PARSER, PARSE_STRATEGIES
from .types import ToolSpec

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

__all__ = [
    "_EXTRA_TOOLS_CACHE",
    "_EXTRA_TOOLS_REGISTERED_PATHS",
    "_EXTRA_TOOL_FIELDS",
    "_EXTRA_TOOL_REQUIRED",
    "_REGEX_CACHE",
    "ExtraToolsConfigError",
    "_ExtraToolRegistration",
    "_compile_regex_count",
    "_extra_tool_parser",
    "_load_extra_tools",
    "_parse_raw_lines",
    "_parse_regex_count",
    "_register_extra_tools",
    "_reset_extra_tools_cache",
    "_validate_extra",
    "register_lint_tool",
]


class ExtraToolsConfigError(Exception):
    location: str
    reason: str

    def __init__(self, location: str, reason: str) -> None:
        self.location = location
        self.reason = reason
        super().__init__(f"[{location}] {reason}")


# Field set shipped in v1.  Update this set when adding a v2 field so
# :func:`_validate_extra` rejects unknown fields cleanly.
_EXTRA_TOOL_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "command",
        "supports_fix",
        "supports_path",
        "supports_exclude",
        "default_paths",
        "config_flag",
        "parse_strategy",
        "parse_regex",
    }
)

# Required v1 fields per :data:`_EXTRA_TOOL_FIELDS`.
_EXTRA_TOOL_REQUIRED: tuple[str, ...] = ("name", "command")


@dataclass(frozen=True)
class _ExtraToolRegistration:
    spec: ToolSpec
    statistics_flag: list[str] | None
    parser: Callable[..., list[tuple[str, int]]] | None
    config_flag: list[str] | None


# Compile a per-regex cache so the same parse_regex is not recompiled on
# every call.  Keyed by the regex source string.
_REGEX_CACHE: dict[str, re.Pattern[str]] = {}


def _compile_regex_count(pattern: str) -> re.Pattern[str]:
    cached = _REGEX_CACHE.get(pattern)
    if cached is not None:
        return cached
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        msg = f"invalid regex {pattern!r}: {exc}"
        raise ValueError(msg) from exc
    if compiled.groups != 1:
        msg = f"regex {pattern!r} must have exactly 1 capture group, has {compiled.groups}"
        raise ValueError(msg) from None
    _REGEX_CACHE[pattern] = compiled
    return compiled


def _parse_regex_count(
    stdout: str, stderr: str, *, regex: str
) -> list[tuple[str, int]]:
    compiled = _compile_regex_count(regex)
    counts: dict[str, int] = {}
    for line in (*stdout.splitlines(), *stderr.splitlines()):
        m = compiled.search(line)
        if m is not None:
            rule = m.group(1)
            counts[rule] = counts.get(rule, 0) + 1
    return list(counts.items())


def _parse_raw_lines(stdout: str, stderr: str) -> list[tuple[str, int]]:
    count = sum(1 for line in stdout.splitlines() if line.strip())
    if count == 0:
        return []
    return [("line", count)]


def _extra_tool_parser(
    *,
    entry: dict[str, Any],
    location: str,
) -> Callable[..., list[tuple[str, int]]] | None:
    strategy = entry.get("parse_strategy", "none")
    if strategy == "none":
        return None
    if strategy in _BUILTIN_PARSE_STRATEGY_TO_PARSER:
        return _BUILTIN_PARSE_STRATEGY_TO_PARSER[strategy]
    if strategy == "raw_lines":
        return _parse_raw_lines
    if strategy == "regex_count":
        regex = entry.get("parse_regex")
        if not isinstance(regex, str) or not regex.strip():
            raise ExtraToolsConfigError(
                location,
                'missing required field: parse_regex (required when parse_strategy == "regex_count")',
            )
        try:
            _compile_regex_count(regex)
        except ValueError as exc:
            raise ExtraToolsConfigError(
                location, f"regex missing or != 1 capture group: {exc}"
            ) from exc
        return functools.partial(_parse_regex_count, regex=regex)
    raise ExtraToolsConfigError(location, f"bad enum: parse_strategy {strategy!r}")


def _validate_extra(
    entry: dict[str, Any],
    *,
    location: str,
    seen_names: set[str],
) -> _ExtraToolRegistration:
    unknown = set(entry) - _EXTRA_TOOL_FIELDS
    if unknown:
        allowed = ", ".join(sorted(_EXTRA_TOOL_FIELDS))
        raise ExtraToolsConfigError(
            location,
            f"unknown field: {sorted(unknown)}; allowed: {allowed}",
        )

    # Required.
    for field in _EXTRA_TOOL_REQUIRED:
        if field not in entry:
            raise ExtraToolsConfigError(location, f"missing required field: {field}")

    name_raw = entry.get("name")
    if not isinstance(name_raw, str) or not name_raw.strip():
        raise ExtraToolsConfigError(location, "wrong type: name must be non-empty str")
    name = name_raw.strip()
    if not name:
        raise ExtraToolsConfigError(location, "empty name")
    if name in TOOLS_BY_NAME:
        raise ExtraToolsConfigError(location, f"duplicate vs built-in: {name}")
    if name in seen_names:
        raise ExtraToolsConfigError(location, f"duplicate within file: {name}")

    command_raw = entry.get("command")
    if not isinstance(command_raw, list) or not command_raw:
        raise ExtraToolsConfigError(
            location, "wrong type: command must be non-empty list[str]"
        )
    for part in command_raw:
        if not isinstance(part, str):
            raise ExtraToolsConfigError(
                location, "wrong type: command must be list[str]"
            )

    supports_fix = entry.get("supports_fix", False)
    if not isinstance(supports_fix, bool):
        raise ExtraToolsConfigError(location, "wrong type: supports_fix must be bool")
    supports_path = entry.get("supports_path", False)
    if not isinstance(supports_path, bool):
        raise ExtraToolsConfigError(location, "wrong type: supports_path must be bool")
    supports_exclude = entry.get("supports_exclude", False)
    if not isinstance(supports_exclude, bool):
        raise ExtraToolsConfigError(
            location, "wrong type: supports_exclude must be bool"
        )

    default_paths_raw = entry.get("default_paths", [])
    if not isinstance(default_paths_raw, list):
        raise ExtraToolsConfigError(
            location, "wrong type: default_paths must be list[str]"
        )
    for part in default_paths_raw:
        if not isinstance(part, str):
            raise ExtraToolsConfigError(
                location, "wrong type: default_paths must be list[str]"
            )

    config_flag_raw = entry.get("config_flag")
    if config_flag_raw is None:
        config_flag: list[str] | None = None
    elif isinstance(config_flag_raw, str):
        config_flag = [config_flag_raw]
    elif isinstance(config_flag_raw, list):
        for part in config_flag_raw:
            if not isinstance(part, str):
                raise ExtraToolsConfigError(
                    location, "wrong type: config_flag must be str | list[str]"
                )
        config_flag = list(config_flag_raw)
    else:
        raise ExtraToolsConfigError(
            location, "wrong type: config_flag must be str | list[str]"
        )

    strategy = entry.get("parse_strategy", "none")
    if not isinstance(strategy, str):
        raise ExtraToolsConfigError(location, "wrong type: parse_strategy must be str")
    if strategy not in PARSE_STRATEGIES:
        raise ExtraToolsConfigError(location, f"bad enum: parse_strategy {strategy!r}")

    # Side-effecting validation: parse_regex presence + group count + compiles.
    parser = _extra_tool_parser(entry=entry, location=location)

    seen_names.add(name)
    spec = ToolSpec(
        name=name,
        command=list(command_raw),
        supports_fix=supports_fix,
        supports_path=supports_path,
        supports_exclude=supports_exclude,
        default_paths=list(default_paths_raw),
    )
    return _ExtraToolRegistration(
        spec=spec,
        statistics_flag=None,
        parser=parser,
        config_flag=config_flag,
    )


# Per-process memoisation of ``_load_extra_tools`` results, keyed on
# ``(resolved_path, mtime_ns)`` so an edit mid-session triggers a fresh parse.
# Cleared via :func:`_reset_extra_tools_cache` (test-only).
_EXTRA_TOOLS_CACHE: dict[tuple[Path, int], list[_ExtraToolRegistration]] = {}
# Paths whose extras have already been registered (prevents re-running
# ``_register_extra_tools`` on every ``run_lint`` call).  Cleared alongside
# the cache in :func:`_reset_extra_tools_cache` so tests that force a
# re-parse also force re-registration.
_EXTRA_TOOLS_REGISTERED_PATHS: set[Path] = set()


def _reset_extra_tools_cache() -> None:
    _EXTRA_TOOLS_CACHE.clear()
    _EXTRA_TOOLS_REGISTERED_PATHS.clear()


def _load_extra_tools(cwd: Path) -> list[_ExtraToolRegistration]:
    pyproject = cwd / "pyproject.toml"
    resolved = pyproject.resolve()
    try:
        mtime = resolved.stat().st_mtime_ns
    except OSError:
        return []
    key = (resolved, mtime)
    cached = _EXTRA_TOOLS_CACHE.get(key)
    if cached is not None:
        return list(cached)
    try:
        with open(resolved, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ExtraToolsConfigError(
            str(resolved), f"pyproject unreadable: {exc}"
        ) from exc

    location = str(resolved)
    extras_raw = (
        data.get("tool", {}).get("python-setup-lint", {}).get("extra-tools", [])
    )
    if not isinstance(extras_raw, list):
        raise ExtraToolsConfigError(
            location, "wrong type: extra-tools must be a list of tables"
        )
    if not extras_raw:
        _EXTRA_TOOLS_CACHE[key] = []
        return []
    seen_names: set[str] = set()
    extras: list[_ExtraToolRegistration] = []
    for entry in extras_raw:
        if not isinstance(entry, dict):
            raise ExtraToolsConfigError(
                location, "wrong type: extra-tools entry must be a table"
            )
        extras.append(_validate_extra(entry, location=location, seen_names=seen_names))
    _EXTRA_TOOLS_CACHE[key] = list(extras)
    return list(extras)


def _register_extra_tools(registrations: list[_ExtraToolRegistration]) -> None:
    for registration in registrations:
        tool = registration.spec
        if tool.name in TOOLS_BY_NAME:
            raise ExtraToolsConfigError(
                "<runtime>",
                f"duplicate vs built-in: {tool.name}",
            )
        register_lint_tool(
            tool,
            statistics_flag=registration.statistics_flag,
            parser=registration.parser,
            config_flag=registration.config_flag,
        )
