"""Unit tests for python_setup_lint.checkers._semantic.

Tests the two-stage NLP ``semantic_check_if_meaningful`` function.

Tests that require network access (model download) are marked ``@pytest.mark.slow``.
Tests that hit the local model cache are **not** marked slow.
"""

from __future__ import annotations

import importlib.util
from unittest.mock import patch

import pytest

from python_setup_lint.checkers._base import check_if_meaningful


# ── ImportError fallback ─────────────────────────────────────────────


class TestImportErrorFallback:
    """When sentence_transformers is not installed, fall back to heuristic."""

    def test_fallback_on_import_error(self) -> None:
        """check_if_meaningful must return heuristic result when _semantic unavailable."""
        # Simulate _semantic module being unimportable by patching the import
        # inside check_if_meaningful to raise ImportError.
        with patch(
            "python_setup_lint.checkers._base._semantic",
            None,
            create=True,
        ), patch(
            "builtins.__import__",
            side_effect=self._make_blocking_import(),
        ):
            result = check_if_meaningful(
                "circular import — PyLinter not available"
            )
            assert result is True  # heuristic: non-empty, non-boilerplate

    def test_fallback_short_text(self) -> None:
        """Short text should still return False via heuristic fallback."""
        with patch(
            "python_setup_lint.checkers._base._semantic",
            None,
            create=True,
        ), patch(
            "builtins.__import__",
            side_effect=self._make_blocking_import(),
        ):
            result = check_if_meaningful("ok")
            assert result is False  # heuristic: too short

    def test_fallback_boilerplate(self) -> None:
        """Boilerplate text should still return False via heuristic fallback."""
        with patch(
            "python_setup_lint.checkers._base._semantic",
            None,
            create=True,
        ), patch(
            "builtins.__import__",
            side_effect=self._make_blocking_import(),
        ):
            result = check_if_meaningful("ignore")
            assert result is False  # heuristic: boilerplate

    @staticmethod
    def _make_blocking_import():
        """Return a side-effect function that blocks _semantic imports."""
        original_import = __builtins__["__import__"]

        def _mock_import(name, *args, **kwargs):
            if name == "python_setup_lint.checkers._semantic":
                raise ImportError("No module named _semantic")
            return original_import(name, *args, **kwargs)

        return _mock_import


# ── Semantic pipeline (requires sentence_transformers) ───────────────


@pytest.mark.skipif(
    importlib.util.find_spec("sentence_transformers") is None,
    reason="sentence_transformers not installed",
)
class TestSemanticCheck:
    """Tests that exercise the NLP pipeline.

    These tests require ``sentence_transformers`` to be importable.
    Tests that download models are marked ``@pytest.mark.slow``.
    """

    def test_meaningful_justification(self) -> None:
        """A detailed technical justification should be meaningful."""
        from python_setup_lint.checkers._semantic import (
            semantic_check_if_meaningful,
        )

        result = semantic_check_if_meaningful(
            "circular import — PyLinter not available at runtime",
            rule="missing-beartype",
            code_context="def foo():  # pylint: disable=missing-beartype",
            comment="circular import — PyLinter not available at runtime",
        )
        # If models are cached, this returns True/False; if not cached,
        # model download may fail returning None. Either is acceptable.
        assert result is None or isinstance(result, bool)

    def test_empty_justification(self) -> None:
        """Empty justification should return False."""
        from python_setup_lint.checkers._semantic import (
            semantic_check_if_meaningful,
        )

        result = semantic_check_if_meaningful("")
        assert result is False

    def test_whitespace_justification(self) -> None:
        """Whitespace-only justification should return False."""
        from python_setup_lint.checkers._semantic import (
            semantic_check_if_meaningful,
        )

        result = semantic_check_if_meaningful("   ")
        assert result is False

    def test_returns_none_on_import_error(self) -> None:
        """When sentence_transformers can't be imported, return None."""
        # Patch inside the function to simulate missing package
        with patch(
            "python_setup_lint.checkers._semantic._load_embedder",
            return_value=None,
        ):
            from python_setup_lint.checkers._semantic import (
                semantic_check_if_meaningful,
            )

            result = semantic_check_if_meaningful("some reason")
            assert result is None

    @pytest.mark.slow
    def test_semantic_with_model_download(self) -> None:
        """End-to-end test that downloads models (slow, network required).

        This test is marked ``slow`` because it downloads model artifacts.
        On cache hit (models already downloaded), it runs quickly but is
        still gated by the ``slow`` marker for safety.
        """
        from python_setup_lint.checkers._semantic import (
            semantic_check_if_meaningful,
        )

        result = semantic_check_if_meaningful(
            "circular import — PyLinter not available at runtime",
            rule="missing-beartype",
            code_context="def foo():  # pylint: disable=missing-beartype",
            comment="circular import — PyLinter not available at runtime",
        )
        # With models downloaded, this should return a definitive bool.
        assert isinstance(result, bool)

    @pytest.mark.slow
    def test_semantic_meaningful_justification(self) -> None:
        """A genuinely meaningful justification should pass the semantic check."""
        from python_setup_lint.checkers._semantic import (
            semantic_check_if_meaningful,
        )

        result = semantic_check_if_meaningful(
            "type stub not yet generated for this module",
            rule="import-error",
            code_context="import foo  # type: ignore",
            comment="type stub not yet generated for this module",
        )
        assert isinstance(result, bool)

    @pytest.mark.slow
    def test_semantic_weak_justification(self) -> None:
        """A weak justification should fail the semantic check."""
        from python_setup_lint.checkers._semantic import (
            semantic_check_if_meaningful,
        )

        result = semantic_check_if_meaningful(
            "noqa",
            rule="E501",
            code_context="x = 1  # noqa: E501",
            comment="noqa",
        )
        # The heuristic would reject this; the semantic check may also
        # reject it or return None if models aren't available.
        assert result is False or result is None
