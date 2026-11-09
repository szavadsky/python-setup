from __future__ import annotations

from .types import ToolSpec

__all__ = ["TOOLS", "TOOLS_BY_NAME"]

# ── Tool definitions ────────────────────────────────────────────────

TOOLS: list[ToolSpec] = [
    ToolSpec("tach check", ["tach", "check"], supports_exclude=True, exclude_flag="-e"),
    ToolSpec(
        "ruff format",
        ["ruff", "format"],
        supports_fix=False,
        supports_path=True,
        supports_exclude=True,
        default_paths=["src/", "tests/"],
    ),
    ToolSpec(
        "ruff check",
        ["ruff", "check", "--output-format", "concise"],
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
        default_paths=["."],
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
        default_paths=["."],
    ),
    ToolSpec(
        "ty check",
        ["ty", "check"],
        supports_fix=True,
        supports_path=True,
        supports_exclude=True,
        fix_flags=("--fix",),
        memory_limit_mb=0,  # 0 disables RLIMIT_AS for ty: Rust runtime reserves ~2.5GB+ virtual address space (thread stacks, mmap arenas) though peak RSS is ~124MB; RLIMIT_AS caps virtual address space, not physical RAM, so the default 2048 MB would crash the Rust binary on startup
        default_paths=[
            "src"
        ],  # ty scoped to src/ only: ty honors its own ignore-comment syntax (not mypy's `# type: ignore[code]`), so 67 existing `# type: ignore[mypy-code]` test suppressions are invisible to ty, producing 38 false positives on test-fixture patterns (monkeypatch, dict-invariance, isinstance-narrowing) that mypy + pyright both certify clean; tests are already type-checked by those 2 independent tools; re-enabling ty on tests would require ~38 duplicate ty-specific ignore comments for zero marginal type-safety gain. (pylint-pyi at line 105 also has default_paths=["src"]—that's a stylistic stub-linter scope, not a type-checker restriction.)  # pylint: disable=unjustified-suppression
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
        "pylint-pyi",
        ["pylint"],
        supports_fix=False,
        supports_path=True,
        supports_exclude=False,
        default_paths=["src"],
    ),
    ToolSpec(
        "pylint tests",
        ["pylint"],
        supports_fix=False,
        supports_path=True,
        supports_exclude=False,
        default_paths=["tests"],
    ),
    ToolSpec(
        "detect-secrets",
        ["detect-secrets-hook"],
    ),
]

TOOLS_BY_NAME: dict[str, ToolSpec] = {t.name: t for t in TOOLS}
