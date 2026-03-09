"""Tests for diff_style, confidence_style, and compact preview in metadata_render."""

from __future__ import annotations

from tapes.ui.metadata_render import (
    confidence_style,
    diff_style,
)

# --- diff_style ---


class TestDiffStyle:
    def test_matches_result(self) -> None:
        assert diff_style("Breaking Bad", "Breaking Bad") == "#888888"

    def test_matches_result_int_coerced(self) -> None:
        # str comparison: int result vs int source
        assert diff_style(2008, 2008) == "#888888"

    def test_differs_from_result(self) -> None:
        assert diff_style("Breaking Bad", "Better Call Saul") == "#E07A47"

    def test_differs_int_vs_different_int(self) -> None:
        assert diff_style(2008, 2010) == "#E07A47"

    def test_fills_empty_none_result(self) -> None:
        assert diff_style(None, "Breaking Bad") == "#86E89A"

    def test_fills_empty_string_result(self) -> None:
        assert diff_style("", "Breaking Bad") == "#86E89A"

    def test_missing_source(self) -> None:
        assert diff_style("Breaking Bad", None) == "#888888"

    def test_both_none(self) -> None:
        assert diff_style(None, None) == "#888888"

    def test_source_zero_fills_none_result(self) -> None:
        # 0 is a valid value, not None
        assert diff_style(None, 0) == "#86E89A"


# --- confidence_style ---


class TestConfidenceStyle:
    def test_high_confidence_muted(self) -> None:
        assert confidence_style(0.95) == "#888888"

    def test_boundary_80_muted(self) -> None:
        assert confidence_style(0.8) == "#888888"

    def test_medium_confidence_yellow(self) -> None:
        assert confidence_style(0.65) == "#E07A47"

    def test_boundary_50_yellow(self) -> None:
        assert confidence_style(0.5) == "#E07A47"

    def test_low_confidence_red(self) -> None:
        assert confidence_style(0.3) == "#FF7A7A"

    def test_zero_confidence_red(self) -> None:
        assert confidence_style(0.0) == "#FF7A7A"

    def test_boundary_just_below_80_yellow(self) -> None:
        assert confidence_style(0.79) == "#E07A47"

    def test_boundary_just_below_50_red(self) -> None:
        assert confidence_style(0.49) == "#FF7A7A"
