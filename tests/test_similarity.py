"""Tests for tapes.similarity module."""
from __future__ import annotations

import pytest

from tapes.similarity import (
    DEFAULT_AUTO_ACCEPT_THRESHOLD,
    compute_confidence,
    title_similarity,
)


class TestTitleSimilarity:
    def test_exact_match(self) -> None:
        assert title_similarity("Dune", "Dune") == 1.0

    def test_case_insensitive(self) -> None:
        assert title_similarity("dune", "DUNE") == 1.0

    def test_no_overlap(self) -> None:
        assert title_similarity("Dune", "Arrival") == 0.0

    def test_partial_overlap(self) -> None:
        # "The Dark Knight" vs "Dark Knight Rises" -> intersection {dark, knight} / union {the, dark, knight, rises}
        score = title_similarity("The Dark Knight", "Dark Knight Rises")
        assert score == pytest.approx(2.0 / 4.0)

    def test_subset(self) -> None:
        # "Dune" vs "Dune Part Two" -> intersection {dune} / union {dune, part, two}
        score = title_similarity("Dune", "Dune Part Two")
        assert score == pytest.approx(1.0 / 3.0)

    def test_extra_words_reduce_score(self) -> None:
        exact = title_similarity("Dune", "Dune")
        partial = title_similarity("Dune", "Dune Part Two")
        assert exact > partial

    def test_empty_string_a(self) -> None:
        assert title_similarity("", "Dune") == 0.0

    def test_empty_string_b(self) -> None:
        assert title_similarity("Dune", "") == 0.0

    def test_both_empty(self) -> None:
        assert title_similarity("", "") == 0.0

    def test_multi_word_exact(self) -> None:
        assert title_similarity("Breaking Bad", "Breaking Bad") == 1.0

    def test_single_common_word(self) -> None:
        # "The Matrix" vs "The Godfather" -> {the} / {the, matrix, godfather}
        score = title_similarity("The Matrix", "The Godfather")
        assert score == pytest.approx(1.0 / 3.0)


class TestComputeConfidence:
    def test_exact_title_and_year(self) -> None:
        score = compute_confidence(
            {"title": "Dune", "year": 2021},
            {"title": "Dune", "year": 2021},
        )
        assert score == pytest.approx(1.0)

    def test_title_match_year_off_by_one(self) -> None:
        score = compute_confidence(
            {"title": "Dune", "year": 2021},
            {"title": "Dune", "year": 2020},
        )
        # 0.7 * 1.0 + 0.3 * 0.5 = 0.85
        assert score == pytest.approx(0.85)

    def test_title_match_year_mismatch(self) -> None:
        score = compute_confidence(
            {"title": "Dune", "year": 2021},
            {"title": "Dune", "year": 1984},
        )
        # 0.7 * 1.0 + 0.3 * 0.0 = 0.7
        assert score == pytest.approx(0.7)

    def test_title_match_no_year_in_query(self) -> None:
        score = compute_confidence(
            {"title": "Dune"},
            {"title": "Dune", "year": 2021},
        )
        # No year in query -> title only = 1.0
        assert score == pytest.approx(1.0)

    def test_title_match_no_year_in_result(self) -> None:
        score = compute_confidence(
            {"title": "Dune", "year": 2021},
            {"title": "Dune"},
        )
        # No year in result -> title only = 1.0
        assert score == pytest.approx(1.0)

    def test_no_title_in_query(self) -> None:
        score = compute_confidence(
            {"year": 2021},
            {"title": "Dune", "year": 2021},
        )
        assert score == 0.0

    def test_no_title_in_result(self) -> None:
        score = compute_confidence(
            {"title": "Dune", "year": 2021},
            {"year": 2021},
        )
        assert score == 0.0

    def test_both_empty_dicts(self) -> None:
        assert compute_confidence({}, {}) == 0.0

    def test_none_title_in_query(self) -> None:
        assert compute_confidence({"title": None}, {"title": "Dune"}) == 0.0

    def test_none_title_in_result(self) -> None:
        assert compute_confidence({"title": "Dune"}, {"title": None}) == 0.0

    def test_partial_title_with_year(self) -> None:
        score = compute_confidence(
            {"title": "Dark Knight", "year": 2008},
            {"title": "The Dark Knight", "year": 2008},
        )
        # title: {dark, knight} / {the, dark, knight} = 2/3
        # year: exact = 1.0
        # 0.7 * (2/3) + 0.3 * 1.0 = 0.7666...
        assert score == pytest.approx(0.7 * (2.0 / 3.0) + 0.3)

    def test_no_overlap_title(self) -> None:
        score = compute_confidence(
            {"title": "Dune", "year": 2021},
            {"title": "Arrival", "year": 2021},
        )
        # title: 0.0, year: 1.0 -> 0.7 * 0 + 0.3 * 1.0 = 0.3
        assert score == pytest.approx(0.3)


class TestDefaultThreshold:
    def test_threshold_value(self) -> None:
        assert DEFAULT_AUTO_ACCEPT_THRESHOLD == 0.85
