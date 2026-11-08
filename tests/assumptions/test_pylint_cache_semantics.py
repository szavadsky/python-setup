"""Pin the writer, timing, and ``--path`` scoping of the cache written during pylint runs.

Observed at HEAD with pylint 4.0.6 (pinned in ``pyproject.toml``).  The tracked
cache in this verdict is the semantic result cache consumed by
``epic-semantic-infrastructure`` -- not pylint's separate persistent
``~/.cache/pylint/*.stats`` bookkeeping.

WRITER-FIRST VERDICT (feeds ``cache-design-spike``)
===================================================
* **Writer identity** -- the checker call path writes the cache while pylint is
  linting: ``python_setup_lint.checkers._semantic.semantic_check_if_meaningful``
  calls ``_save_result_cache``.  The runner performs no post-process merge and
  checker ``open()``/``close()`` hooks do not write the file.
* **Timing** -- one whole-file rewrite per newly computed verdict (cache miss),
  synchronously before the check returns.  Cache hits and heuristic fallbacks
  (reranker unavailable) write nothing.
* **``--path`` scoping** -- the runner's ``--path`` narrows only the file
  arguments passed to each pylint invocation.  The cache is a single
  home-directory file and the key is SHA-256 over
  ``(text, rule, code_context, comment, model)``: no file path participates, so
  scoped and full runs share entries across the sequential ``pylint``,
  ``pylint-pyi`` and ``pylint tests`` invocations.
* **Sweep implication** -- because cache identity is path-free, ``--path``
  cannot partition the cache.  Prune/sweep scope must come from per-entry file
  references (the tracked schema's ``files`` field), not from the lint
  invocation's path argument.
* **Concurrency** -- the runner executes tools sequentially and none of the
  three pylint specs passes ``-j``/``--jobs``; pylint's default ``jobs`` is 1,
  so each run has a single writer.  No lockfile, runner-side merge, or sidecar
  files are required today.  If ``-j`` is introduced, pylint dispatches workers
  as separate processes, and the verdict flips to per-writer sidecars plus a
  runner merge (or a crash-safe lock plus atomic replace).
* **Crash safety** -- the writer is a non-atomic ``Path.write_text``.  A crash
  mid-write can lose entries but cannot break lint: unparsable JSON loads as an
  empty cache and is recomputed.

These tests *are* the verdict: when one fails, re-derive the writer-first
semantics before changing the assertion rather than loosening it.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
from pathlib import Path
from typing import Any, cast

import pytest
from pylint.lint import PyLinter

import python_setup_lint.checkers._semantic as semantic_module
from python_setup_lint.checkers._semantic import semantic_check_if_meaningful
from python_setup_lint.runner.dispatch import TOOLS, TOOLS_BY_NAME, _strategy_for
from python_setup_lint.runner.types import RunnerConfig

pytestmark = pytest.mark.no_external_api

_PYLINT_TOOL_NAMES = ("pylint", "pylint-pyi", "pylint tests")


class _FakeReranker:
    """Stand-in for the optional cross-encoder so cache writes are exercised offline."""

    def __init__(self, score: float) -> None:
        self.score = score
        self.calls = 0

    def predict(self, _pairs: list[tuple[str, str]]) -> list[float]:
        """Return a fixed score and count invocations."""
        self.calls += 1
        return [self.score]


def _expected_cache_key(text: str, *, rule: str, code_context: str, comment: str) -> int:
    """Compute the documented path-free cache key independently of the writer."""
    model = cast(Any, semantic_module)._RERANKER_MODEL
    payload = f"{text}|{rule}|{code_context}|{comment}|{model}"
    return int.from_bytes(hashlib.sha256(payload.encode()).digest()[:8], "big")


@pytest.fixture
def semantic_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Route the semantic result cache to a per-test directory."""
    cache_dir = tmp_path / "semantic"
    cache_file = cache_dir / "results.json"
    monkeypatch.setattr("python_setup_lint.checkers._semantic._CACHE_DIR", cache_dir)
    monkeypatch.setattr("python_setup_lint.checkers._semantic._RESULT_CACHE_FILE", cache_file)
    monkeypatch.setattr("python_setup_lint.checkers._semantic._RESULT_CACHE", None)
    return cache_file


class TestSemanticCacheWriter:
    """Writer identity and timing of the cache produced inside a pylint run."""

    def test_semantic_check_if_meaningful_given_new_verdicts_then_writes_each_miss_immediately(
        self, semantic_cache: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OBSERVED: the in-process check call is the writer; each miss rewrites the file."""
        reranker = _FakeReranker(score=0.9)
        monkeypatch.setattr("python_setup_lint.checkers._semantic._load_reranker", lambda: reranker)

        assert not semantic_cache.exists()

        assert (
            semantic_check_if_meaningful(
                "guarded by a lock",
                rule="W9704",
                code_context="lock = Lock()",
                comment="guarded by a lock",
            )
            is True
        )
        first_payload = json.loads(semantic_cache.read_text())
        assert list(first_payload.values()) == [True]

        assert (
            semantic_check_if_meaningful(
                "retry is idempotent",
                rule="W9704",
                code_context="retry()",
                comment="retry is idempotent",
            )
            is True
        )
        second_payload = json.loads(semantic_cache.read_text())
        assert len(second_payload) == 2
        assert first_payload.keys() <= second_payload.keys()
        assert set(second_payload.values()) == {True}
        assert reranker.calls == 2

        # In-memory hit: no reranker call and no extra file rewrite.
        assert (
            semantic_check_if_meaningful(
                "guarded by a lock",
                rule="W9704",
                code_context="lock = Lock()",
                comment="guarded by a lock",
            )
            is True
        )
        assert reranker.calls == 2
        assert json.loads(semantic_cache.read_text()) == second_payload

    def test_semantic_check_if_meaningful_given_persisted_entry_then_serves_it_without_model_or_write(
        self, semantic_cache: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OBSERVED: the cache is lazy-loaded from disk; a hit reaches neither writer nor model."""
        text, rule, code_context, comment = (
            "persisted verdict",
            "W9704",
            "guard()",
            "persisted verdict",
        )
        key = _expected_cache_key(text, rule=rule, code_context=code_context, comment=comment)
        semantic_cache.parent.mkdir(parents=True)
        semantic_cache.write_text(json.dumps({str(key): False}))
        persisted = semantic_cache.read_text()

        def _unexpected_load() -> None:
            raise AssertionError("cache hit must not load the reranker")

        def _unexpected_write() -> None:
            raise AssertionError("cache hit must not rewrite the result cache")

        monkeypatch.setattr("python_setup_lint.checkers._semantic._load_reranker", _unexpected_load)
        monkeypatch.setattr("python_setup_lint.checkers._semantic._save_result_cache", _unexpected_write)

        assert semantic_check_if_meaningful(text, rule=rule, code_context=code_context, comment=comment) is False
        assert semantic_cache.read_text() == persisted

    def test_semantic_check_if_meaningful_given_reranker_unavailable_then_writes_no_entry(
        self, semantic_cache: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OBSERVED: the heuristic fallback path (None) creates neither cache file nor directory."""
        monkeypatch.setattr("python_setup_lint.checkers._semantic._load_reranker", lambda: None)

        assert semantic_check_if_meaningful("checked elsewhere", rule="W9704", code_context="x = 1") is None
        assert not semantic_cache.exists()
        assert not semantic_cache.parent.exists()

    def test_semantic_check_if_meaningful_given_truncated_cache_file_then_recovers_with_new_entry(
        self, semantic_cache: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OBSERVED: a crash-truncated file loads as empty and is replaced by a valid rewrite."""
        semantic_cache.parent.mkdir(parents=True)
        semantic_cache.write_text('{"truncated": tru')
        reranker = _FakeReranker(score=0.9)
        monkeypatch.setattr("python_setup_lint.checkers._semantic._load_reranker", lambda: reranker)

        assert (
            semantic_check_if_meaningful(
                "crash tolerant",
                rule="W9704",
                code_context="cache = load()",
                comment="crash tolerant",
            )
            is True
        )
        payload = json.loads(semantic_cache.read_text())
        assert payload == {
            str(
                _expected_cache_key(
                    "crash tolerant",
                    rule="W9704",
                    code_context="cache = load()",
                    comment="crash tolerant",
                )
            ): True
        }

    def test_semantic_result_cache_given_single_writer_then_leaves_no_lock_or_sidecar_artifacts(
        self, semantic_cache: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OBSERVED: sequential writes leave exactly ``results.json`` -- no lock or sidecar files."""
        monkeypatch.setattr(
            "python_setup_lint.checkers._semantic._load_reranker",
            lambda: _FakeReranker(0.9),
        )

        assert semantic_check_if_meaningful("only writer", rule="W9704", code_context="x = 1", comment="only writer") is True
        assert [entry.name for entry in sorted(semantic_cache.parent.iterdir())] == ["results.json"]


class TestSemanticCachePathScoping:
    """The cache is a single path-free store shared by every pylint invocation."""

    def test_semantic_check_if_meaningful_given_identical_inputs_then_cache_key_ignores_source_path(
        self, semantic_cache: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OBSERVED: key = SHA-256(text, rule, context, comment, model); the API takes no path."""
        monkeypatch.setattr(
            "python_setup_lint.checkers._semantic._load_reranker",
            lambda: _FakeReranker(0.9),
        )
        text, rule, code_context, comment = (
            "path free key",
            "W9704",
            "value = load()",
            "path free key",
        )

        assert semantic_check_if_meaningful(text, rule=rule, code_context=code_context, comment=comment) is True
        expected = _expected_cache_key(text, rule=rule, code_context=code_context, comment=comment)
        assert json.loads(semantic_cache.read_text()) == {str(expected): True}

        signature = inspect.signature(semantic_check_if_meaningful)
        assert set(signature.parameters).isdisjoint({"path", "file", "filename"})

    def test_semantic_result_cache_file_given_runner_invocations_then_single_home_location(
        self,
    ) -> None:
        """OBSERVED: one process-independent cache file, not a per-path or per-cwd cache."""
        module = cast(Any, semantic_module)
        expected_dir = Path.home() / ".cache" / "python-setup" / "semantic"
        assert expected_dir == module._CACHE_DIR
        assert (expected_dir / "results.json") == module._RESULT_CACHE_FILE

    def test_runner_pylint_commands_given_path_scope_then_scope_file_targets_only(self, tmp_path: Path) -> None:
        """OBSERVED: --path narrows lint targets; default runs keep each tool's own scope."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("APP = 1\n")
        (tmp_path / "src" / "app.pyi").write_text("APP: int\n")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_app.py").write_text("def test_app() -> None: ...\n")
        config = RunnerConfig(cwd=tmp_path)

        scoped_targets = {
            "pylint": "src/app.py",
            "pylint-pyi": "src/app.pyi",
            "pylint tests": "src/app.py",
        }
        for tool_name, expected_target in scoped_targets.items():
            command = _strategy_for(tool_name, TOOLS_BY_NAME[tool_name]).build_command(config=config, _path="src")
            assert expected_target in command
            assert "tests/test_app.py" not in command

        default_targets = {
            "pylint": "src/app.py",
            "pylint-pyi": "src/app.pyi",
            "pylint tests": "tests/test_app.py",
        }
        for tool_name, expected_target in default_targets.items():
            command = _strategy_for(tool_name, TOOLS_BY_NAME[tool_name]).build_command(config=config)
            assert expected_target in command

    def test_semantic_cache_writer_given_source_tree_then_only_check_call_path_writes(
        self,
    ) -> None:
        """OBSERVED: `_save_result_cache` has one caller; runner code never performs a merge."""
        source = Path(semantic_module.__file__).read_text()
        tree = ast.parse(source)
        save_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_save_result_cache"
        ]
        assert len(save_calls) == 1
        callers = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and any(
                isinstance(call, ast.Call) and getattr(call.func, "id", None) == "_save_result_cache" for call in ast.walk(node)
            )
        ]
        assert callers == ["semantic_check_if_meaningful"]

        runner_dir = Path(semantic_module.__file__).parent.parent / "runner"
        assert not [
            path.name
            for path in runner_dir.rglob("*.py")
            if "_save_result_cache" in path.read_text() or "_RESULT_CACHE_FILE" in path.read_text()
        ]

        checkers_dir = Path(semantic_module.__file__).parent
        assert not [
            path.name
            for path in checkers_dir.rglob("*.py")
            if path.name != Path(semantic_module.__file__).name
            and ("_save_result_cache" in path.read_text() or "_RESULT_CACHE_FILE" in path.read_text())
        ]


class TestPylintInvocationConcurrency:
    """Single-writer assumptions on the pylint invocations that produce cache entries."""

    @pytest.mark.parametrize("tool_name", _PYLINT_TOOL_NAMES)
    def test_runner_pylint_command_given_default_runner_config_then_passes_no_jobs_flag(
        self, tool_name: str, tmp_path: Path
    ) -> None:
        """OBSERVED: the runner keeps every pylint invocation single-process."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("APP = 1\n")
        config = RunnerConfig(cwd=tmp_path)

        spec = TOOLS_BY_NAME[tool_name]
        assert spec.command == ["pylint"]
        command = _strategy_for(tool_name, spec).build_command(config=config)
        assert "-j" not in command
        assert "--jobs" not in command
        assert not any(argument.startswith("--jobs=") for argument in command)

    def test_runner_pylint_tools_given_registry_order_then_three_sequential_specs_share_executable(
        self,
    ) -> None:
        """OBSERVED: pylint, pylint-pyi and pylint tests are separate sequential invocations."""
        pylint_tools = [spec for spec in TOOLS if spec.command == ["pylint"]]
        assert [spec.name for spec in pylint_tools] == list(_PYLINT_TOOL_NAMES)
        assert all(spec.supports_path for spec in pylint_tools)

    def test_pylint_linter_given_default_options_then_jobs_equals_one(self) -> None:
        """OBSERVED at pylint 4.0.6: the default run has no worker pool."""
        assert PyLinter().config.jobs == 1

    def test_pylint_linter_given_jobs_over_one_then_dispatches_parallel_check(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OBSERVED: ``-j > 1`` hands lints to ``check_parallel`` (separate process writers)."""
        source = tmp_path / "sample.py"
        source.write_text("VALUE = 1\n")
        dispatched: list[int] = []

        def _record_parallel(
            _linter: PyLinter,
            jobs: int,
            _files: object,
            _extra_packages_paths: object = None,
        ) -> None:
            dispatched.append(jobs)

        monkeypatch.setattr("pylint.lint.pylinter.check_parallel", _record_parallel)
        linter = PyLinter()
        linter.set_option("jobs", 2)
        linter.check([str(source)])

        assert dispatched == [2]
