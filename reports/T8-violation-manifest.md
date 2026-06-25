# T8 Violation Manifest (post-T1b/T5 regen)

## src/ violating files

- src/python_setup_lint/checkers/asyncio_timeout_checker.py  (pylint)
- src/python_setup_lint/checkers/beartype_checker.py  (pylint)
- src/python_setup_lint/checkers/no_try_import_checker.py  (pylint)
- src/python_setup_lint/checkers/stub_checker.py  (pylint, pyright check, ruff check, ty check)
- src/python_setup_lint/checkers/stub_coverage.py  (pylint)
- src/python_setup_lint/checkers/stub_docstring_checker.py  (pylint, ruff check)
- src/python_setup_lint/checkers/stub_fidelity/__init__.py  (pylint)
- src/python_setup_lint/checkers/stub_fidelity/_ast_helpers.py  (ruff check)
- src/python_setup_lint/checkers/stub_fidelity/annotation.py  (pyright check, ruff check, ty check)
- src/python_setup_lint/checkers/stub_fidelity/kind.py  (pylint)
- src/python_setup_lint/checkers/stub_fidelity/orchestrator.py  (pylint)
- src/python_setup_lint/checkers/stub_fidelity/signature.py  (pyright check, ruff check, ty check)
- src/python_setup_lint/checkers/stub_import_contract.py  (pylint, pyright check, ruff check, ty check)
- src/python_setup_lint/checkers/stub_normalizer.py  (mypy, pylint, pyright check, ty check)
- src/python_setup_lint/checkers/tmp_path_checker.py  (pylint)
- src/python_setup_lint/runner/__init__.py  (mypy, pylint, ruff check, ty check)
- src/python_setup_lint/runner/baseline.py  (pylint, ruff check)
- src/python_setup_lint/runner/cli.py  (pylint, pyright check, ruff check, ty check)
- src/python_setup_lint/runner/cli.pyi  (ruff check)
- src/python_setup_lint/runner/cmd_build.py  (pylint, ruff check)
- src/python_setup_lint/runner/cmd_build.pyi  (mypy)
- src/python_setup_lint/runner/dispatch.py  (pylint, pyright check, ruff check, ty check)
- src/python_setup_lint/runner/extra_tools.py  (pylint, ruff check, ty check)
- src/python_setup_lint/runner/output.py  (pylint, pyright check, ruff check, ty check)
- src/python_setup_lint/runner/parsers.py  (pylint, ruff check)
- src/python_setup_lint/runner/types.py  (ruff check)
- src/python_setup_lint/setup.py  (pylint, pyright check, ruff check, ty check)
- src/python_setup_lint/setup.pyi  (ruff check)
- src/python_setup_lint/testing.py  (pylint, ruff check)
- src/python_setup_lint/testing.pyi  (ruff check)

## tests/ violating files

- tests/checkers/_factories.py  (mypy, pylint)
- tests/checkers/test_asyncio_timeout_checker.py  (mypy, ruff check)
- tests/checkers/test_beartype_checker.py  (mypy, pylint, pyright check, ruff check)
- tests/checkers/test_no_try_import_checker.py  (mypy, pylint, pyright check, ruff check)
- tests/checkers/test_stub_checker.py  (mypy, pylint, pyright check, ruff check, ty check)
- tests/checkers/test_stub_checker_callable.py  (mypy, pylint, pyright check, ruff check, ty check)
- tests/checkers/test_stub_checker_class.py  (mypy, pylint, pyright check, ruff check, ty check)
- tests/checkers/test_stub_coverage.py  (mypy, pylint, pyright check, ruff check)
- tests/checkers/test_stub_docstring_checker.py  (mypy, pylint, pyright check, ruff check)
- tests/checkers/test_stub_fidelity_invariants.py  (mypy, pylint, pyright check, ruff check, ty check)
- tests/checkers/test_stub_normalizer.py  (mypy, pylint, pyright check, ruff check, ty check)
- tests/checkers/test_tmp_path_checker.py  (mypy, pylint, ruff check)
- tests/conftest.py  (pylint, pyright check, ruff check)
- tests/runner/_factories.py  (mypy, pylint, pyright check, ruff check, ty check)
- tests/runner/test_autofix_conflict.py  (pylint, pyright check, ruff check)
- tests/runner/test_baseline_diff.py  (mypy, pylint, pyright check, ruff check, ty check)
- tests/runner/test_bench_runner_overhead.py  (mypy, pylint, pyright check, ruff check, ty check)
- tests/runner/test_extra_tools.py  (mypy, pylint, pyright check, ruff check, ty check)
- tests/runner/test_lint_runner.py  (mypy, pylint, pyright check, ruff check, ty check)
- tests/runner/test_real_pipeline_smoke.py  (mypy, pylint, ruff check)
- tests/runner/test_setup.py  (mypy, pylint, pyright check, ruff check, ty check)
- tests/runner/test_t11_health_checks.py  (pylint, ruff check)
- tests/runner/test_t1b_self_discovery.py  (ruff check)
- tests/runner/test_t3_coverage.py  (mypy, pylint, pyright check, ruff check, ty check)
- tests/runner/test_t5_compose_ruff.py  (mypy, pylint, pyright check, ruff check, ty check)
- tests/runner/test_testing_fakes.py  (mypy, pylint, pyright check, ruff check, ty check)

## Per-tool summary

- mypy: 3 src files, 22 test files
- pylint: 22 src files, 24 test files
- pyright check: 9 src files, 20 test files
- ruff check: 20 src files, 25 test files
- ty check: 11 src files, 14 test files
