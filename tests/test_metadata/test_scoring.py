import pytest
from tapes.metadata.tmdb import _normalize_title, _title_similarity, _year_factor, _score


# --- Title normalization ---

class TestNormalizeTitle:
    def test_strips_leading_the(self):
        assert _normalize_title("The Matrix") == "matrix"

    def test_strips_leading_a(self):
        assert _normalize_title("A Quiet Place") == "quiet place"

    def test_strips_leading_an(self):
        assert _normalize_title("An Officer and a Gentleman") == "officer and a gentleman"

    def test_case_insensitive(self):
        assert _normalize_title("THE MATRIX") == "matrix"

    def test_no_article(self):
        assert _normalize_title("Matrix") == "matrix"

    def test_article_in_middle_preserved(self):
        assert _normalize_title("Lord of the Rings") == "lord of the rings"

    def test_empty_string(self):
        assert _normalize_title("") == ""


# --- Title similarity ---

class TestTitleSimilarity:
    def test_exact_match(self):
        assert _title_similarity("The Matrix", "The Matrix") == pytest.approx(1.0)

    def test_query_missing_article(self):
        # guessit often strips "The" from filenames
        score = _title_similarity("Matrix", "The Matrix")
        assert score == pytest.approx(1.0)

    def test_article_the_both_ways(self):
        assert _title_similarity("The Matrix", "Matrix") == pytest.approx(1.0)

    def test_case_difference(self):
        assert _title_similarity("the matrix", "THE MATRIX") == pytest.approx(1.0)

    def test_minor_typo(self):
        # "Matrx" vs "Matrix" - one char off
        score = _title_similarity("Matrx", "The Matrix")
        assert score > 0.85

    def test_scene_title_dots_parsed(self):
        # guessit parses "The.Matrix" -> "The Matrix", so this should be exact
        score = _title_similarity("The Matrix", "The Matrix")
        assert score == pytest.approx(1.0)

    def test_completely_different(self):
        score = _title_similarity("Inception", "The Matrix")
        assert score < 0.6

    def test_partial_match(self):
        # "Matrix" vs "Matrix Reloaded" - related but different
        score = _title_similarity("Matrix", "Matrix Reloaded")
        assert 0.7 < score < 0.95

    def test_sequel_disambiguation(self):
        # Should distinguish between similar sequels
        score_1 = _title_similarity("The Matrix", "The Matrix")
        score_2 = _title_similarity("The Matrix", "The Matrix Reloaded")
        assert score_1 > score_2

    def test_foreign_title(self):
        score = _title_similarity("Amelie", "Amelie")
        assert score == pytest.approx(1.0)

    def test_subtitle_in_title(self):
        # Scene releases sometimes include subtitle
        score = _title_similarity("Alien Romulus", "Alien: Romulus")
        assert score > 0.9

    def test_ampersand_vs_and(self):
        score = _title_similarity("Fast and Furious", "Fast & Furious")
        assert score > 0.85


# --- Year factor ---

class TestYearFactor:
    def test_exact_year(self):
        assert _year_factor(1999, 1999) == 1.0

    def test_off_by_one(self):
        assert _year_factor(1999, 2000) == 0.95
        assert _year_factor(2000, 1999) == 0.95

    def test_off_by_two(self):
        assert _year_factor(1999, 2001) == 0.85

    def test_no_query_year(self):
        assert _year_factor(None, 1999) == 0.8

    def test_no_result_year(self):
        assert _year_factor(1999, None) == 0.8

    def test_both_years_none(self):
        assert _year_factor(None, None) == 0.8

    def test_large_distance_has_floor(self):
        factor = _year_factor(1999, 2020)
        assert factor == 0.5

    def test_moderate_distance(self):
        # 5 years: 1.0 - 0.5 = 0.5
        factor = _year_factor(1999, 2004)
        assert factor == 0.5

    def test_three_years(self):
        factor = _year_factor(1999, 2002)
        assert factor == 0.7

    def test_monotonic_decay(self):
        factors = [_year_factor(2000, 2000 + d) for d in range(10)]
        for i in range(len(factors) - 1):
            assert factors[i] >= factors[i + 1]


# --- Combined scoring (simulates TMDB response items) ---

def _item(title: str, year: str | None, media_type: str = "movie") -> dict:
    """Build a minimal TMDB-like result item."""
    item = {}
    if media_type == "tv":
        item["name"] = title
        if year:
            item["first_air_date"] = f"{year}-01-01"
    else:
        item["title"] = title
        if year:
            item["release_date"] = f"{year}-01-01"
    return item


class TestScore:
    """End-to-end scoring tests simulating real filename -> TMDB result pairs."""

    # --- Exact matches ---

    def test_exact_title_and_year(self):
        score = _score("The Matrix", 1999, _item("The Matrix", "1999"), "movie", 1999)
        assert score > 0.95

    def test_exact_title_no_year_in_query(self):
        score = _score("The Matrix", None, _item("The Matrix", "1999"), "movie", 1999)
        assert 0.75 < score < 0.85

    # --- Scene naming conventions ---

    def test_scene_missing_article(self):
        # Matrix.1999.BluRay.mkv -> guessit: title="Matrix"
        score = _score("Matrix", 1999, _item("The Matrix", "1999"), "movie", 1999)
        assert score > 0.9

    def test_scene_year_off_by_one(self):
        # Matrix.2000.BluRay.mkv
        score = _score("Matrix", 2000, _item("The Matrix", "1999"), "movie", 1999)
        assert score > 0.85

    def test_scene_wrong_year(self):
        # Matrix.1998.BluRay.mkv
        score = _score("Matrix", 1998, _item("The Matrix", "1999"), "movie", 1999)
        assert score > 0.85

    def test_scene_very_wrong_year(self):
        # Matrix.1989.BluRay.mkv - 10 years off
        score = _score("Matrix", 1989, _item("The Matrix", "1999"), "movie", 1999)
        assert score < 0.6

    # --- Typos ---

    def test_typo_one_char(self):
        score = _score("Matrx", 1999, _item("The Matrix", "1999"), "movie", 1999)
        assert score > 0.8

    def test_typo_transposition(self):
        score = _score("Amlie", 2001, _item("Amelie", "2001"), "movie", 2001)
        assert score > 0.8

    def test_typo_extra_char(self):
        score = _score("Matrixx", 1999, _item("The Matrix", "1999"), "movie", 1999)
        assert score > 0.8

    # --- TV shows ---

    def test_tv_exact(self):
        score = _score("The Wire", 2002, _item("The Wire", "2002", "tv"), "tv", 2002)
        assert score > 0.95

    def test_tv_missing_article(self):
        score = _score("Wire", 2002, _item("The Wire", "2002", "tv"), "tv", 2002)
        assert score > 0.9

    def test_tv_year_off(self):
        score = _score("Breaking Bad", 2007, _item("Breaking Bad", "2008", "tv"), "tv", 2008)
        assert score > 0.9

    # --- Disambiguation ---

    def test_correct_movie_scores_higher_than_wrong_sequel(self):
        score_correct = _score("The Matrix", 1999, _item("The Matrix", "1999"), "movie", 1999)
        score_sequel = _score("The Matrix", 1999, _item("The Matrix Reloaded", "2003"), "movie", 2003)
        assert score_correct > score_sequel

    def test_correct_year_wins_over_wrong_year(self):
        score_right = _score("Dune", 2021, _item("Dune", "2021"), "movie", 2021)
        score_wrong = _score("Dune", 2021, _item("Dune", "1984"), "movie", 1984)
        assert score_right > score_wrong

    # --- Edge cases ---

    def test_empty_query_title(self):
        score = _score("", 1999, _item("The Matrix", "1999"), "movie", 1999)
        assert score < 0.5

    def test_no_years_at_all(self):
        score = _score("The Matrix", None, _item("The Matrix", None), "movie", None)
        assert 0.75 < score < 0.85

    def test_single_word_vs_long_title(self):
        # "Avatar" should match well, not get confused by length
        score = _score("Avatar", 2009, _item("Avatar", "2009"), "movie", 2009)
        assert score > 0.95

    # --- Real-world scene filenames (post-guessit parsing) ---

    def test_scene_inception(self):
        score = _score("Inception", 2010, _item("Inception", "2010"), "movie", 2010)
        assert score > 0.95

    def test_scene_parasite(self):
        score = _score("Parasite", 2019, _item("Parasite", "2019"), "movie", 2019)
        assert score > 0.95

    def test_scene_with_subtitle_colon(self):
        # guessit: "Blade Runner 2049"
        score = _score("Blade Runner 2049", 2017, _item("Blade Runner 2049", "2017"), "movie", 2017)
        assert score > 0.95

    def test_scene_multi_word_mismatch(self):
        # "Eternal Sunshine" vs full title
        score = _score(
            "Eternal Sunshine of the Spotless Mind", 2004,
            _item("Eternal Sunshine of the Spotless Mind", "2004"), "movie", 2004,
        )
        assert score > 0.95
