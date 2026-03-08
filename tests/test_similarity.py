"""Tests for tapes.similarity module."""
from __future__ import annotations

import pytest

from tapes.config import DEFAULT_AUTO_ACCEPT_THRESHOLD
from tapes.similarity import (
    _string_similarity,
    compute_confidence,
    compute_episode_confidence,
)


class TestStringSimilarity:
    def test_exact_match(self) -> None:
        assert _string_similarity("Dune", "Dune") == pytest.approx(1.0)

    def test_case_insensitive(self) -> None:
        assert _string_similarity("dune", "DUNE") == pytest.approx(1.0)

    def test_empty_a(self) -> None:
        assert _string_similarity("", "Dune") == 0.0

    def test_empty_b(self) -> None:
        assert _string_similarity("Dune", "") == 0.0

    def test_both_empty(self) -> None:
        assert _string_similarity("", "") == 0.0

    def test_multi_word_exact(self) -> None:
        assert _string_similarity("Breaking Bad", "Breaking Bad") == pytest.approx(1.0)

    def test_article_difference_scores_high(self) -> None:
        score = _string_similarity("The Dark Knight", "Dark Knight")
        assert score > 0.8

    def test_subset_scores_high(self) -> None:
        score = _string_similarity("Dune", "Dune Part Two")
        assert score > 0.6

    def test_no_overlap_scores_low(self) -> None:
        score = _string_similarity("Dune", "Arrival")
        assert score < 0.5

    def test_word_order_irrelevant(self) -> None:
        score = _string_similarity("Batman v Superman", "Superman v Batman")
        assert score > 0.9

    def test_exact_beats_partial(self) -> None:
        exact = _string_similarity("Dune", "Dune")
        partial = _string_similarity("Dune", "Dune Part Two")
        assert exact > partial


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

    def test_no_year_in_query_penalized(self) -> None:
        score = compute_confidence(
            {"title": "Dune"},
            {"title": "Dune", "year": 2021},
        )
        # NULL year scores 0.0: 0.7 * 1.0 + 0.3 * 0.0 = 0.7
        assert score == pytest.approx(0.7)

    def test_no_year_in_result_penalized(self) -> None:
        score = compute_confidence(
            {"title": "Dune", "year": 2021},
            {"title": "Dune"},
        )
        assert score == pytest.approx(0.7)

    def test_no_year_below_auto_accept(self) -> None:
        """Missing year must keep score below auto-accept threshold."""
        score = compute_confidence(
            {"title": "Dune"},
            {"title": "Dune"},
        )
        assert score < DEFAULT_AUTO_ACCEPT_THRESHOLD

    def test_no_title_in_query(self) -> None:
        assert compute_confidence({"year": 2021}, {"title": "Dune", "year": 2021}) == 0.0

    def test_no_title_in_result(self) -> None:
        assert compute_confidence({"title": "Dune", "year": 2021}, {"year": 2021}) == 0.0

    def test_both_empty_dicts(self) -> None:
        assert compute_confidence({}, {}) == 0.0

    def test_none_title_in_query(self) -> None:
        assert compute_confidence({"title": None}, {"title": "Dune"}) == 0.0

    def test_none_title_in_result(self) -> None:
        assert compute_confidence({"title": "Dune"}, {"title": None}) == 0.0

    def test_article_difference_with_year(self) -> None:
        score = compute_confidence(
            {"title": "Dark Knight", "year": 2008},
            {"title": "The Dark Knight", "year": 2008},
        )
        # rapidfuzz handles articles well; score should auto-accept
        assert score > DEFAULT_AUTO_ACCEPT_THRESHOLD

    def test_no_overlap_title_same_year(self) -> None:
        score = compute_confidence(
            {"title": "Dune", "year": 2021},
            {"title": "Arrival", "year": 2021},
        )
        # Low title similarity + year match
        assert score < 0.7

    def test_tmdb_id_match_overrides(self) -> None:
        score = compute_confidence(
            {"title": "Wrong", "year": 1900, "tmdb_id": 12345},
            {"title": "Different", "year": 2024, "tmdb_id": 12345},
        )
        assert score == 1.0

    def test_tmdb_id_mismatch_scores_normally(self) -> None:
        score = compute_confidence(
            {"title": "Dune", "year": 2021, "tmdb_id": 111},
            {"title": "Dune", "year": 2021, "tmdb_id": 222},
        )
        # Different IDs, fall through to normal scoring
        assert score == pytest.approx(1.0)

    def test_tmdb_id_only_in_query_no_override(self) -> None:
        score = compute_confidence(
            {"title": "Dune", "year": 2021, "tmdb_id": 12345},
            {"title": "Dune", "year": 2021},
        )
        # tmdb_id absent from result, score normally
        assert score == pytest.approx(1.0)

    def test_tmdb_id_only_in_result_no_override(self) -> None:
        score = compute_confidence(
            {"title": "Dune", "year": 2021},
            {"title": "Dune", "year": 2021, "tmdb_id": 12345},
        )
        assert score == pytest.approx(1.0)


class TestComputeEpisodeConfidence:
    def test_exact_episode_and_season(self) -> None:
        score = compute_episode_confidence(
            {"season": 1, "episode": 1},
            {"season": 1, "episode": 1},
        )
        # 0.65 (ep) + 0.25 (season) = 0.9
        assert score == pytest.approx(0.9)

    def test_episode_match_only(self) -> None:
        score = compute_episode_confidence(
            {"episode": 3},
            {"season": 1, "episode": 3},
        )
        assert score == pytest.approx(0.65)

    def test_season_match_only(self) -> None:
        score = compute_episode_confidence(
            {"season": 2},
            {"season": 2, "episode": 5},
        )
        assert score == pytest.approx(0.25)

    def test_no_match(self) -> None:
        score = compute_episode_confidence(
            {"season": 1, "episode": 1},
            {"season": 2, "episode": 5},
        )
        assert score == pytest.approx(0.0)

    def test_episode_title_similarity(self) -> None:
        score = compute_episode_confidence(
            {"season": 1, "episode": 1, "episode_title": "Pilot"},
            {"season": 1, "episode": 1, "episode_title": "Pilot"},
        )
        # 0.65 (ep) + 0.25 (season) + 0.1 * 1.0 (title) = 1.0
        assert score == pytest.approx(1.0)

    def test_episode_title_partial(self) -> None:
        score = compute_episode_confidence(
            {"season": 1, "episode": 1, "episode_title": "The Pilot Episode"},
            {"season": 1, "episode": 1, "episode_title": "Pilot"},
        )
        # 0.65 + 0.25 + 0.1 * rapidfuzz("The Pilot Episode", "Pilot")
        # rapidfuzz WRatio scores this ~0.9, so total ~0.99
        assert score > 0.95

    def test_empty_query(self) -> None:
        score = compute_episode_confidence(
            {},
            {"season": 1, "episode": 1},
        )
        assert score == pytest.approx(0.0)

    def test_wrong_episode_right_season(self) -> None:
        score = compute_episode_confidence(
            {"season": 1, "episode": 1},
            {"season": 1, "episode": 5},
        )
        assert score == pytest.approx(0.25)

    def test_capped_at_1(self) -> None:
        # Even with all fields matching, should not exceed 1.0
        score = compute_episode_confidence(
            {"season": 1, "episode": 1, "episode_title": "Pilot"},
            {"season": 1, "episode": 1, "episode_title": "Pilot"},
        )
        assert score <= 1.0


class TestDefaultThreshold:
    def test_threshold_value(self) -> None:
        assert DEFAULT_AUTO_ACCEPT_THRESHOLD == 0.85
