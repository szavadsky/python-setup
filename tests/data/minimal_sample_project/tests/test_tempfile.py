"""Test file with planted tempfile violation for integration testing."""

from __future__ import annotations

import tempfile


def test_create_temp_dir() -> None:
    """Test that creates a temp dir (should trigger tempfile-mkdtemp-in-test)."""
    d = tempfile.mkdtemp()  # should trigger tempfile-mkdtemp-in-test
    assert d
