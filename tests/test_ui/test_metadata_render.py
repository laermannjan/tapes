"""Tests for diff_style and compact preview in metadata_render."""

from __future__ import annotations

from tapes.ui.metadata_render import (
    diff_style,
)

# --- diff_style ---


class TestDiffStyle:
    def test_matches_metadata(self) -> None:
        assert diff_style("Breaking Bad", "Breaking Bad") == "#888888"

    def test_matches_metadata_int_coerced(self) -> None:
        # str comparison: int metadata vs int candidate
        assert diff_style(2008, 2008) == "#888888"

    def test_differs_from_metadata(self) -> None:
        assert diff_style("Breaking Bad", "Better Call Saul") == "#E07A47"

    def test_differs_int_vs_different_int(self) -> None:
        assert diff_style(2008, 2010) == "#E07A47"

    def test_fills_empty_none_metadata(self) -> None:
        assert diff_style(None, "Breaking Bad") == "#86E89A"

    def test_fills_empty_string_metadata(self) -> None:
        assert diff_style("", "Breaking Bad") == "#86E89A"

    def test_missing_candidate(self) -> None:
        assert diff_style("Breaking Bad", None) == "#888888"

    def test_both_none(self) -> None:
        assert diff_style(None, None) == "#888888"

    def test_candidate_zero_fills_none_metadata(self) -> None:
        # 0 is a valid value, not None
        assert diff_style(None, 0) == "#86E89A"
