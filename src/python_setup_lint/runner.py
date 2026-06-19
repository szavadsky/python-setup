"""Python CLI runner for the python-setup lint pipeline.

Replaces ``scripts/lint.sh``. Runs all 11 lint steps sequentially with
optional path scoping, fix mode, baseline diffing, and flexible failure
handling.

## CLI

---

::

    uv run lint                              # all 11 steps, fail-fast
    uv run lint --path src/python_setup_lint      # scope to a single dir
    uv run lint --fix                         # apply autofixes
    uv run lint --baseline lint.baseline      # diff vs stored baseline
    uv run lint --no-fail-fast                # run all, report aggregate
    uv run lint --exclude tests/              # exclude a path
"""

from __future__ import annotations

import argparse
import functools
import json
import logging
import subprocess
import sys
import time
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Sequence

class ToolSpec(NamedTuple):
    """Specification for a single lint tool.

    Attributes:
        name: Human-readable label for the tool.
        command: Base command list (no paths, no flag overrides).
        supports_fix: Whether the tool accepts ``--fix``.
        supports_path: Whether the tool accepts a positional path.
        supports_exclude: Whether the tool accepts ``--exclude`` / ``-e``.
        default_paths: Paths to use when no ``--path`` is given.
        fix_flags: Extra CLI flags to append when ``--fix`` is active.
        exclude_flag: CLI flag name for exclusion (default ``--exclude``).
    """

    name: str
    command: list[str]
    supports_fix: bool = False
    supports_path: bool = False
    supports_exclude: bool = False
    default_paths: list[str] = []
    fix_flags: tuple[str, ...] = ("--fix",)
    exclude_flag: str = "--exclude"

@dataclass
class LintResult:
    """Result of running a single lint tool."""

    tool_name: str
    exit_code: int
    stdout: str
    stderr: str
    elapsed: float

@dataclass
class ViolationCount:
    """Aggregated violation count for a single rule in a single tool."""

    tool: str
    rule: str
    count: int

    def __lt__(self, other: ViolationCount) -> bool:
        return (-self.count, self.tool, self.rule) < (-other.count, other.tool, other.rule)

@dataclass
class RunnerConfig:
    """Project-level configuration for the lint runner.

    Attributes:
        cwd: Working directory — all path resolution is relative to this.
        package_name: Package name passed to ``mypy.stubtest`` and
            ``pyright verifytypes``.  ``None`` skips those tools.
        default_py_dirs: Default directories for pylint ``_find_py_files``
            discovery when no ``--path`` is given.
        tools_override: Optional list of tool names to run.  ``None``
            runs all 11 default tools.  Tool names map to internal
            :class:`ToolSpec` entries via ``TOOLS_BY_NAME`` (built-ins) and
            the live :data:`LINT_TOOLS` registry (built-ins + extras).
            Unknown names raise :class:`ExtraToolsConfigError` (T8 fail-fast)
            rather than silently running a subset — a typo in a tool name
            is treated as malformed configuration.
        secrets_baseline: Path (relative to ``cwd``) to the
            detect-secrets baseline file.
        config_paths: Optional mapping of tool identifiers to config file
            paths.  Canonical keys are the built-in :class:`ToolSpec`
            labels: ``ruff check``, ``mypy``, ``pylint``,
            ``pyright check``, ``rumdl check``, ``ty check`` (matching the
            names used in :func:`_config_flag_for` and the strategy
            subclasses).  The CLI ``--config TOOL=PATH`` flag additionally
            accepts short aliases (``ruff``, ``pyright``, ``rumdl``, ``ty``,
            plus the canonical labels) which it normalises to the canonical
            label — unrecognised keys are rejected with a non-zero
            ``SystemExit`` and a message naming the offending key (T8
            fail-fast).

            * ``ruff check``: ``--config <path>``
            * ``mypy``: ``--config-file <path>``
            * ``pylint``: ``--rcfile <path>``
            * ``pyright check``: ``--project <path>``
            * ``rumdl check``: ``--config <path>``
            * ``ty check``: ``--config <path>``
    """

    cwd: Path
    package_name: str | None = None
    default_py_dirs: list[str] | None = None
    tools_override: list[str] | None = None
    secrets_baseline: str = ".secrets.baseline"
    config_paths: dict[str, Path] | None = None

    def __post_init__(self) -> None:
        if self.default_py_dirs is None:
            self.default_py_dirs = ["src", "scripts", "tests"]
        if self.config_paths is None:
            self.config_paths = {}

# ── Tool definitions ────────────────────────────────────────────────

TOOLS: list[ToolSpec] = [
    ToolSpec("tach check", ["tach", "check"], supports_exclude=True, exclude_flag="-e"),
    ToolSpec(
        "ruff check",
        ["ruff", "check"],
        supports_fix=True,
        supports_path=True,
        supports_exclude=True,
        default_paths=["src/", "tests/"],
        fix_flags=("--fix", "--exit-non-zero-on-fix"),
    ),
    ToolSpec(
        "rumdl check",
        ["rumdl", "check"],
        supports_fix=True,
        supports_path=True,
        supports_exclude=True,
        fix_flags=("--fix",),
    ),
    ToolSpec(
        "mypy",
        ["mypy"],
        supports_path=True,
        default_paths=["."],
    ),
    ToolSpec(
        "yamllint",
        ["yamllint"],
        supports_path=True,
        default_paths=["config/*.yaml"],
    ),
    ToolSpec(
        "ty check",
        ["ty", "check"],
        supports_fix=True,
        supports_path=True,
        supports_exclude=True,
        fix_flags=("--fix",),
    ),
    ToolSpec(
        "mypy.stubtest",
        ["python", "-m", "mypy.stubtest"],
    ),
    ToolSpec(
        "pyright check",
        ["pyright", "--outputjson"],
        supports_path=True,
        default_paths=["."],
    ),
    ToolSpec(
        "pyright verify types",
        ["pyright", "--verifytypes"],
    ),
    ToolSpec(
        "pylint",
        ["pylint"],
        supports_path=True,
    ),
    ToolSpec(
        "detect-secrets",
        ["detect-secrets-hook"],
    ),
]

TOOLS_BY_NAME: dict[str, ToolSpec] = {t.name: t for t in TOOLS}

# T8 fail-fast ``--config TOOL=PATH`` keys: canonical labels + short aliases
# (``ruff`` → ``ruff check``).  Unknown ids exit non-zero via argparse
# ``parser.error`` — no silent drop where a typo produced an entry
# :func:`_config_flag_for` never read.
_CONFIG_KEY_ALIASES: dict[str, str] = {
    "ruff": "ruff check",
    "pyright": "pyright check",
    "rumdl": "rumdl check",
    "ty": "ty check",
    "mypy": "mypy",
    "pylint": "pylint",
}
_SUPPORTED_CONFIG_KEYS: frozenset[str] = frozenset(
    set(_CONFIG_KEY_ALIASES) | set(_CONFIG_KEY_ALIASES.values())
)

# ── Strategy registry ──────────────────────────────────────────────
#
# A per-tool ``LintTool`` strategy wraps command construction, statistics
# flags, and statistics parsing.  Built-ins reuse the existing
# module-level helpers (``_build_command``, ``_build_statistics_flags``,
# ``_STATISTICS_PARSERS``) so behaviour stays byte-equivalent.  Extras
# registered via :func:`register_lint_tool` land on :class:`GenericLintTool`,
# which composes the same generic flag logic via the spec's ``supports_*``
# booleans (the common-case branches of ``_build_command``).
#
# The dispatch is DEFAULT-aware: ``STRATEGIES.get(name)`` returns ``None``
# for unknown names, and :func:`_strategy_for` synthesises a
# :class:`GenericLintTool` on lookup so T11 extras never ``KeyError``.


class LintTool:
    """Strategy for a single lint tool.

    Implementations encapsulate per-tool command construction, statistics
    flags, and statistics parsing.  Config-agnostic: the
    ``package_name is None`` skip for ``mypy.stubtest`` /
    ``pyright verify types`` stays in :func:`run_lint`, not here.

    Subclasses override :meth:`build_command` / :meth:`statistics_flags`
    / :meth:`parse_statistics` to specialise per-tool behaviour.  The
    default implementations consult the module-level dispatch tables
    (``_build_command`` / ``_build_statistics_flags`` /
    ``_STATISTICS_PARSERS``) so built-in behaviour stays verbatim.
    """

    spec: ToolSpec

    def __init__(self, spec: ToolSpec) -> None:
        self.spec = spec

    @property
    def name(self) -> str:
        """Tool label — mirrors the spec's name."""
        return self.spec.name

    def build_command(
        self,
        *,
        config: RunnerConfig,
        fix: bool = False,
        path: str | None = None,
        exclude: str | None = None,
    ) -> list[str]:
        """Build the full command list for this tool given runtime flags.

        Default: delegates to the module-level :func:`_build_command`,
        which is the authoritative literal specification of each built-in
        tool's command shape.
        """
        return _build_command(self.spec, config=config, fix=fix, path=path, exclude=exclude)

    def statistics_flags(self) -> list[str]:
        """Extra CLI flags for statistics output mode.

        Default: delegates to :func:`_build_statistics_flags`.
        """
        return _build_statistics_flags(self.spec)

    def parse_statistics(self, stdout: str, stderr: str) -> list[tuple[str, int]]:
        """Parse this tool's stdout/stderr into ``(rule, count)`` pairs.

        Default: looks up the parser in :data:`_STATISTICS_PARSERS`.
        Returns an empty list when no parser is registered.
        """
        parser = _STATISTICS_PARSERS.get(self.spec.name)
        if parser is None:
            return []
        return parser(stdout, stderr)


# ── Per-tool strategy subclasses ─────────────────────────────────
# Three built-in tools have fundamentally different command shapes that
# cannot be expressed via ToolSpec declarative fields alone.  Each
# overrides ``build_command`` with tool-specific logic, eliminating
# ``if spec.name ==`` branches from ``_build_command``.


class _StubtestLintTool(LintTool):
    """Strategy for ``mypy.stubtest`` — builds command from ``package_name`` + optional allowlist."""

    def build_command(
        self,
        *,
        config: RunnerConfig,
        fix: bool = False,
        path: str | None = None,
        exclude: str | None = None,
    ) -> list[str]:
        spec = self.spec
        cwd = config.cwd
        cmd = list(spec.command)
        config_paths = config.config_paths or {}
        mypy_config = config_paths.get("mypy")
        cmd.extend(
            [
                config.package_name,
                "--concise",
                "--ignore-missing-stub",
                "--mypy-config-file",
                str(mypy_config) if mypy_config is not None else "pyproject.toml",
            ]
        )
        allowlist_path = cwd / "stubtest_allowlist.txt"
        if allowlist_path.exists():
            cmd.extend(["--allowlist", "stubtest_allowlist.txt"])
        return cmd


class _VerifyTypesLintTool(LintTool):
    """Strategy for ``pyright verify types`` — builds command from ``package_name`` + optional project."""

    def build_command(
        self,
        *,
        config: RunnerConfig,
        fix: bool = False,
        path: str | None = None,
        exclude: str | None = None,
    ) -> list[str]:
        spec = self.spec
        cmd = list(spec.command)
        config_paths = config.config_paths or {}
        pyright_config = config_paths.get("pyright check")
        cmd.extend([config.package_name, "--ignoreexternal", "--outputjson"])
        if pyright_config is not None:
            cmd.extend(["--project", str(pyright_config)])
        return cmd


class _DetectSecretsLintTool(LintTool):
    """Strategy for ``detect-secrets`` — wraps in ``bash -c`` pipeline over git-ls-files."""

    def build_command(
        self,
        *,
        config: RunnerConfig,
        fix: bool = False,
        path: str | None = None,
        exclude: str | None = None,
    ) -> list[str]:
        spec = self.spec
        _ = path, fix, exclude
        return ["bash", "-c", f"git ls-files -z | xargs -0 {' '.join(spec.command)} --baseline {config.secrets_baseline}"]


class _PylintLintTool(LintTool):
    """Strategy for ``pylint`` — always resolves ``_find_py_files()`` for path expansion.

    Pylint expects file arguments, not directory paths.  Unlike other tools
    that accept a directory and recurse internally, pylint needs an explicit
    list of ``.py`` files.  This strategy always calls ``_find_py_files``
    regardless of whether ``spec.default_paths`` is empty, ensuring pylint
    never runs with an empty file list.
    """

    def build_command(
        self,
        *,
        config: RunnerConfig,
        fix: bool = False,
        path: str | None = None,
        exclude: str | None = None,
    ) -> list[str]:
        spec = self.spec
        cmd = list(spec.command)
        config_paths = config.config_paths or {}

        # ── Shared config files ───────────────────────────────
        cmd.extend(_config_flag_for(spec.name, config_paths.get(spec.name)))

        # ── Fix flags ────────────────────────────────────────
        if fix and spec.supports_fix:
            cmd.extend(spec.fix_flags)

        # ── Path scoping — always expand to .py files ────────
        if path is not None:
            paths = _find_py_files([path], cwd=config.cwd)
        else:
            paths = _find_py_files(config.default_py_dirs, cwd=config.cwd)

        # Expand globs (e.g. config/*.yaml)
        paths = _expand_globs(paths, cwd=config.cwd)

        if paths:
            cmd.extend(paths)

        # ── Exclude flags ────────────────────────────────────
        if exclude is not None and spec.supports_exclude:
            cmd.extend([spec.exclude_flag, exclude])

        return cmd


# Populate the strategy registry from the 11 built-ins.
_STRATEGY_CLASSES: dict[str, type[LintTool]] = {
    "mypy.stubtest": _StubtestLintTool,
    "pyright verify types": _VerifyTypesLintTool,
    "detect-secrets": _DetectSecretsLintTool,
    "pylint": _PylintLintTool,
}
STRATEGIES: dict[str, LintTool] = {
    spec.name: (_STRATEGY_CLASSES.get(spec.name) or LintTool)(spec)
    for spec in TOOLS
}


class GenericLintTool(LintTool):
    """Minimal strategy for extras registered via :func:`register_lint_tool`.

    Carries three optional declarative fields supplied at registration:

    * ``statistics_flag`` — explicit CLI flag(s) for statistics output.
    * ``parser`` — callable returning ``list[tuple[str, int]]`` for stats.
    * ``config_flag`` — explicit CLI flag(s) for external config file.

    Unset fields fall back to the generic ``_build_command`` /
    ``_build_statistics_flags`` / ``_STATISTICS_PARSERS`` lookups, mirroring
    the common-case branches of :func:`_build_command`.  The 11 built-ins
    keep their own strategies; only extras land on :class:`GenericLintTool`.
    """

    def __init__(
        self,
        spec: ToolSpec,
        *,
        statistics_flag: list[str] | None = None,
        parser: Callable[..., list[tuple[str, int]]] | None = None,
        config_flag: list[str] | None = None,
    ) -> None:
        super().__init__(spec)
        self._statistics_flag = statistics_flag
        self._parser = parser
        self._config_flag = config_flag

    def build_command(
        self,
        *,
        config: RunnerConfig,
        fix: bool = False,
        path: str | None = None,
        exclude: str | None = None,
    ) -> list[str]:
        """Build the command, forwarding the declarative ``config_flag``.

        The 11 built-ins inherit :meth:`LintTool.build_command` which uses
        :func:`_config_flag_for`'s hardcoded name→flags dict.  Extras declare
        their own ``config_flag`` (a list like ``["--config"]``) at registration;
        this override forwards it to :func:`_build_command` via the
        ``config_flag_override`` seam so the declarative flag actually reaches
        the constructed command (the dict lookup would otherwise return ``[]``
        for an unknown name, silently dropping the flag).
        """
        return _build_command(
            self.spec,
            config=config,
            fix=fix,
            path=path,
            exclude=exclude,
            config_flag_override=self._config_flag,
        )

    def statistics_flags(self) -> list[str]:
        """Return the explicit statistics flag(s) when set; else module-level lookup."""
        if self._statistics_flag is not None:
            return list(self._statistics_flag)
        return _build_statistics_flags(self.spec)

    def parse_statistics(self, stdout: str, stderr: str) -> list[tuple[str, int]]:
        """Use the explicit parser when set; else module-level lookup."""
        if self._parser is not None:
            return self._parser(stdout, stderr)
        parser = _STATISTICS_PARSERS.get(self.spec.name)
        if parser is None:
            return []
        return parser(stdout, stderr)


# Live registry of declared ``ToolSpec`` instances.
# At import time it mirrors the 11 built-ins from :data:`TOOLS`; extras
# registered via :func:`register_lint_tool` append to it.  :data:`TOOLS`
# stays the frozen built-in list and is kept as a legacy-compat alias.
LINT_TOOLS: list[ToolSpec] = list(TOOLS)


def _strategy_for(name: str, spec: ToolSpec) -> LintTool:
    """Resolve a strategy for *name*, default-aware.

    Lookup uses :data:`STRATEGIES` first.  Unknown names synthesise a
    :class:`GenericLintTool` for *spec* — this is the default-aware
    dispatch seam that lets T11 extras reach the pipeline without
    ``KeyError``.  A cached strategy under :data:`STRATEGIES` (the built-ins
    or any previously-registered extra) is returned as-is.
    """
    cached = STRATEGIES.get(name)
    if cached is not None:
        return cached
    return GenericLintTool(spec)


def register_lint_tool(
    tool: ToolSpec,
    *,
    statistics_flag: list[str] | None = None,
    parser: Callable[..., list[tuple[str, int]]] | None = None,
    config_flag: list[str] | None = None,
) -> None:
    """Append *tool* to the live registry and register its strategy.

    For names not already in :data:`STRATEGIES`, a :class:`GenericLintTool`
    is synthesised from ``tool`` + the three optional declarative fields
    and registered under ``STRATEGIES[tool.name]``.  For built-in names
    (already present in :data:`STRATEGIES`), the existing strategy is kept
    and only :data:`LINT_TOOLS`'s entry for that name is updated.

    Idempotent per ``tool.name`` — a re-call with the same name is an
    update-in-place (no duplicate append).  This protects against T11's
    re-merge on repeated ``run_lint`` calls accumulating duplicate entries.
    """
    # Idempotent: replace any existing LINT_TOOLS entry with the same name;
    # otherwise append.
    for i, existing in enumerate(LINT_TOOLS):
        if existing.name == tool.name:
            LINT_TOOLS[i] = tool
            break
    else:
        LINT_TOOLS.append(tool)

    # Register strategy only when no per-tool class already exists (built-ins
    # keep their strategies; non-builtin names get a GenericLintTool).
    if tool.name not in STRATEGIES:
        STRATEGIES[tool.name] = GenericLintTool(
            tool,
            statistics_flag=statistics_flag,
            parser=parser,
            config_flag=config_flag,
        )


## ── Extra-tools config (T11 v1) ────────────────────────────────────
##
## Loads ``[[tool.python-setup-lint.extra-tools]]`` entries from
## ``pyproject.toml`` and registers each as a live lint tool via
## :func:`register_lint_tool`.  Purely declarative: a consumer project adds
## a new lint step with NO Python code.  Per :data:`PARSE_STRATEGIES`, the
## parser for an extra is either a built-in (one of the 11 verbatim names)
## or one of the two new generic parsers (``regex_count`` / ``raw_lines``).


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


class ExtraToolsConfigError(Exception):
    """Typed fail-fast for malformed pyproject / invalid tool config (T8).

    Serves the whole T8 fail-fast envelope — see ``runner.pyi`` for the
    full contract.  Three failure shapes all raise this:

    * Malformed ``[[tool.python-setup-lint.extra-tools]]`` entry (T8 R4 table).
    * Unreadable ``pyproject.toml`` (TOMLDecodeError / OSError wrapped via
      ``raise ... from exc`` — no raw ``tomllib`` exception leaks).
    * Unknown tool name in :attr:`RunnerConfig.tools_override` (location is
      the synthetic ``"<RunnerConfig.tools_override>"`` token; no file).

    :func:`run_lint` does NOT catch it — propagated uncaught so the caller
    surface (CLI ``main()`` returns int; Python API caller catches or takes
    the default traceback + non-zero exit) is the caller's choice.
    Intentionally distinct from T6's ``SystemExit`` for raw-TOML paperover.

    Attributes:
        location: Resolved pyproject path, or ``"<RunnerConfig.tools_override>"``
            for programmatic-input errors that have no associated file.
        reason: Stable one-line code identifier of the failure shape.
    """

    def __init__(self, location: str, reason: str) -> None:
        self.location = location
        self.reason = reason
        super().__init__(f"[{location}] {reason}")


@dataclass(frozen=True)
class _ExtraToolRegistration:
    """Bundle a validated extra's :class:`ToolSpec` + the registration kwargs.

    :func:`_load_extra_tools` returns these; :func:`_register_extra_tools`
    unpacks each into a :func:`register_lint_tool` call.  Carrying the parser
    callable + ``config_flag`` separately is necessary because
    :class:`ToolSpec` itself is the unchanged NamedTuple from the cycle-1
    contract (T4 owns its shape; T11 only constructs it positionally).
    """

    spec: ToolSpec
    statistics_flag: list[str] | None
    parser: Callable[..., list[tuple[str, int]]] | None
    config_flag: list[str] | None


# Compile a per-regex cache so the same parse_regex is not recompiled on
# every call.  Keyed by the regex source string.
_REGEX_CACHE: dict[str, re.Pattern[str]] = {}


def _compile_regex_count(pattern: str) -> re.Pattern[str]:
    """Compile *pattern* once and cache the result by source string.

    Raises:
        ValueError: when *pattern* is not a valid regex or does NOT have
            exactly one capture group.
    """
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
        # ``from None`` (not ``from exc``) — ``exc`` only exists in the
        # ``except re.error`` branch above; referencing it here is an
        # ``UnboundLocalError`` that shadows the intended ``ValueError``.
        raise ValueError(msg) from None
    _REGEX_CACHE[pattern] = compiled
    return compiled


def _parse_regex_count(stdout: str, stderr: str, *, regex: str) -> list[tuple[str, int]]:
    """Count distinct capture-group values across all stdout+stderr lines.

    The regex MUST have exactly one capture group; the captured text is the
    rule identifier.  Lines that do not match are skipped.  Both stdout and
    stderr are scanned — most CLIs split diagnostics across the two streams.

    Args:
        stdout: Process stdout.
        stderr: Process stderr.
        regex: Source string of the regex; compiled lazily and cached.
    """
    compiled = _compile_regex_count(regex)
    counts: dict[str, int] = {}
    for line in (*stdout.splitlines(), *stderr.splitlines()):
        m = compiled.search(line)
        if m is not None:
            rule = m.group(1)
            counts[rule] = counts.get(rule, 0) + 1
    return list(counts.items())


def _parse_raw_lines(stdout: str, stderr: str) -> list[tuple[str, int]]:
    """Count non-empty stdout lines as a single synthetic rule ``"line"``.

    Escape hatch for tools with no notion of rule identifiers: every
    non-empty stdout line is one violation.  stderr is ignored (most tools
    surface diagnostics on stdout; stderr typically carries progress noise).
    """
    count = sum(1 for line in stdout.splitlines() if line.strip())
    if count == 0:
        return []
    return [("line", count)]


# Closed ``parse_strategy`` enum — names the 11 built-in parsers verbatim
# plus the two new generic parsers (T11) plus ``"none"`` (skip stats
# aggregation, mirroring the ``_aggregate_statistics`` skip at L557).
# Update this string set AND the ``_BUILTIN_PARSE_STRATEGY_TO_PARSER`` map
# together when adding a parser.
PARSE_STRATEGIES: frozenset[str] = frozenset(
    {
        "none",
        "ruff_statistics",
        "rumdl_statistics",
        "pylint_json2",
        "pyright_outputjson",
        "pyright_verify_types",
        "mypy_stderr",
        "ty_concise",
        "tach_json",
        "yamllint_parsable",
        "stubtest_stderr",
        "detect_secrets_json",
        "regex_count",
        "raw_lines",
    }
)

# Map the parse_strategy enum name to the parser callable for the 11
# built-in strategy names (verbatim).  Populated by ``.update()`` AFTER all
# ``_parse_*`` functions are defined (see near the parser dispatch table).
# ``regex_count`` is parameterised by the per-entry ``parse_regex`` source
# so it's resolved in :func:`_extra_tool_parser`.  ``raw_lines`` is the
# single-arg form returned directly.
_BUILTIN_PARSE_STRATEGY_TO_PARSER: dict[str, Callable[..., list[tuple[str, int]]]] = {}  # populated below


def _extra_tool_parser(
    *,
    entry: dict[str, Any],
    location: str,
) -> Callable[..., list[tuple[str, int]]] | None:
    """Resolve the parser callable for an extra-tools entry's ``parse_strategy``.

    Returns ``None`` for ``"none"`` (skip statistics aggregation — matches
    :func:`_aggregate_statistics`).  For built-in strategy names, returns
    the parser verbatim.  For ``"regex_count"``, validates ``parse_regex``
    is present and has exactly one capture group; returns a closure binding
    the compiled regex.  For ``"raw_lines"``, returns the parser directly.

    Args:
        entry: The parsed TOML entry dict.
        location: Stable location string used in raised :class:`ExtraToolsConfigError`.

    Raises:
        ExtraToolsConfigError: on a bad enum value, missing/invalid
            ``parse_regex``, or a regex without exactly one capture group.
    """
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
                "missing required field: parse_regex (required when parse_strategy == \"regex_count\")",
            )
        try:
            _compile_regex_count(regex)
        except ValueError as exc:
            raise ExtraToolsConfigError(location, f"regex missing or != 1 capture group: {exc}") from exc
        return functools.partial(_parse_regex_count, regex=regex)
    raise ExtraToolsConfigError(location, f"bad enum: parse_strategy {strategy!r}")


def _validate_extra(
    entry: dict[str, Any],
    *,
    location: str,
    seen_names: set[str],
) -> _ExtraToolRegistration:
    """Validate a single ``[[tool.python-setup-lint.extra-tools]]`` entry.

    Implements the T8 R4 failure table: missing required field, wrong type,
    empty name, duplicate within file, duplicate vs built-in, bad enum,
    regex missing or != 1 capture group, unknown field.  Each failure raises
    :class:`ExtraToolsConfigError` with a one-line ``reason`` identifier.

    Args:
        entry: Raw parsed TOML entry dict (the value of one ``[[...]]`` block).
        location: Stable location string used in raised errors.
        seen_names: Names already validated from entries earlier in the same file;
            mutated to add this entry's name on success.

    Returns:
        :class:`_ExtraToolRegistration` carrying the built :class:`ToolSpec`
        and the per-tool ``parser``/``statistics_flag``/``config_flag`` fields
        for :func:`_register_extra_tools` to feed to :func:`register_lint_tool`.

    Raises:
        ExtraToolsConfigError: on any malformed shape per T8 R4.
    """
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
        raise ExtraToolsConfigError(location, "wrong type: command must be non-empty list[str]")
    for part in command_raw:
        if not isinstance(part, str):
            raise ExtraToolsConfigError(location, "wrong type: command must be list[str]")

    supports_fix = entry.get("supports_fix", False)
    if not isinstance(supports_fix, bool):
        raise ExtraToolsConfigError(location, "wrong type: supports_fix must be bool")
    supports_path = entry.get("supports_path", False)
    if not isinstance(supports_path, bool):
        raise ExtraToolsConfigError(location, "wrong type: supports_path must be bool")
    supports_exclude = entry.get("supports_exclude", False)
    if not isinstance(supports_exclude, bool):
        raise ExtraToolsConfigError(location, "wrong type: supports_exclude must be bool")

    default_paths_raw = entry.get("default_paths", [])
    if not isinstance(default_paths_raw, list):
        raise ExtraToolsConfigError(location, "wrong type: default_paths must be list[str]")
    for part in default_paths_raw:
        if not isinstance(part, str):
            raise ExtraToolsConfigError(location, "wrong type: default_paths must be list[str]")

    config_flag_raw = entry.get("config_flag")
    if config_flag_raw is None:
        config_flag: list[str] | None = None
    elif isinstance(config_flag_raw, str):
        config_flag = [config_flag_raw]
    elif isinstance(config_flag_raw, list):
        for part in config_flag_raw:
            if not isinstance(part, str):
                raise ExtraToolsConfigError(location, "wrong type: config_flag must be str | list[str]")
        config_flag = list(config_flag_raw)
    else:
        raise ExtraToolsConfigError(location, "wrong type: config_flag must be str | list[str]")

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
    # statistics_flag is not a v1 declarative field (per T8 R7: deferred to
    # v2); extras with a non-``none`` strategy rely on the strategy's own
    # ``parse_statistics`` to surface violations.  ``statistics_flag`` here
    # is ``None`` so :class:`GenericLintTool` falls back to the empty
    # default for unknown names (no extra CLI flag emitted in stats mode).
    return _ExtraToolRegistration(
        spec=spec,
        statistics_flag=None,
        parser=parser,
        config_flag=config_flag,
    )


# Per-process memoisation of ``_load_extra_tools`` results, keyed on
# ``(resolved_path, mtime_ns)`` so an edit mid-session triggers a fresh parse.
# Mirror of consultant.mcp's ``_load_pyproject_toml`` memo.  Cleared via
# :func:`_reset_extra_tools_cache` (test-only).
_EXTRA_TOOLS_CACHE: dict[tuple[Path, int], list[_ExtraToolRegistration]] = {}
# Paths whose extras have already been registered (prevents re-running
# ``_register_extra_tools`` on every ``run_lint`` call).  Cleared alongside
# the cache in :func:`_reset_extra_tools_cache` so tests that force a
# re-parse also force re-registration.
_EXTRA_TOOLS_REGISTERED_PATHS: set[Path] = set()


def _reset_extra_tools_cache() -> None:
    """Clear the per-process memo for ``_load_extra_tools`` (test-only).

    Production callers should NOT invoke this; the cache invalidates on
    mtime change.  Tests use it to force a re-parse against a rewritten
    synthetic pyproject.toml in the same process.
    """
    _EXTRA_TOOLS_CACHE.clear()
    _EXTRA_TOOLS_REGISTERED_PATHS.clear()


def _load_extra_tools(cwd: Path) -> list[_ExtraToolRegistration]:
    """Load ``[[tool.python-setup-lint.extra-tools]]`` entries from ``cwd/pyproject.toml``.

    Reads + validates one ``pyproject.toml``.  Returns ``[]`` when:

    * ``pyproject.toml`` does not exist in ``cwd``.
    * The file lacks the ``[tool.python-setup-lint]`` section entirely.
    * The ``extra-tools`` key is absent or empty (no ``[[...]]`` array).
    * Every ``[[...]]`` block is empty (a no-op merge per design).

    Memoised per-process keyed on ``(resolved_path, mtime_ns)`` so a
    repeated ``run_lint`` invocation reuses the cached parse.  An mtime
    change invalidates the cache for that path.

    Args:
        cwd: Project root the lint pipeline is configured against.

    Returns:
        Validated :class:`_ExtraToolRegistration` instances ready for
        :func:`_register_extra_tools`.

    Raises:
        ExtraToolsConfigError: when ``pyproject.toml`` is unreadable OR a
            ``[[...]]`` entry fails :func:`_validate_extra` (T8 R4 table).
    """
    pyproject = cwd / "pyproject.toml"
    resolved = pyproject.resolve()
    try:
        mtime = resolved.stat().st_mtime_ns
    except OSError:
        # Treat as pyproject-less path (loader returns no extras).  We do
        # NOT raise for missing files — consumers without extras are the
        # common case and must no-op cleanly; ``_load_extra_tools`` only
        # raises on present-but-malformed pyproject content.
        return []
    key = (resolved, mtime)
    cached = _EXTRA_TOOLS_CACHE.get(key)
    if cached is not None:
        return list(cached)
    try:
        with open(resolved, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ExtraToolsConfigError(str(resolved), f"pyproject unreadable: {exc}") from exc

    location = str(resolved)
    extras_raw = data.get("tool", {}).get("python-setup-lint", {}).get("extra-tools", [])
    if not isinstance(extras_raw, list):
        raise ExtraToolsConfigError(location, "wrong type: extra-tools must be a list of tables")
    if not extras_raw:
        _EXTRA_TOOLS_CACHE[key] = []
        return []
    seen_names: set[str] = set()
    extras: list[_ExtraToolRegistration] = []
    for entry in extras_raw:
        if not isinstance(entry, dict):
            raise ExtraToolsConfigError(location, "wrong type: extra-tools entry must be a table")
        extras.append(_validate_extra(entry, location=location, seen_names=seen_names))
    _EXTRA_TOOLS_CACHE[key] = list(extras)
    return list(extras)


def _register_extra_tools(registrations: list[_ExtraToolRegistration]) -> None:
    """Register each validated extra via :func:`register_lint_tool`.

    Idempotent — :func:`register_lint_tool` is already idempotent per
    ``tool.name`` (it replaces the matching :data:`LINT_TOOLS` entry rather
    than appending), so a re-merge in the same process is a no-op.  This is
    required because :func:`run_lint` may be invoked multiple times in
    tests against the same pyproject.

    Args:
        registrations: :class:`_ExtraToolRegistration` instances produced by
            :func:`_load_extra_tools`; each carries the validated
            :class:`ToolSpec` + the ``parser``/``config_flag`` to feed
            :func:`register_lint_tool` so the live :data:`STRATEGIES` entry
            is a :class:`GenericLintTool` with the right parser bound (NOT
            a strategy that silently produces empty stats).

    Raises:
        ExtraToolsConfigError: when an extra's name collides with a built-in
            name (T8 R3 — the live registry MUST NOT shadow a built-in).
            Defense-in-depth: :func:`_validate_extra` already rejects this
            at load time; this guard catches callers that bypass the loader
            (manual registration from test scaffolding).
    """
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

## ── Path helpers ────────────────────────────────────────────────────

def _find_py_files(dirs: Sequence[str], *, cwd: Path) -> list[str]:

## Find all .py files under *dirs* sorted uniquely (relative to cwd)

    files: set[Path] = set()
    for d in dirs:
        p = cwd / d
        if p.is_dir():
            files.update(p.rglob("*.py"))
        elif p.is_file() and p.suffix == ".py":
            files.add(p)
    return sorted(str(f.relative_to(cwd)) for f in files)

def _expand_globs(paths: Sequence[str], *, cwd: Path) -> list[str]:

## Expand shell glob patterns (*, ?) in *paths* relative to cwd

    cwd = Path(cwd)
    result: list[str] = []
    for p in paths:
        if "*" in p or "?" in p:
            expanded = sorted(str(f.relative_to(cwd)) for f in cwd.glob(p))
            result.extend(expanded)
        else:
            result.append(p)
    return result

## ── Command construction ───────────────────────────────────────────

def _config_flag_for(spec_name: str, config_path: Path | None) -> list[str]:
    """Build CLI flag that tells a tool to use *config_path*.

    Returns an empty list when no config path is provided or the tool does not
    support external configuration files.
    """
    if config_path is None:
        return []
    flags: dict[str, list[str]] = {
        "ruff check": ["--config", str(config_path)],
        "mypy": ["--config-file", str(config_path)],
        "pylint": ["--rcfile", str(config_path)],
        "pyright check": ["--project", str(config_path)],
        "pyright verify types": ["--project", str(config_path)],
        "rumdl check": ["--config", str(config_path)],
        "ty check": ["--config", str(config_path)],
    }
    return flags.get(spec_name, [])

def _build_command(
    spec: ToolSpec,
    *,
    config: RunnerConfig,
    fix: bool = False,
    path: str | None = None,
    exclude: str | None = None,
    config_flag_override: list[str] | None = None,
) -> list[str]:

## Build the full command list for a tool spec given runtime flags

    cwd = config.cwd
    cmd = list(spec.command)
    config_paths = config.config_paths or {}

    # ── Shared config files ───────────────────────────────────
    if config_flag_override is not None:
        extra_cfg = config_paths.get(spec.name)
        if extra_cfg is not None:
            cmd.extend([*config_flag_override, str(extra_cfg)])
    else:
        cmd.extend(_config_flag_for(spec.name, config_paths.get(spec.name)))

    # ── Fix flags (data-driven via ToolSpec.fix_flags) ────────
    if fix and spec.supports_fix:
        cmd.extend(spec.fix_flags)

    # ── Path scoping ───────────────────────────────────────────
    paths: list[str] = []
    if path is not None and spec.supports_path:
        paths = [path]
    elif spec.default_paths:
        paths = list(spec.default_paths)

    # Expand globs (e.g. config/*.yaml)
    paths = _expand_globs(paths, cwd=cwd)

    if paths:
        cmd.extend(paths)

    # ── Exclude flags (data-driven via ToolSpec.exclude_flag) ─
    if exclude is not None and spec.supports_exclude:
        cmd.extend([spec.exclude_flag, exclude])

    return cmd

## ── Statistics command flags ───────────────────────────────────────

def _build_statistics_flags(spec: ToolSpec) -> list[str]:

## Build extra CLI flags for statistics output mode

## Each tool uses a different flag or format to emit machine-readable

    # violation data. Returns an empty list when the tool already emits
    # parseable output by default.
    flags: dict[str, list[str]] = {
        "ruff check": ["--statistics"],
        "rumdl check": ["--statistics"],
        "pylint": ["--output-format=json2"],
        "pyright check": ["--outputjson"],
        "mypy": ["--no-error-summary"],
        "ty check": ["--output-format", "concise"],
        "tach check": ["--output", "json"],
        "yamllint": ["-f", "parsable"],
    }
    return flags.get(spec.name, [])

## ── Statistics parsers ────────────────────────────────────────────

import re

def _parse_ruff_statistics(stdout: str, stderr: str) -> list[tuple[str, int]]:

## Parse ruff --statistics output

## Each non-header line: <count>\t<rule>\t

    _ = stderr
    counts: dict[str, int] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line or line.startswith(("-", "Count")):
            continue
        m = re.match(r"^(\d+)\s+(\S+)", line)
        if m:
            rule = m.group(2)
            counts[rule] = counts.get(rule, 0) + int(m.group(1))
    return list(counts.items())

def _parse_rumdl_statistics(stdout: str, stderr: str) -> list[tuple[str, int]]:

## Parse rumdl --statistics output

## Format matches ruff: <count>\t<rule>\t

    _ = stderr
    counts: dict[str, int] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line or line.startswith(("-", "Count")):
            continue
        m = re.match(r"^(\d+)\s+(\S+)", line)
        if m:
            rule = m.group(2)
            counts[rule] = counts.get(rule, 0) + int(m.group(1))
    return list(counts.items())

def _parse_pylint_json2(stdout: str, stderr: str) -> list[tuple[str, int]]:

## Parse pylint --output-format=json2 output

## JSON array of dicts, each with a ``symbol`` key

    _ = stderr
    try:
        raw: Any = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(raw, list):
        return []
    counts: dict[str, int] = {}
    for msg in raw:
        symbol = msg.get("symbol") if isinstance(msg, dict) else None
        if isinstance(symbol, str):
            counts[symbol] = counts.get(symbol, 0) + 1
    return list(counts.items())

def _parse_pyright_outputjson(stdout: str, stderr: str) -> list[tuple[str, int]]:

## Parse pyright --outputjson output

## JSON object with generalDiagnostics array, each with a rule key

    _ = stderr
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    diags = data.get("generalDiagnostics", [])
    if not isinstance(diags, list):
        return []
    counts: dict[str, int] = {}
    for d in diags:
        rule = d.get("rule") if isinstance(d, dict) else None
        if isinstance(rule, str):
            counts[rule] = counts.get(rule, 0) + 1
    return list(counts.items())

def _parse_pyright_verify_types(stdout: str, stderr: str) -> list[tuple[str, int]]:

## Parse pyright --verifytypes JSON output

## JSON object with typeCompleteness containing per-symbol results

## Reports any symbolName with completeness < 1.0 as verifytypes:incomplete

    _ = stderr
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    tc = data.get("typeCompleteness", {})
    if not isinstance(tc, dict):
        return []
    symbols = tc.get("symbols", [])
    if not isinstance(symbols, list):
        return []
    incomplete = 0
    for s in symbols:
        if isinstance(s, dict) and s.get("completeness", 1.0) < 1.0:
            incomplete += 1
    if incomplete:
        return [("verifytypes:incomplete", incomplete)]
    return []

def _parse_mypy_stderr(stdout: str, stderr: str) -> list[tuple[str, int]]:

## Parse mypy stderr for error-code statistics

## Each error line: file:line: error: message [error-code]

## Extracts the [error-code] from the end of each line

    _ = stdout
    counts: dict[str, int] = {}
    for line in stderr.splitlines():
        m = re.search(r"\[([^\]]+)\]$", line)
        if m:
            code = m.group(1)
            counts[code] = counts.get(code, 0) + 1
    return list(counts.items())

def _parse_ty_concise(stdout: str, stderr: str) -> list[tuple[str, int]]:

## Parse ty --output-format concise output

## Lines: file:line:col: error_code message

## The error code is the first non-numeric token after the colon-space

    _ = stderr
    counts: dict[str, int] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue

## Format: file:line:col: error_code message

## Extract error_code after the last colon-space

        m = re.search(r":\s+(\S+)\s+", line)
        if m:
            code = m.group(1)
            counts[code] = counts.get(code, 0) + 1
    return list(counts.items())

def _parse_tach_json(stdout: str, stderr: str) -> list[tuple[str, int]]:

## Parse tach --output json output

## JSON object with errors list

    _ = stderr
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    errors = data.get("errors", [])
    if isinstance(errors, list) and errors:
        return [("tach:error", len(errors))]
    return []

def _parse_yamllint_parsable(stdout: str, stderr: str) -> list[tuple[str, int]]:

## Parse yamllint -f parsable output

## Format: file:line:col:rule_id:message

    _ = stderr
    counts: dict[str, int] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(":")
        # file:line:col:rule_id:message → parts[3] is rule_id
        if len(parts) >= 4:
            rule_id = parts[3]
            if rule_id:
                counts[rule_id] = counts.get(rule_id, 0) + 1
    return list(counts.items())

def _parse_stubtest_stderr(stdout: str, stderr: str) -> list[tuple[str, int]]:

## Parse mypy.stubtest stderr for error codes

## Lines: error: <code>

## Extract the code after "error: " and before the first space

    _ = stdout
    counts: dict[str, int] = {}
    for line in stderr.splitlines():
        m = re.match(r"^error:\s+(\S+)", line)
        if m:
            code = m.group(1)
            counts[code] = counts.get(code, 0) + 1
    return list(counts.items())

def _parse_detect_secrets_json(stdout: str, stderr: str) -> list[tuple[str, int]]:

## Parse detect-secrets --json output

## JSON object with results dict mapping filename to list of secrets

    # each with a type key.
    _ = stderr
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    results = data.get("results", {})
    if not isinstance(results, dict):
        return []
    counts: dict[str, int] = {}
    for secrets in results.values():
        if not isinstance(secrets, list):
            continue
        for secret in secrets:
            if isinstance(secret, dict):
                secret_type = secret.get("type", "unknown")
                if isinstance(secret_type, str):
                    counts[secret_type] = counts.get(secret_type, 0) + 1
    return list(counts.items())

## ── Parser dispatch table ──────────────────────────────────────────

_STATISTICS_PARSERS: dict[str, Callable[..., list[tuple[str, int]]]] = {
    "ruff check": _parse_ruff_statistics,
    "rumdl check": _parse_rumdl_statistics,
    "pylint": _parse_pylint_json2,
    "pyright check": _parse_pyright_outputjson,
    "pyright verify types": _parse_pyright_verify_types,
    "mypy": _parse_mypy_stderr,
    "ty check": _parse_ty_concise,
    "tach check": _parse_tach_json,
    "yamllint": _parse_yamllint_parsable,
    "mypy.stubtest": _parse_stubtest_stderr,
    "detect-secrets": _parse_detect_secrets_json,
}

# Now that all ``_parse_*`` are defined, populate the strategy-name → parser
# map used by :func:`_extra_tool_parser` to resolve an extra's
# ``parse_strategy`` enum to a stats callable (the 11 built-in names).
_BUILTIN_PARSE_STRATEGY_TO_PARSER.update(
    {
        "ruff_statistics": _parse_ruff_statistics,
        "rumdl_statistics": _parse_rumdl_statistics,
        "pylint_json2": _parse_pylint_json2,
        "pyright_outputjson": _parse_pyright_outputjson,
        "pyright_verify_types": _parse_pyright_verify_types,
        "mypy_stderr": _parse_mypy_stderr,
        "ty_concise": _parse_ty_concise,
        "tach_json": _parse_tach_json,
        "yamllint_parsable": _parse_yamllint_parsable,
        "stubtest_stderr": _parse_stubtest_stderr,
        "detect_secrets_json": _parse_detect_secrets_json,
    }
)

## ── Statistics aggregation and display ────────────────────────────

def _aggregate_statistics(results: list[LintResult]) -> list[ViolationCount]:

## Aggregate violation counts per tool per rule from all tool results

## Returns a list sorted by count descending, then tool, then rule

## Only tools with a registered parser are included

    counts: list[ViolationCount] = []
    for result in results:
        # Default-aware dispatch: prefer the strategy registered for this
        # tool name; fall back to the module-level parser table.  The
        # fallback keeps older tool-name consumers (which may not yet have
        # a strategy entry) working without behaviour drift.  Both paths
        # swallow parser exceptions, matching the legacy behaviour.
        try:
            strategy = STRATEGIES.get(result.tool_name)
            if strategy is not None:
                violations = strategy.parse_statistics(result.stdout, result.stderr)
            else:
                parser = _STATISTICS_PARSERS.get(result.tool_name)
                if parser is None:
                    continue
                violations = parser(result.stdout, result.stderr)
        except Exception as e:
            logger.warning("stats parser %s failed: %s", result.tool_name, e)
            continue
        for rule, count in violations:
            counts.append(
                ViolationCount(
                    tool=result.tool_name,
                    rule=rule,
                    count=count,
                )
            )
    counts.sort()
    return counts

def _print_statistics_table(counts: list[ViolationCount]) -> None:

## Print violation counts as an aligned human-readable table

    if not counts:
        print("\nNo violations found.")
        return
    print(f"\n{'=' * 60}")
    print("VIOLATION STATISTICS")
    print(f"{'=' * 60}")
    print(f"{'Tool':<20} {'Rule':<30} {'Count':>6}")
    print("-" * 60)
    for v in counts:
        print(f"{v.tool:<20} {v.rule:<30} {v.count:>6}")

def _sort_counts(
    counts: list[ViolationCount],
    *,
    sort_by_rule: bool = False,
) -> list[ViolationCount]:
    """Return *counts* in the requested sort order.

    Default sort (``sort_by_rule=False``): count descending, then tool, then rule.
    ``sort_by_rule=True``: rule ascending, then tool, then count descending.
    """
    if sort_by_rule:
        return sorted(counts, key=lambda v: (v.rule, v.tool, -v.count))
    return sorted(counts)

def _print_statistics_grouped(
    counts: list[ViolationCount],
    *,
    group: str = "tool",
    sort_by_rule: bool = False,
) -> None:
    """Print violation counts grouped by *group* key.

    * ``"tool"`` — section per tool.
    * ``"rule"`` — section per rule, showing per-tool counts.
    * ``"file"`` — same layout as ``"tool"`` (no per-file data in statistics).
    """
    if not counts:
        print("\nNo violations found.")
        return

    sorted_counts = _sort_counts(counts, sort_by_rule=sort_by_rule)

    if group in ("tool", "file"):
        # Group by tool
        from itertools import groupby

        by_tool: dict[str, list[ViolationCount]] = {}
        for v in sorted_counts:
            by_tool.setdefault(v.tool, []).append(v)

        print(f"\n{'=' * 60}")
        print("VIOLATION STATISTICS (grouped by tool)")
        print(f"{'=' * 60}")
        total = 0
        for tool_name, entries in by_tool.items():
            print(f"\n  [{tool_name}]")
            for v in entries:
                print(f"    {v.rule:<30} {v.count:>6}")
                total += v.count
            print(f"    {'─' * 38}")
            print(f"    {'Subtotal':<30} {sum(e.count for e in entries):>6}")
        print(f"\n{'─' * 60}")
        print(f"{'Total':<30} {total:>6}")

    elif group == "rule":
        # Group by rule
        from itertools import groupby

        by_rule: dict[str, list[ViolationCount]] = {}
        for v in sorted_counts:
            by_rule.setdefault(v.rule, []).append(v)

        print(f"\n{'=' * 60}")
        print("VIOLATION STATISTICS (grouped by rule)")
        print(f"{'=' * 60}")
        total = 0
        for rule, entries in by_rule.items():
            print(f"\n  [{rule}]")
            for v in entries:
                print(f"    {v.tool:<20} {v.count:>6}")
                total += v.count
            print(f"    {'─' * 28}")
            print(f"    {'Subtotal':<20} {sum(e.count for e in entries):>6}")
        print(f"\n{'─' * 60}")
        print(f"{'Total':<30} {total:>6}")

## ── Subprocess runner ──────────────────────────────────────────────

def _run_cmd(cmd: list[str], *, cwd: Path, label: str) -> LintResult:

## Run a single command and return its result

    start = time.monotonic()
    proc = subprocess.run( # noqa: S603 # commands are constructed from internal ToolSpec, not user input
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    elapsed = time.monotonic() - start
    return LintResult(
        tool_name=label,
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        elapsed=elapsed,
    )

def _print_result(result: LintResult) -> None:

## Print a formatted result to stdout

    status = "PASSED" if result.exit_code == 0 else f"FAILED (exit={result.exit_code})"
    print(f"\n{'=' * 60}")
    print(f"[{result.tool_name}] {status} [{result.elapsed:.1f}s]")
    print(f"{'=' * 60}")
    if result.stderr:
        print(result.stderr, end="")
    if result.stdout:
        print(result.stdout, end="")

## ── Baseline support ────────────────────────────────────────────────

def _capture_baseline(results: list[LintResult]) -> list[dict[str, Any]]:

## Capture structured baseline data from tool results

    # pyright/rumdl diagnostics stored as parsed JSON for stable diffing;
    # other tools store raw stdout.

## Rumdl success output includes timing that changes per run — strip it

    import re as _re

    baseline: list[dict[str, Any]] = []
    for r in results:
        entry: dict[str, Any] = {
            "tool": r.tool_name,
            "exit_code": r.exit_code,
        }
        if r.tool_name in ("pyright check", "pyright verify types") and r.stdout:
            try:
                diag = json.loads(r.stdout)
                if isinstance(diag, dict):
                    diag.pop("time", None)
                    diag.pop("version", None)
                    summary = diag.get("summary")
                    if isinstance(summary, dict):
                        summary.pop("timeInSec", None)
                entry["diagnostics"] = diag
            except (json.JSONDecodeError, ValueError):
                entry["output"] = r.stdout
        elif r.tool_name == "rumdl check" and r.stdout:
            try:
                entry["diagnostics"] = json.loads(r.stdout)
            except (json.JSONDecodeError, ValueError):
                entry["output"] = _re.sub(r"\(\d+ms\)", "(XXXms)", r.stdout)
        elif r.tool_name == "ruff check" and r.stdout:
            # Sort ruff violations to make baseline stable across runs
            entry["output"] = "\n".join(sorted(r.stdout.splitlines()))
        else:
            entry["output"] = r.stdout
        baseline.append(entry)
    return baseline

def _diff_baseline(
    current: list[LintResult],
    baseline_path: Path,
) -> list[str]:
    """Compare current results against saved baseline.

    Returns a list of human-readable violation descriptions for any
    NEW or CHANGED issues (additions only).  Removals (shrinkage) are
    silently auto-recorded by rewriting the baseline in-place.

    .. note::

        Set-diff on output lines collapses duplicate counts; a count
        increase on the SAME signature is not flagged.  Pylint uses
        ``_pylint_inventory`` to fold counts before set-diff, so pylint
        count changes are detected.

    Args:
        current: :class:`LintResult` list from current run.
        baseline_path: Path to a JSON file previously written by
            :func:`_capture_baseline`.
    """
    if not baseline_path.exists():
        return [f"Baseline file not found: {baseline_path}"]

    try:
        with open(baseline_path) as f:
            raw: list[dict[str, Any]] = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        return [f"Cannot read baseline: {exc}"]
    saved: list[dict[str, Any]] = raw

    # Normalise saved diagnostics: strip volatile fields (timeInSec) that
    # change between runs so baseline comparison is stable.
    for entry in saved:
        saved_diag = entry.get("diagnostics")
        if isinstance(saved_diag, dict):
            saved_summary = saved_diag.get("summary")
            if isinstance(saved_summary, dict):
                saved_summary.pop("timeInSec", None)

    saved_map: dict[str, dict[str, Any]] = {}
    for entry in saved:
        tool_name = entry.get("tool", "")
        if isinstance(tool_name, str):
            saved_map[tool_name] = entry

    violations: list[str] = []
    baseline_modified = False
    current_tool_names = {r.tool_name for r in current}

    # Tools in saved but absent from current → shrinkage (remove from baseline)
    # Remove ALL entries with the same tool name (not just the last one),
    # preventing stale duplicate entries from leaking into the rewritten baseline.
    for tool_name in list(saved_map.keys()):
        if tool_name not in current_tool_names:
            for entry in saved[:]:
                if entry.get("tool") == tool_name:
                    saved.remove(entry)
                    baseline_modified = True
            del saved_map[tool_name]

    import re as _re

    def _pylint_signature(line: str) -> str | None:
        dup = _re.search(
            r"Similar lines in 2 files\s*==(\S+):\[(\d+):(\d+)\]\s*==(\S+):\[(\d+):(\d+)\]",
            line,
        )
        if dup:
            parts = sorted(
                [
                    f"{dup.group(1)}:{dup.group(2)}-{dup.group(3)}",
                    f"{dup.group(4)}:{dup.group(5)}-{dup.group(6)}",
                ]
            )
            return f"R0801:{parts[0]}<->{parts[1]}"
        cyc = _re.search(r"Cyclic import \(([^)]+)\)", line)
        if cyc:
            return f"R0401:{cyc.group(1)}"
        msg = _re.search(r"(\S+\.py:\d+:\d+:\s*[A-Z]\d+:)", line)
        if msg:
            return msg.group(1)
        return None

    def _pylint_inventory(output: str) -> str:
        sigs = {}
        for line in output.splitlines():
            sig = _pylint_signature(line)
            if sig is not None:
                sigs[sig] = sigs.get(sig, 0) + 1
        return "\n".join(sorted(f"{count} {sig}" for sig, count in sigs.items()))

    for r in current:
        saved_entry = saved_map.get(r.tool_name)
        if saved_entry is None:
            violations.append(f"[{r.tool_name}] New tool result — no baseline entry")
            continue

        # ── Exit code check ──────────────────────────────────────
        saved_rc = saved_entry.get("exit_code", -1)
        if r.exit_code != saved_rc:
            if r.exit_code == 0 and saved_rc != 0:
                # Tool now passes → pure shrinkage
                saved_entry["exit_code"] = 0
                saved_entry.pop("output", None)
                saved_entry.pop("diagnostics", None)
                baseline_modified = True
                continue
            if saved_rc == 0 and r.exit_code != 0:
                violations.append(
                    f"[{r.tool_name}] Exit code changed: 0 → {r.exit_code}"
                )
            # else: both non-zero but different → fall through to output comparison

        # ── Diagnostics comparison (pyright) ────────────────────
        saved_diag = saved_entry.get("diagnostics")
        if saved_diag is not None:
            try:
                current_diag = json.loads(r.stdout) if r.stdout else None
            except (json.JSONDecodeError, ValueError):
                current_diag = None

            # D4: When saved has diagnostics (dict) but current stdout is
            # non-JSON (current_diag is None), treat as a REGRESSION — the
            # tool that used to emit JSON no longer does.  Do NOT treat as
            # shrinkage.
            if isinstance(saved_diag, dict) and current_diag is None:
                violations.append(
                    f"[{r.tool_name}] Diagnostics lost: current output is not valid JSON"
                )
                continue

            if isinstance(current_diag, dict):
                current_diag.pop("time", None)
                current_diag.pop("version", None)
                current_summary = current_diag.get("summary")
                if isinstance(current_summary, dict):
                    current_summary.pop("timeInSec", None)
            if current_diag != saved_diag:

                def _diag_error_count(d: Any) -> int:
                    if isinstance(d, dict):
                        s = d.get("summary", {})
                        if isinstance(s, dict):
                            return s.get("errorCount", 0) + s.get("warningCount", 0)
                    return 0

                saved_errors = _diag_error_count(saved_diag)
                current_errors = _diag_error_count(current_diag)
                if current_errors < saved_errors:
                    # Shrinkage: update baseline
                    saved_entry["diagnostics"] = current_diag
                    baseline_modified = True
                if current_errors > saved_errors:
                    violations.append(
                        f"[{r.tool_name}] Diagnostics changed (new/different violations)"
                    )
                if current_errors == saved_errors and current_diag != saved_diag:
                    violations.append(
                        f"[{r.tool_name}] Diagnostics changed (new/different violations)"
                    )
            continue

        # ── Output comparison ────────────────────────────────────
        saved_output = saved_entry.get("output") or ""

        # Normalise both outputs using the same per-tool logic
        if r.tool_name == "ruff check":
            current_output = "\n".join(sorted((r.stdout or "").splitlines()))
            saved_output_norm = "\n".join(sorted(saved_output.splitlines()))
        elif r.tool_name == "rumdl check":
            current_output = _re.sub(r"\(\d+ms\)", "(XXXms)", r.stdout or "")
            saved_output_norm = _re.sub(r"\(\d+ms\)", "(XXXms)", saved_output)
        elif r.tool_name == "pylint":
            current_output = _pylint_inventory(r.stdout or "")
            saved_output_norm = _pylint_inventory(saved_output)
        else:
            current_output = r.stdout or ""
            saved_output_norm = saved_output

        if current_output == saved_output_norm:
            continue

        # Line-by-line set diff to distinguish add vs remove
        # D6: rstrip each line so trailing-whitespace-only differences are
        # not flagged as regressions.
        saved_lines = set(l.rstrip() for l in saved_output_norm.splitlines())
        current_lines = set(l.rstrip() for l in current_output.splitlines())
        removed_lines = saved_lines - current_lines
        added_lines = current_lines - saved_lines

        if removed_lines:
            # Shrinkage: update baseline entry to only keep remaining lines
            remaining = sorted(saved_lines & current_lines)
            saved_entry["output"] = "\n".join(remaining)
            baseline_modified = True

        if added_lines:
            violations.append(
                f"[{r.tool_name}] Output changed (new/different violations)"
            )

    if baseline_modified:
        # D5: wrap write in try/except OSError so an unwritable baseline
        # degrades gracefully with a violation message (matching the
        # read-path handling at L1457), rather than crashing the pipeline.
        try:
            with open(baseline_path, "w") as f:
                json.dump(saved, f, indent=2, sort_keys=True)
        except OSError as exc:
            return [f"Cannot write baseline: {exc}"]

    return violations

## ── Main runner ─────────────────────────────────────────────────────

def run_lint(
    *,
    config: RunnerConfig | None = None,
    path: str | None = None,
    fix: bool = False,
    baseline: str | None = None,
    exclude: str | None = None,
    no_fail_fast: bool = False,
    statistics: bool = False,
    statistics_format: str = "table",
    overwrite_baseline: bool = False,
    group: str = "none",
    sort_by_rule: bool = False,
) -> int:

## Run the full lint pipeline

## Returns 0 if all tools pass, non-zero on any failure

    if config is None:
        config = RunnerConfig(cwd=Path.cwd())

    # ── Extras merge (T11 v1) ─────────────────────────────────────
    # Load + validate ``[[tool.python-setup-lint.extra-tools]]`` from the
    # project's ``pyproject.toml`` and register each entry as a live
    # :class:`ToolSpec` via :func:`register_lint_tool`.  Idempotent per
    # ``tool.name`` so a re-invocation in the same process is a no-op.
    # ``ExtraToolsConfigError`` is NOT caught here — it propagates uncaught
    # to the caller (T8 R4: per-entry validation errors surface as a
    # traceback + non-zero exit, not silent fallback).
    extras = _load_extra_tools(config.cwd)
    cwd_resolved = config.cwd.resolve()
    if extras and cwd_resolved not in _EXTRA_TOOLS_REGISTERED_PATHS:
        _register_extra_tools(extras)
        _EXTRA_TOOLS_REGISTERED_PATHS.add(cwd_resolved)

    # Resolve which tools to run.
    # Resolve which tools to run.  ``tools_override=None`` → iterate the
    # live registry (:data:`LINT_TOOLS`); with a list, each name MUST resolve
    # against the live registry — an unknown name raises
    # :class:`ExtraToolsConfigError` (T8 fail-fast, location
    # ``<RunnerConfig.tools_override>``) rather than silently running a subset.
    selected: list[ToolSpec] = []
    if config.tools_override is not None:
        lint_tools_by_name = {t.name: t for t in LINT_TOOLS}
        for raw_name in config.tools_override:
            name = raw_name.strip()
            spec = lint_tools_by_name.get(name)
            if spec is None:
                raise ExtraToolsConfigError(
                    "<RunnerConfig.tools_override>",
                    f"unknown tool name: {name!r}; "
                    f"known: {sorted(lint_tools_by_name)}",
                )
            selected.append(spec)
    else:
        selected = list(LINT_TOOLS)

    results: list[LintResult] = []
    overall_rc = 0
    cwd = config.cwd

    for spec in selected:
        # Skip tools that require package_name when none configured.
        # Per DESIGN-0 D14: this skip stays in run_lint (NOT inside
        # strategies) so strategies stay config-agnostic.
        if spec.name in ("mypy.stubtest", "pyright verify types") and config.package_name is None:
            print(f"  [{spec.name}] SKIPPED: --package-name not set", file=sys.stderr)
            continue

        # Report unsupported flags before running — use stderr so --statistics --format json is not polluted
        if fix and not spec.supports_fix:
            print(f"  [{spec.name}] --fix: N/A (tool does not support autofix)", file=sys.stderr)
        if path is not None and not spec.supports_path:
            print(f"  [{spec.name}] --path: N/A (tool does not support path scoping)", file=sys.stderr)
        if exclude is not None and not spec.supports_exclude:
            print(f"  [{spec.name}] --exclude: N/A (tool does not support exclude)", file=sys.stderr)

        # Default-aware dispatch — unknown names synthesise a GenericLintTool.
        strategy = _strategy_for(spec.name, spec)
        cmd = strategy.build_command(config=config, fix=fix, path=path, exclude=exclude)
        if statistics:
            cmd.extend(strategy.statistics_flags())
        result = _run_cmd(cmd, cwd=cwd, label=spec.name)
        results.append(result)
        if not statistics:
            _print_result(result)

        if result.exit_code != 0:
            overall_rc = result.exit_code
            if not no_fail_fast:
                break

    # ── Statistics output ──────────────────────────────────────
    if statistics:
        vcounts = _aggregate_statistics(results)
        if statistics_format == "json":
            print(
                json.dumps(
                    [{"tool": v.tool, "rule": v.rule, "count": v.count} for v in vcounts],
                    indent=2,
                )
            )
        elif group != "none":
            _print_statistics_grouped(vcounts, group=group, sort_by_rule=sort_by_rule)
        else:
            if sort_by_rule:
                vcounts = _sort_counts(vcounts, sort_by_rule=True)
            _print_statistics_table(vcounts)

    # ── Baseline handling ──────────────────────────────────────
    if baseline is not None:
        base_path = Path(baseline)
        if base_path.exists() and not overwrite_baseline:
            new_issues = _diff_baseline(results, base_path)
            if new_issues:
                print(f"\n{'=' * 60}")
                print("[baseline] New violations detected:")
                for issue in new_issues:
                    print(f"  \u2022 {issue}")
                if overall_rc == 0:
                    overall_rc = 1
            else:
                print(f"\n{'=' * 60}")
                print("[baseline] No new violations — output matches baseline")
                overall_rc = 0
        else:
            action = "Overwriting" if base_path.exists() else "Creating"
            print(f"\n{'=' * 60}")
            print(f"[baseline] {action} baseline \u2192 {baseline}")
            base_data = _capture_baseline(results)
            base_path.parent.mkdir(parents=True, exist_ok=True)
            with open(base_path, "w") as f:
                json.dump(base_data, f, indent=2, sort_keys=True)
            print(f"[baseline] Baseline saved ({len(base_data)} tool entries)")
            overall_rc = 0

    return overall_rc

def main(argv: list[str] | None = None, *, config: RunnerConfig | None = None) -> int:
    """CLI entry point for ``uv run lint``.

    When *config* is provided, CLI flags still override the pre-built
    configuration (cwd, package-name, default-py-dirs, tools, config-paths
    can all be set on the command line).  This lets thin wrappers construct a
    default configuration while still exposing the full CLI surface.
    """
    parser = argparse.ArgumentParser(
        description="Run the python-setup lint pipeline",
    )
    parser.add_argument(
        "--path",
        help="Scope lint to a specific file or directory",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Apply autofixes (ruff, rumdl, ty)",
    )
    parser.add_argument(
        "--baseline",
        metavar="FILE",
        help="Compare against saved baseline (creates if missing)",
    )
    parser.add_argument(
        "--exclude",
        help="Exclude a file or directory pattern",
    )
    parser.add_argument(
        "--no-fail-fast",
        action="store_true",
        help="Run all tools, accumulate failures",
    )
    parser.add_argument(
        "--overwrite-baseline",
        action="store_true",
        help="Force overwrite of existing baseline file (used with --baseline)",
    )
    parser.add_argument(
        "--statistics",
        action="store_true",
        help="Display per-rule violation counts aggregated across all tools",
    )
    parser.add_argument(
        "--format",
        choices=("table", "json"),
        default="table",
        help="Output format for --statistics (default: table)",
    )
    parser.add_argument(
        "--group",
        choices=("none", "rule", "tool", "file"),
        default="none",
        help="Group statistics output by tool, rule, or file (default: none)",
    )
    parser.add_argument(
        "--sort-by-rule",
        action="store_true",
        help="Sort statistics output by rule name instead of count",
    )
    parser.add_argument(
        "--package-name",
        metavar="PKG",
        help="Package name for mypy.stubtest + pyright verifytypes",
    )
    parser.add_argument(
        "--cwd",
        metavar="DIR",
        default=None,
        help="Working directory (default: current dir)",
    )
    parser.add_argument(
        "--tools",
        metavar="LIST",
        help="Comma-separated tool names to run (default: all 11 tools)",
    )
    parser.add_argument(
        "--default-py-dirs",
        metavar="DIRS",
        default="src,scripts,tests",
        help="Default dirs for pylint file discovery (default: src,scripts,tests)",
    )
    parser.add_argument(
        "--config",
        metavar="TOOL=PATH",
        action="append",
        default=[],
        help="Override config file for a tool (ruff, mypy, pylint, pyright, rumdl, ty). May be given multiple times.",
    )
    args = parser.parse_args(argv)

    # Start from caller-supplied defaults, allow CLI overrides.
    cwd = Path(args.cwd) if args.cwd else (config.cwd if config is not None else Path.cwd())
    cli_tools_override = args.tools.split(",") if args.tools else None
    base_tools_override = cli_tools_override if cli_tools_override is not None else (
        config.tools_override if config is not None else None
    )
    tools_override: list[str] | None = base_tools_override
    package_name = args.package_name if args.package_name is not None else (config.package_name if config is not None else None)
    default_py_dirs = (
        args.default_py_dirs.split(",") if args.default_py_dirs else (config.default_py_dirs if config is not None else None)
    )
    config_paths: dict[str, Path] = dict(config.config_paths) if config is not None else {}
    for raw in args.config:
        if "=" not in raw:
            parser.error(f"--config must be TOOL=PATH, got: {raw!r}")
        tool_id, path_str = raw.split("=", 1)
        # T8 fail-fast: validate tool_id against the closed config-key set.
        # Previously a typo silently produced an entry :func:`_config_flag_for`
        # never read; now exits ``SystemExit(2)`` naming the offending key.
        if tool_id not in _SUPPORTED_CONFIG_KEYS:
            parser.error(
                f"--config: unknown tool id {tool_id!r}; "
                f"supported (canonical labels + short aliases): "
                f"{sorted(_SUPPORTED_CONFIG_KEYS)}"
            )
        # Normalise short alias → canonical label.  ``args.config`` is
        # ``Namespace[Any]`` so ``tool_id`` is ``Any``; ``or tool_id`` coalesces
        # the widened ``dict.get(Any, Any) -> str | None`` to ``str``.
        canonical = _CONFIG_KEY_ALIASES.get(tool_id) or tool_id
        config_paths[canonical] = Path(path_str)

    # T8 fail-fast: ``--tools`` syntax (empty pieces, blank list) exits
    # ``SystemExit(2)`` here.  Unknown-but-non-empty names are deferred to
    # ``run_lint`` — the valid-name set is open (extras come from pyproject).
    if cli_tools_override is not None:
        if not cli_tools_override:
            parser.error("--tools: empty tool list")
        for raw_name in cli_tools_override:
            if not raw_name.strip():
                parser.error(f"--tools: empty name in {args.tools!r}")

    merged_config = RunnerConfig(
        cwd=cwd,
        package_name=package_name,
        default_py_dirs=default_py_dirs,
        tools_override=tools_override,
        config_paths=config_paths,
        secrets_baseline=config.secrets_baseline if config is not None else ".secrets.baseline",
    )

    return run_lint(
        config=merged_config,
        path=args.path,
        fix=args.fix,
        baseline=args.baseline,
        exclude=args.exclude,
        no_fail_fast=args.no_fail_fast,
        overwrite_baseline=args.overwrite_baseline,
        statistics=args.statistics,
        statistics_format=args.format,
        group=args.group,
        sort_by_rule=args.sort_by_rule,
    )

if __name__ == "__main__":
    sys.exit(main())
