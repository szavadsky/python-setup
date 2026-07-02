"""Tests enforcing config consistency across pylintrc files (single source of truth)."""
from __future__ import annotations

import configparser
from pathlib import Path

import pytest

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
PYLINTRC = CONFIG_DIR / ".pylintrc"
PYLINTRC_TESTS = CONFIG_DIR / ".pylintrc-tests"
PYLINTRC_PYI = CONFIG_DIR / ".pylintrc-pyi"

ALL_RCFILES = [PYLINTRC, PYLINTRC_TESTS, PYLINTRC_PYI]


def _parse(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.read(path)
    return parser


# ── [DESIGN] — identical across all three ──────────────────────────────


class TestDesignSectionConsistency:
    """[DESIGN] must be byte-for-byte identical across all 3 rc files."""

    @staticmethod
    @pytest.fixture(params=ALL_RCFILES, ids=lambda p: p.name)
    def parsed(request: pytest.FixtureRequest) -> configparser.ConfigParser:
        return _parse(request.param)

    def test_design_section_present(self, parsed: configparser.ConfigParser) -> None:
        assert parsed.has_section("DESIGN")

    def test_design_identical_across_all(self) -> None:
        ref = _parse(PYLINTRC)
        for path in [PYLINTRC_TESTS, PYLINTRC_PYI]:
            other = _parse(path)
            assert ref.has_section("DESIGN")
            assert other.has_section("DESIGN")
            assert dict(ref["DESIGN"]) == dict(other["DESIGN"]), (
                f"[DESIGN] in {path.name} differs from .pylintrc"
            )


# ── [STUB-CHECKER] — .pylintrc and .pylintrc-pyi match ────────────────


class TestStubCheckerSectionConsistency:
    """[STUB-CHECKER] must match between .pylintrc and .pylintrc-pyi."""

    def test_stub_checker_present_in_main(self) -> None:
        assert _parse(PYLINTRC).has_section("STUB-CHECKER")

    def test_stub_checker_present_in_pyi(self) -> None:
        assert _parse(PYLINTRC_PYI).has_section("STUB-CHECKER")

    def test_stub_checker_identical(self) -> None:
        ref = _parse(PYLINTRC)
        other = _parse(PYLINTRC_PYI)
        assert dict(ref["STUB-CHECKER"]) == dict(other["STUB-CHECKER"])

    def test_stub_checker_not_in_tests(self) -> None:
        assert not _parse(PYLINTRC_TESTS).has_section("STUB-CHECKER")


# ── [SIMILARITIES] — pylintrc/tests=10, pyi=25 ─────────────────────────


class TestSimilaritiesSection:
    """min-similarity-lines values per expected configuration."""

    @staticmethod
    def _min_lines(path: Path) -> int:
        parser = _parse(path)
        return int(parser["SIMILARITIES"]["min-similarity-lines"])

    def test_main_similarity_default(self) -> None:
        assert self._min_lines(PYLINTRC) == 10

    def test_tests_similarity_matches_main(self) -> None:
        assert self._min_lines(PYLINTRC_TESTS) == 10

    def test_pyi_similarity_higher_for_stubs(self) -> None:
        assert self._min_lines(PYLINTRC_PYI) == 25