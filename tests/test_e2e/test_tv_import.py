"""End-to-end tests for TV show import scenarios (B1-B7)."""

from unittest.mock import patch

import responses

from tests.test_e2e.conftest import assert_db_record, assert_imported, make_video
from tests.test_e2e.tmdb_fixtures import (
    BREAKING_BAD,
    GENERIC_SHOW,
    THE_DAILY_SHOW,
    THE_OFFICE_AMBIGUOUS,
    mock_tmdb,
    mock_tmdb_ambiguous,
    mock_tmdb_empty,
)


# ---------------------------------------------------------------------------
# Helper: patch the interactive prompt to auto-skip
# ---------------------------------------------------------------------------

def _skip_prompt(self, video, result, *, index, total):
    """Stand-in for ImportService._prompt_user that always skips."""
    return None, None


# ---------------------------------------------------------------------------
# B1: Standard TV episode
# ---------------------------------------------------------------------------


@responses.activate
def test_b1_standard_tv_episode(source_dir, library, make_service):
    """Breaking.Bad.S01E01.720p.mkv -- auto-accepts with lowered threshold.

    guessit extracts show="Breaking Bad", season=1, episode=1, no year.
    JW("breaking bad", "breaking bad") = 1.0, year_factor = 0.8 (no year).
    confidence = 0.80. Threshold lowered to 0.75 so it auto-accepts.
    """
    video = make_video(source_dir, "Breaking.Bad.S01E01.720p.mkv")
    mock_tmdb(BREAKING_BAD, media_type="tv")

    service, repo = make_service(threshold=0.75)
    summary = service.import_path(source_dir)

    assert summary["imported"] == 1
    assert summary["skipped"] == 0

    assert_imported(
        library["tv"],
        "Breaking Bad/Season 01/Breaking Bad - S01E01.mkv",
        source=video,
        mode="copy",
    )
    assert_db_record(
        repo,
        count=1,
        media_type="tv",
        show="Breaking Bad",
        season=1,
        episode=1,
        tmdb_id=1396,
    )


# ---------------------------------------------------------------------------
# B2: Folder name fallback
# ---------------------------------------------------------------------------


@responses.activate
def test_b2_folder_name_fallback(source_dir, library, make_service):
    """source_dir/Breaking Bad/S01E01.mkv -- show name from folder.

    parse_filename("S01E01.mkv", folder_name="Breaking Bad") extracts
    show="Breaking Bad", season=1, episode=1, year=None.
    confidence = 1.0 * 0.8 = 0.80.  Threshold lowered to 0.75.
    """
    show_dir = source_dir / "Breaking Bad"
    show_dir.mkdir()
    video = make_video(show_dir, "S01E01.mkv")
    mock_tmdb(BREAKING_BAD, media_type="tv")

    service, repo = make_service(threshold=0.75)
    summary = service.import_path(source_dir)

    assert summary["imported"] == 1

    assert_imported(
        library["tv"],
        "Breaking Bad/Season 01/Breaking Bad - S01E01.mkv",
        source=video,
        mode="copy",
    )
    assert_db_record(
        repo,
        count=1,
        media_type="tv",
        show="Breaking Bad",
        season=1,
        episode=1,
    )


# ---------------------------------------------------------------------------
# B3: Multi-episode file is skipped (non-interactive)
# ---------------------------------------------------------------------------


@responses.activate
@patch(
    "tapes.importer.service.ImportService._prompt_user",
    _skip_prompt,
)
def test_b3_multi_episode_skipped(source_dir, make_service):
    """The.Wire.S01E01E02.mkv -- multi-episode guard triggers skip.

    guessit extracts episode=[1,2]. Pipeline sets requires_interaction=True,
    multi_episode=True. Non-interactive mode: skipped.
    """
    make_video(source_dir, "The.Wire.S01E01E02.mkv")
    # Safety mock in case pipeline somehow reaches TMDB
    mock_tmdb_empty(media_type="tv")

    service, repo = make_service()
    summary = service.import_path(source_dir)

    assert summary["imported"] == 0
    assert summary["skipped"] == 1
    assert_db_record(repo, count=0)


# ---------------------------------------------------------------------------
# B4: Daily show (date-based episode)
# ---------------------------------------------------------------------------


@responses.activate
@patch(
    "tapes.importer.service.ImportService._prompt_user",
    _skip_prompt,
)
def test_b4_daily_show(source_dir, make_service):
    """The.Daily.Show.2024.01.15.mkv -- date-based episode, no crash.

    guessit extracts show="The Daily Show", date=2024-01-15, no season.
    Without season in file_info, pipeline treats it as media_type="movie".
    No crash is the key assertion. The file will be skipped or imported
    depending on scoring; either outcome is acceptable.
    """
    make_video(source_dir, "The.Daily.Show.2024.01.15.mkv")
    # Pipeline searches as "movie" (no season), so mock movie endpoint
    mock_tmdb_empty(media_type="movie")

    service, repo = make_service()
    summary = service.import_path(source_dir)

    # No crash -- either skipped (no results) or imported
    assert summary["errors"] == 0
    assert summary["skipped"] + summary["imported"] == 1


# ---------------------------------------------------------------------------
# B5: Ambiguous show name -- both below threshold, skipped
# ---------------------------------------------------------------------------


@responses.activate
@patch(
    "tapes.importer.service.ImportService._prompt_user",
    _skip_prompt,
)
def test_b5_ambiguous_show_name(source_dir, make_service):
    """The.Office.S01E01.mkv -- two results with same name, both below threshold.

    guessit: show="The Office", season=1, episode=1, no year.
    Both TMDB results have JW=1.0 (after article removal).
    No year in filename -> year_factor=0.8 -> confidence=0.80.
    Default threshold=0.9 -> requires_interaction -> skipped.
    """
    make_video(source_dir, "The.Office.S01E01.mkv")
    mock_tmdb_ambiguous(THE_OFFICE_AMBIGUOUS, media_type="tv")

    service, repo = make_service()  # default threshold=0.9
    summary = service.import_path(source_dir)

    assert summary["imported"] == 0
    assert summary["skipped"] == 1
    assert_db_record(repo, count=0)


# ---------------------------------------------------------------------------
# B6: Anime-style naming -- no crash
# ---------------------------------------------------------------------------


@responses.activate
@patch(
    "tapes.importer.service.ImportService._prompt_user",
    _skip_prompt,
)
def test_b6_anime_style_naming(source_dir, make_service):
    """[SubGroup] Show Name - 01 [1080p].mkv -- anime bracket naming.

    guessit extracts show="Show Name", episode=1, no season.
    Without season, pipeline treats as media_type="movie".
    Key assertion: no crash.
    """
    make_video(source_dir, "[SubGroup] Show Name - 01 [1080p].mkv")
    # No season -> movie search
    mock_tmdb_empty(media_type="movie")

    service, repo = make_service()
    summary = service.import_path(source_dir)

    assert summary["errors"] == 0
    assert summary["skipped"] + summary["imported"] == 1


# ---------------------------------------------------------------------------
# B7: Season pack -- multiple episodes from same folder
# ---------------------------------------------------------------------------


@responses.activate
def test_b7_season_pack(source_dir, library, make_service):
    """Season pack: 3 episodes in Show.Name.S02.Complete/ folder.

    Each file individually identified and imported. TMDB searched once per
    file (mock registered 3 times). Threshold lowered to 0.75 for
    auto-accept (no year in filename -> year_factor=0.8, JW=1.0 -> 0.80).
    """
    pack_dir = source_dir / "Show.Name.S02.Complete"
    pack_dir.mkdir()
    videos = []
    for i in range(1, 4):
        v = make_video(pack_dir, f"Show.Name.S02E{i:02d}.mkv")
        videos.append(v)

    # Register search + detail 3 times (one per file)
    for _ in range(3):
        mock_tmdb(GENERIC_SHOW, media_type="tv")

    service, repo = make_service(threshold=0.75)
    summary = service.import_path(source_dir)

    assert summary["imported"] == 3
    assert summary["errors"] == 0

    for i in range(1, 4):
        assert_imported(
            library["tv"],
            f"Show Name/Season 02/Show Name - S02E{i:02d}.mkv",
            source=videos[i - 1],
            mode="copy",
        )

    assert_db_record(repo, count=3)
    # Verify each episode is in the DB
    for i in range(1, 4):
        assert_db_record(repo, media_type="tv", season=2, episode=i, show="Show Name")
