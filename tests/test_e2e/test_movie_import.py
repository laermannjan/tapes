"""E2E tests for movie import scenarios (A1-A12).

Each test creates real files on disk, mocks TMDB HTTP via the ``responses``
library, runs the full import pipeline, and asserts on destination files,
DB records, and summary counts.
"""

from unittest.mock import patch

import responses

from tests.test_e2e.conftest import assert_db_record, assert_imported, make_video
from tests.test_e2e.tmdb_fixtures import (
    AMELIE_2001,
    BLADE_RUNNER_1982,
    DUNE_2021,
    INCEPTION_2010,
    THE_GODFATHER_1972,
    THE_MATRIX_1999,
    mock_tmdb,
    mock_tmdb_empty,
)


# ---------------------------------------------------------------------------
# Helper: patch the interactive prompt to auto-skip
# ---------------------------------------------------------------------------

def _skip_prompt(self, video, result, *, index, total):
    """Stand-in for ImportService._prompt_user that always skips."""
    return None, None


# ---------------------------------------------------------------------------
# Custom fixtures for tests that need bespoke TMDB responses
# ---------------------------------------------------------------------------

MY_MOVIE_NAME_2020 = {
    "search": {
        "results": [
            {
                "id": 70001,
                "title": "My Movie Name",
                "release_date": "2020-06-15",
                "genre_ids": [18],
            }
        ]
    },
    "detail": {
        "id": 70001,
        "title": "My Movie Name",
        "release_date": "2020-06-15",
        "genres": [{"name": "Drama"}],
        "credits": {"crew": [{"job": "Director", "name": "Jane Doe"}]},
    },
}

LONG_MOVIE_2021 = {
    "search": {
        "results": [
            {
                "id": 70002,
                "title": "A Really Long Movie Title That Goes On And On And On",
                "release_date": "2021-03-01",
                "genre_ids": [35],
            }
        ]
    },
    "detail": {
        "id": 70002,
        "title": "A Really Long Movie Title That Goes On And On And On",
        "release_date": "2021-03-01",
        "genres": [{"name": "Comedy"}],
        "credits": {"crew": []},
    },
}


# ---------------------------------------------------------------------------
# A1: Clean scene release
# ---------------------------------------------------------------------------


@responses.activate
def test_a1_clean_scene_release(source_dir, library, make_service):
    mock_tmdb(DUNE_2021)
    src = make_video(source_dir, "Dune.2021.1080p.BluRay.x265-GROUP.mkv")

    service, repo = make_service()
    summary = service.import_path(source_dir)

    assert summary["imported"] == 1
    assert summary["skipped"] == 0
    assert_imported(
        library["movies"],
        "Dune (2021)/Dune (2021).mkv",
        source=src,
        mode="copy",
    )
    assert_db_record(
        repo,
        count=1,
        title="Dune",
        year=2021,
        tmdb_id=438631,
        media_type="movie",
        match_source="filename",
    )


# ---------------------------------------------------------------------------
# A2: No year -> confidence below threshold -> skipped
# ---------------------------------------------------------------------------


@responses.activate
@patch(
    "tapes.importer.service.ImportService._prompt_user",
    _skip_prompt,
)
def test_a2_no_year_below_threshold(source_dir, library, make_service):
    mock_tmdb(INCEPTION_2010)
    make_video(source_dir, "Inception.1080p.mkv")

    service, repo = make_service()
    summary = service.import_path(source_dir)

    # JW("inception","inception")=1.0 * year_factor(None,2010)=0.8 -> 0.80 < 0.9
    # Pipeline sets requires_interaction=True; prompt mock returns skip.
    assert summary["imported"] == 0
    assert summary["skipped"] == 1
    assert_db_record(repo, count=0)


# ---------------------------------------------------------------------------
# A3: Wrong year off-by-one -> still above threshold
# ---------------------------------------------------------------------------


@responses.activate
def test_a3_wrong_year_off_by_one(source_dir, library, make_service):
    mock_tmdb(INCEPTION_2010)
    make_video(source_dir, "Inception.2009.1080p.mkv")

    service, repo = make_service()
    summary = service.import_path(source_dir)

    # JW=1.0 * year_factor(2009,2010)=0.95 -> 0.95 >= 0.9 -> auto-accept
    assert summary["imported"] == 1
    assert_imported(
        library["movies"],
        "Inception (2010)/Inception (2010).mkv",
    )
    assert_db_record(
        repo,
        count=1,
        title="Inception",
        year=2010,  # from TMDB, not filename
        tmdb_id=27205,
    )


# ---------------------------------------------------------------------------
# A4: Typo in title -> confidence too low -> skipped
# ---------------------------------------------------------------------------


@responses.activate
@patch(
    "tapes.importer.service.ImportService._prompt_user",
    _skip_prompt,
)
def test_a4_typo_in_title(source_dir, library, make_service):
    mock_tmdb(THE_MATRIX_1999)
    make_video(source_dir, "Teh.Matrx.1999.720p.mkv")

    service, repo = make_service()
    summary = service.import_path(source_dir)

    # JW("teh matrx","matrix")=0.5185 * 1.0 -> 0.5185 < 0.9 -> skipped
    assert summary["imported"] == 0
    assert summary["skipped"] == 1
    assert_db_record(repo, count=0)


# ---------------------------------------------------------------------------
# A5: Article normalization (The Godfather -> godfather vs godfather)
# ---------------------------------------------------------------------------


@responses.activate
def test_a5_article_normalization(source_dir, library, make_service):
    mock_tmdb(THE_GODFATHER_1972)
    src = make_video(source_dir, "The.Godfather.1972.mkv")

    service, repo = make_service()
    summary = service.import_path(source_dir)

    # JW("godfather","godfather")=1.0 * year_factor=1.0 -> 1.0 >= 0.9
    assert summary["imported"] == 1
    assert_imported(
        library["movies"],
        "The Godfather (1972)/The Godfather (1972).mkv",
        source=src,
        mode="copy",
    )
    assert_db_record(
        repo,
        count=1,
        title="The Godfather",
        year=1972,
        tmdb_id=238,
        media_type="movie",
    )


# ---------------------------------------------------------------------------
# A6: Edition tag (Director's Cut)
# ---------------------------------------------------------------------------


@responses.activate
def test_a6_edition_tag(source_dir, library, make_service):
    mock_tmdb(BLADE_RUNNER_1982)
    make_video(source_dir, "Blade.Runner.1982.Directors.Cut.1080p.mkv")

    # Use a template with conditional edition field
    service, repo = make_service(
        movie_template="{title} ({year}){edition: - $}/{title} ({year}){edition: - $}{ext}",
    )
    summary = service.import_path(source_dir)

    # JW=1.0 * year_factor=1.0 -> 1.0 >= 0.9 -> auto-accept
    assert summary["imported"] == 1
    assert summary["errors"] == 0
    assert_db_record(
        repo,
        count=1,
        title="Blade Runner",
        year=1982,
        tmdb_id=78,
    )
    # edition is None in the service (hardcoded), so the conditional renders empty
    assert_imported(
        library["movies"],
        "Blade Runner (1982)/Blade Runner (1982).mkv",
    )


# ---------------------------------------------------------------------------
# A7: Mixed separators
# ---------------------------------------------------------------------------


@responses.activate
def test_a7_mixed_separators(source_dir, library, make_service):
    # guessit extracts title="My Movie-Name", year=2020
    # JW("my movie-name","my movie name")=0.9692 * year_factor=1.0 -> 0.9692 >= 0.9
    mock_tmdb(MY_MOVIE_NAME_2020)
    make_video(source_dir, "My_Movie-Name (2020) [1080p].mkv")

    service, repo = make_service()
    summary = service.import_path(source_dir)

    assert summary["errors"] == 0
    assert summary["imported"] == 1
    assert_imported(
        library["movies"],
        "My Movie Name (2020)/My Movie Name (2020).mkv",
    )
    assert_db_record(repo, count=1, title="My Movie Name", year=2020, tmdb_id=70001)


# ---------------------------------------------------------------------------
# A8: Minimal filename ("movie.mkv")
# ---------------------------------------------------------------------------


@responses.activate
@patch(
    "tapes.importer.service.ImportService._prompt_user",
    _skip_prompt,
)
def test_a8_minimal_filename(source_dir, library, make_service):
    # guessit extracts title="movie", no year
    # TMDB returns empty -> no candidates, requires_interaction=True -> prompt skips
    mock_tmdb_empty()
    make_video(source_dir, "movie.mkv")

    service, repo = make_service()
    summary = service.import_path(source_dir)

    assert summary["errors"] == 0
    assert summary["skipped"] >= 1
    assert summary["imported"] == 0
    assert_db_record(repo, count=0)


# ---------------------------------------------------------------------------
# A9: Obfuscated hash name
# ---------------------------------------------------------------------------


@responses.activate
@patch(
    "tapes.importer.service.ImportService._prompt_user",
    _skip_prompt,
)
def test_a9_obfuscated_hash_name(source_dir, library, make_service):
    mock_tmdb_empty()
    make_video(source_dir, "a8f3e2b1c4d5.mkv")

    service, repo = make_service()
    summary = service.import_path(source_dir)

    assert summary["errors"] == 0
    assert summary["imported"] == 0
    assert summary["skipped"] >= 1
    assert_db_record(repo, count=0)


# ---------------------------------------------------------------------------
# A10: Unicode accents
# ---------------------------------------------------------------------------


@responses.activate
def test_a10_unicode_accents(source_dir, library, make_service):
    # guessit: title="Amélie", year=2001
    # TMDB returns title="Amelie"
    # JW("amélie","amelie")=0.9111 * year_factor=1.0 -> 0.9111 >= 0.9 -> auto-accept
    mock_tmdb(AMELIE_2001)
    make_video(source_dir, "Am\u00e9lie.2001.mkv")

    service, repo = make_service()
    summary = service.import_path(source_dir)

    assert summary["errors"] == 0
    assert summary["imported"] == 1
    assert_imported(
        library["movies"],
        "Amelie (2001)/Amelie (2001).mkv",
    )
    assert_db_record(repo, count=1, title="Amelie", year=2001, tmdb_id=194)


# ---------------------------------------------------------------------------
# A11: Very long filename
# ---------------------------------------------------------------------------


@responses.activate
def test_a11_very_long_filename(source_dir, library, make_service):
    # guessit: title="A Really Long Movie Title That Goes On And On And On", year=2021
    # JW with exact match=1.0 * year_factor=1.0 -> 1.0 >= 0.9 -> auto-accept
    mock_tmdb(LONG_MOVIE_2021)
    make_video(
        source_dir,
        "A.Really.Long.Movie.Title.That.Goes.On.And.On.And.On.2021.1080p.BluRay.Remux.AVC.DTS-HD.MA.5.1-GROUP.mkv",
    )

    service, repo = make_service()
    summary = service.import_path(source_dir)

    assert summary["errors"] == 0
    # Exact title match -> imported
    assert summary["imported"] == 1
    assert_db_record(repo, count=1, tmdb_id=70002, year=2021)


# ---------------------------------------------------------------------------
# A12: Resolution-only filename
# ---------------------------------------------------------------------------


@responses.activate
@patch(
    "tapes.importer.service.ImportService._prompt_user",
    _skip_prompt,
)
def test_a12_resolution_only(source_dir, library, make_service):
    # guessit: title=None -> TMDBSource.search returns [] for empty title
    # No candidates, requires_interaction=True -> prompt skips
    mock_tmdb_empty()
    make_video(source_dir, "1080p.x264.mkv")

    service, repo = make_service()
    summary = service.import_path(source_dir)

    assert summary["errors"] == 0
    assert summary["imported"] == 0
    assert summary["skipped"] >= 1
    assert_db_record(repo, count=0)
