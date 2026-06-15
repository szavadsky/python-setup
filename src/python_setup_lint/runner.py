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
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

class ToolSpec(NamedTuple):
    """Specification for a single lint tool.

    Attributes:
        name: Human-readable label for the tool.
        command: Base command list (no paths, no flag overrides).
        supports_fix: Whether the tool accepts ``--fix``.
        supports_path: Whether the tool accepts a positional path.
        supports_exclude: Whether the tool accepts ``--exclude`` / ``-e``.
        default_paths: Paths to use when no ``--path`` is given.
    """

    name: str
    command: list[str]
    supports_fix: bool = False
    supports_path: bool = False
    supports_exclude: bool = False
    default_paths: list[str] = []

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
            :class:`ToolSpec` entries via ``TOOLS_BY_NAME``.
        secrets_baseline: Path (relative to ``cwd``) to the
            detect-secrets baseline file.
        config_paths: Optional mapping of tool identifiers to config file
            paths.  Supported keys: ``ruff``, ``mypy``, ``pylint``,
            ``pyright``, ``rumdl``, ``ty``.

            * ``ruff``: ``--config <path>``
            * ``mypy``: ``--config-file <path>``
            * ``pylint``: ``--rcfile <path>``
            * ``pyright``: ``--project <path>``
            * ``rumdl``: ``--config <path>``
            * ``ty``: ``--config <path>``
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
    ToolSpec("tach check", ["tach", "check"], supports_exclude=True),
    ToolSpec(
        "ruff check",
        ["ruff", "check"],
        supports_fix=True,
        supports_path=True,
        supports_exclude=True,
        default_paths=["src/", "tests/"],
    ),
    ToolSpec(
        "rumdl check",
        ["rumdl", "check"],
        supports_fix=True,
        supports_path=True,
        supports_exclude=True,
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
) -> list[str]:

## Build the full command list for a tool spec given runtime flags

    cwd = config.cwd
    cmd = list(spec.command)
    config_paths = config.config_paths or {}

    # ── Runtime-constructed commands ───────────────────────────
    if spec.name == "mypy.stubtest" and config.package_name is not None:
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
    elif spec.name == "pyright verify types" and config.package_name is not None:
        pyright_config = config_paths.get("pyright check")
        cmd.extend([config.package_name, "--ignoreexternal", "--outputjson"])
        if pyright_config is not None:
            cmd.extend(["--project", str(pyright_config)])
    elif spec.name == "detect-secrets":
        cmd = ["bash", "-c", f"git ls-files -z | xargs -0 detect-secrets-hook --baseline {config.secrets_baseline}"]

    # ── Shared config files ───────────────────────────────────
    cmd.extend(_config_flag_for(spec.name, config_paths.get(spec.name)))

    # ── Fix flags ──────────────────────────────────────────────
    if fix and spec.supports_fix:
        if spec.name == "ruff check":
            cmd.extend(["--fix", "--exit-non-zero-on-fix"])
        elif spec.name in ("rumdl check", "ty check"):
            cmd.append("--fix")

    # ── Path scoping ───────────────────────────────────────────
    paths: list[str] = []
    if path is not None and spec.supports_path:
        paths = [path]
    elif spec.default_paths:
        paths = list(spec.default_paths)

    # Expand path to .py file list for pylint (it expects file args)
    if spec.name == "pylint":
        paths = _find_py_files([path], cwd=cwd) if path is not None else _find_py_files(config.default_py_dirs, cwd=cwd)

    # Expand globs (e.g. config/*.yaml)
    paths = _expand_globs(paths, cwd=cwd)

    if paths:
        cmd.extend(paths)

    # ── Exclude flags ──────────────────────────────────────────
    if exclude is not None and spec.supports_exclude:
        if spec.name == "tach check":
            cmd.extend(["-e", exclude])
        else:
            cmd.extend(["--exclude", exclude])

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

## ── Statistics aggregation and display ────────────────────────────

def _aggregate_statistics(results: list[LintResult]) -> list[ViolationCount]:

## Aggregate violation counts per tool per rule from all tool results

## Returns a list sorted by count descending, then tool, then rule

## Only tools with a registered parser are included

    counts: list[ViolationCount] = []
    for result in results:
        parser = _STATISTICS_PARSERS.get(result.tool_name)
        if parser is None:
            continue
        try:
            violations = parser(result.stdout, result.stderr)
        except Exception:
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
        else:
            entry["output"] = r.stdout
        baseline.append(entry)
    return baseline

def _diff_baseline(
    current: list[LintResult],
    baseline_path: Path,
) -> list[str]:

## Compare current results against saved baseline

## Returns a list of human-readable violation descriptions for any

    # new or changed issues.
    if not baseline_path.exists():
        return [f"Baseline file not found: {baseline_path}"]

    try:
        with open(baseline_path) as f:
            raw: list[dict[str, Any]] = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        return [f"Cannot read baseline: {exc}"]
    # cast after JSON load so mypy sees concrete types
    saved: list[dict[str, Any]] = raw

    # Normalise saved diagnostics: strip volatile fields (timeInSec) that
    # change between runs so baseline comparison is stable.
    for entry in saved:
        saved_diag = entry.get("diagnostics")
        if isinstance(saved_diag, dict):
            saved_summary = saved_diag.get("summary")
            if isinstance(saved_summary, dict):
                saved_summary.pop("timeInSec", None)

    violations: list[str] = []
    saved_map: dict[str, dict[str, Any]] = {}
    for entry in saved:
        tool_name = entry.get("tool", "")
        if isinstance(tool_name, str):
            saved_map[tool_name] = entry
    for r in current:
        saved_entry = saved_map.get(r.tool_name)
        if saved_entry is None:
            violations.append(f"[{r.tool_name}] New tool result — no baseline entry")
            continue
        if r.exit_code != saved_entry.get("exit_code", -1):
            violations.append(f"[{r.tool_name}] Exit code changed: {saved_entry['exit_code']} → {r.exit_code}")
        # Prefer parsed diagnostics over raw output for stable diffing
        saved_diag = saved_entry.get("diagnostics")
        if saved_diag is not None:
            try:
                current_diag = json.loads(r.stdout) if r.stdout else None
            except (json.JSONDecodeError, ValueError):
                current_diag = None
            if isinstance(current_diag, dict):
                current_diag.pop("time", None)
                current_diag.pop("version", None)
                current_summary = current_diag.get("summary")
                if isinstance(current_summary, dict):
                    current_summary.pop("timeInSec", None)
            if current_diag != saved_diag:
                violations.append(f"[{r.tool_name}] Diagnostics changed (new/different violations)")
        # Rumdl timing changes per run — strip before comparing
        elif r.tool_name == "rumdl check":
            import re as _re

            saved_output = _re.sub(r"\(\d+ms\)", "(XXXms)", saved_entry.get("output") or "")
            current_output = _re.sub(r"\(\d+ms\)", "(XXXms)", r.stdout or "")
            if current_output != saved_output:
                violations.append(f"[{r.tool_name}] Output changed (new/different violations)")
        else:
            saved_output = saved_entry.get("output") or ""
            if r.stdout != saved_output:
                violations.append(f"[{r.tool_name}] Output changed (new/different violations)")
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
) -> int:

## Run the full lint pipeline

## Returns 0 if all tools pass, non-zero on any failure

    if config is None:
        config = RunnerConfig(cwd=Path.cwd())

    # Resolve which tools to run
    if config.tools_override is not None:
        selected: list[ToolSpec] = []
        for name in config.tools_override:
            spec = TOOLS_BY_NAME.get(name.strip())
            if spec is not None:
                selected.append(spec)
    else:
        selected = list(TOOLS)

    results: list[LintResult] = []
    overall_rc = 0
    cwd = config.cwd

    for spec in selected:
        # Skip tools that require package_name when none configured
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

        cmd = _build_command(spec, config=config, fix=fix, path=path, exclude=exclude)
        if statistics:
            cmd.extend(_build_statistics_flags(spec))
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
        else:
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
    tools_override = args.tools.split(",") if args.tools else (config.tools_override if config is not None else None)
    package_name = args.package_name if args.package_name is not None else (config.package_name if config is not None else None)
    default_py_dirs = (
        args.default_py_dirs.split(",") if args.default_py_dirs else (config.default_py_dirs if config is not None else None)
    )
    config_paths: dict[str, Path] = dict(config.config_paths) if config is not None else {}
    for raw in args.config:
        if "=" not in raw:
            parser.error(f"--config must be TOOL=PATH, got: {raw}")
        tool_id, path_str = raw.split("=", 1)
        config_paths[tool_id] = Path(path_str)

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
    )

if __name__ == "__main__":
    sys.exit(main())
