
from __future__ import annotations

import functools
import re
import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

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


def _parse_raw_lines(stdout: str, _stderr: str) -> list[tuple[str, int]]:
    count = sum(1 for line in stdout.splitlines() if line.strip())
    if count == 0:
        return []
    return [("line", count)]


def _extra_tool_parser(
    *,
    entry: dict[str, object],
    location: str,
) -> Callable[..., list[tuple[str, int]]] | None:
    strategy = entry.get("parse_strategy", "none")
    if strategy == "none":
        return None
    if strategy in _BUILTIN_PARSE_STRATEGY_TO_PARSER:
        return _BUILTIN_PARSE_STRATEGY_TO_PARSER[cast(str, strategy)]
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


def _validate_extra_bool_fields(
    entry: dict[str, object], location: str
) -> tuple[bool, bool, bool]:
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
    return supports_fix, supports_path, supports_exclude


def _validate_extra_list_field(
    entry: dict[str, object], key: str, location: str
) -> list[str]:
    raw = entry.get(key, [])
    if not isinstance(raw, list):
        raise ExtraToolsConfigError(location, f"wrong type: {key} must be list[str]")
    for part in raw:
        if not isinstance(part, str):
            raise ExtraToolsConfigError(
                location, f"wrong type: {key} must be list[str]"
            )
    return list(raw)  # type: ignore[return-value]  # raw is list[object]; validated as list[str] above  # ty:ignore[invalid-return-type]


def _validate_extra_config_flag(
    entry: dict[str, object], location: str
) -> list[str] | None:
    config_flag_raw = entry.get("config_flag")
    if config_flag_raw is None:
        return None
    if isinstance(config_flag_raw, str):
        return [config_flag_raw]
    if isinstance(config_flag_raw, list):
        for part in config_flag_raw:
            if not isinstance(part, str):
                raise ExtraToolsConfigError(
                    location, "wrong type: config_flag must be str | list[str]"
                )
        return list(config_flag_raw)  # type: ignore[return-value]  # config_flag_raw is list[object]; validated as list[str] above  # ty:ignore[invalid-return-type]
    raise ExtraToolsConfigError(
        location, "wrong type: config_flag must be str | list[str]"
    )


def _validate_extra_fields(entry: dict[str, object], location: str) -> dict[str, Any]:  # validated dict, keys are known strings; return dict is built from validated fields, values are str|list[str]|None|bool by construction
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

    command = _validate_extra_list_field(entry, "command", location)
    if not command:
        raise ExtraToolsConfigError(
            location, "wrong type: command must be non-empty list[str]"
        )

    supports_fix, supports_path, supports_exclude = _validate_extra_bool_fields(
        entry, location
    )
    default_paths = _validate_extra_list_field(entry, "default_paths", location)
    config_flag = _validate_extra_config_flag(entry, location)

    strategy = entry.get("parse_strategy", "none")
    if not isinstance(strategy, str):
        raise ExtraToolsConfigError(location, "wrong type: parse_strategy must be str")
    if strategy not in PARSE_STRATEGIES:
        raise ExtraToolsConfigError(location, f"bad enum: parse_strategy {strategy!r}")

    return {
        "name": name,
        "command": command,
        "supports_fix": supports_fix,
        "supports_path": supports_path,
        "supports_exclude": supports_exclude,
        "default_paths": default_paths,
        "config_flag": config_flag,
        "strategy": strategy,
    }


def _validate_extra_name(name: str, seen_names: set[str], location: str) -> str:
    if name in TOOLS_BY_NAME:
        raise ExtraToolsConfigError(location, f"duplicate vs built-in: {name}")
    if name in seen_names:
        raise ExtraToolsConfigError(location, f"duplicate within file: {name}")
    return name


def _validate_extra(
    entry: dict[str, Any],  # validated dict, keys are known strings
    *,
    location: str,
    seen_names: set[str],
) -> _ExtraToolRegistration:
    fields = _validate_extra_fields(entry, location)
    name = _validate_extra_name(fields["name"], seen_names, location)
    parser = _extra_tool_parser(entry=entry, location=location)
    seen_names.add(name)
    spec = ToolSpec(
        name=name,
        command=fields["command"],
        supports_fix=fields["supports_fix"],
        supports_path=fields["supports_path"],
        supports_exclude=fields["supports_exclude"],
        default_paths=fields["default_paths"],
    )
    return _ExtraToolRegistration(
        spec=spec,
        statistics_flag=None,
        parser=parser,
        config_flag=fields["config_flag"],
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
    except OSError:  # pylint: disable=W9740  # best-effort stat fallback; logging would noise unavoidable IO degrade
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
