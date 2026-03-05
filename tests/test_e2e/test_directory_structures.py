"""End-to-end tests for different directory layouts (C1-C7)."""

import responses

from tests.test_e2e.conftest import (
    assert_db_record,
    assert_imported,
    make_video,
)
from tests.test_e2e.tmdb_fixtures import (
    DUNE_2021,
    GENERIC_SHOW,
    INCEPTION_2010,
    mock_tmdb,
)


# ---------------------------------------------------------------------------
# C1: Flat directory with mixed file types
# ---------------------------------------------------------------------------


@responses.activate
def test_c1_flat_mixed_directory(source_dir, library, make_service):
    """Flat dir with two videos, a .txt, and a sample.mkv.

    Only the two real videos should be imported.  The .txt is not a video
    extension so the scanner ignores it.  sample.mkv matches the sample
    pattern (^sample$) and is excluded.

    guessit: Dune title="Dune" year=2021 -> confidence ~1.0
             Inception title="Inception" year=2010 -> confidence ~1.0
    """
    make_video(source_dir, "Dune.2021.1080p.mkv")
    make_video(source_dir, "Inception.2010.720p.mkv")
    (source_dir / "random_file.txt").write_text("not a video")
    make_video(source_dir, "sample.mkv")

    mock_tmdb(DUNE_2021)
    mock_tmdb(INCEPTION_2010)

    service, repo = make_service()
    summary = service.import_path(source_dir)

    assert summary["imported"] == 2
    assert summary["errors"] == 0

    assert_imported(library["movies"], "Dune (2021)/Dune (2021).mkv")
    assert_imported(library["movies"], "Inception (2010)/Inception (2010).mkv")
    assert_db_record(repo, count=2)


# ---------------------------------------------------------------------------
# C2: Scene release folder with NFO (no TMDB tag), SRT, and sample subfolder
# ---------------------------------------------------------------------------


MOVIE_NAME_2021 = {
    "search": {
        "results": [
            {
                "id": 12345,
                "title": "Movie Name",
                "release_date": "2021-06-01",
                "genre_ids": [28],
            }
        ]
    },
    "detail": {
        "id": 12345,
        "title": "Movie Name",
        "release_date": "2021-06-01",
        "genres": [{"name": "Action"}],
        "credits": {"crew": []},
    },
}


@responses.activate
def test_c2_scene_release_folder(source_dir, library, make_service):
    """Scene-style folder with video, NFO (no tmdbid), SRT, and sample sub-dir.

    The NFO has no <tmdbid> tag, so the NFO scanner returns None and
    identification falls through to guessit + TMDB search.

    guessit: title="Movie Name", year=2021 -> confidence ~1.0
    Expect: 1 video imported, NFO and SRT moved as companions, sample excluded.
    """
    scene_dir = source_dir / "Movie.Name.2021.1080p.BluRay.x264-GROUP"
    scene_dir.mkdir(parents=True)

    video = make_video(scene_dir, "Movie.Name.2021.1080p.BluRay.x264-GROUP.mkv")
    # NFO without a tmdbid tag -- scanner returns None, falls through to guessit
    nfo = scene_dir / "Movie.Name.2021.1080p.BluRay.x264-GROUP.nfo"
    nfo.write_text("<movie><title>Movie Name</title></movie>")
    srt = scene_dir / "Movie.Name.2021.1080p.BluRay.x264-GROUP.en.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")

    sample_dir = scene_dir / "Sample"
    sample_dir.mkdir()
    make_video(sample_dir, "sample-movie.mkv")

    mock_tmdb(MOVIE_NAME_2021)

    service, repo = make_service()
    summary = service.import_path(source_dir)

    assert summary["imported"] == 1
    assert summary["errors"] == 0

    dest = assert_imported(
        library["movies"],
        "Movie Name (2021)/Movie Name (2021).mkv",
        source=video,
        mode="copy",
    )
    # Companions should be moved alongside the video
    companion_dir = dest.parent
    srt_files = list(companion_dir.glob("*.srt"))
    nfo_files = list(companion_dir.glob("*.nfo"))
    assert len(srt_files) == 1, f"Expected 1 SRT companion, found {srt_files}"
    assert len(nfo_files) == 1, f"Expected 1 NFO companion, found {nfo_files}"

    assert_db_record(repo, count=1, title="Movie Name", year=2021)


# ---------------------------------------------------------------------------
# C3: Nested TV structure (Show/Season NN/episodes)
# ---------------------------------------------------------------------------


@responses.activate
def test_c3_nested_tv_structure(source_dir, library, make_service):
    """Nested TV layout: Show Name/Season 01/S01E01.mkv etc.

    guessit: show="Show Name", season and episode extracted from filename.
    No year -> year_factor = 0.8. JW("show name", "show name") = 1.0.
    confidence = 0.8 -> threshold lowered to 0.75 for auto-accept.
    """
    show_dir = source_dir / "Show Name"
    s01 = show_dir / "Season 01"
    s02 = show_dir / "Season 02"

    make_video(s01, "Show.Name.S01E01.mkv")
    make_video(s01, "Show.Name.S01E02.mkv")
    make_video(s02, "Show.Name.S02E01.mkv")

    # Pipeline calls search once per file
    mock_tmdb(GENERIC_SHOW, "tv")
    mock_tmdb(GENERIC_SHOW, "tv")
    mock_tmdb(GENERIC_SHOW, "tv")

    service, repo = make_service(threshold=0.75)
    summary = service.import_path(source_dir)

    assert summary["imported"] == 3
    assert summary["errors"] == 0

    assert_imported(
        library["tv"],
        "Show Name/Season 01/Show Name - S01E01.mkv",
    )
    assert_imported(
        library["tv"],
        "Show Name/Season 01/Show Name - S01E02.mkv",
    )
    assert_imported(
        library["tv"],
        "Show Name/Season 02/Show Name - S02E01.mkv",
    )

    assert_db_record(repo, count=3)
    assert_db_record(repo, media_type="tv", season=1, episode=1)
    assert_db_record(repo, media_type="tv", season=1, episode=2)
    assert_db_record(repo, media_type="tv", season=2, episode=1)


# ---------------------------------------------------------------------------
# C4: RAR extraction artifacts alongside video
# ---------------------------------------------------------------------------


@responses.activate
def test_c4_rar_extract_artifacts(source_dir, library, make_service):
    """Directory with video, .r00/.r01/.nzb junk, and SRT in Subs/ subfolder.

    .r00, .r01, .nzb are not in VIDEO_EXTENSIONS -- scanner ignores them.
    SRT in Subs/ is found by companion classifier (recursive scan of parent).
    """
    movie_dir = source_dir / "Movie.Name.2021"
    movie_dir.mkdir()

    video = make_video(movie_dir, "Movie.Name.2021.mkv")
    (movie_dir / "Movie.Name.2021.r00").write_bytes(b"\x00" * 100)
    (movie_dir / "Movie.Name.2021.r01").write_bytes(b"\x00" * 100)
    (movie_dir / "Movie.Name.2021.nzb").write_text("<nzb></nzb>")

    subs_dir = movie_dir / "Subs"
    subs_dir.mkdir()
    srt = subs_dir / "Movie.Name.2021.en.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")

    mock_tmdb(MOVIE_NAME_2021)

    service, repo = make_service()
    summary = service.import_path(source_dir)

    assert summary["imported"] == 1
    assert summary["errors"] == 0

    dest = assert_imported(
        library["movies"],
        "Movie Name (2021)/Movie Name (2021).mkv",
        source=video,
        mode="copy",
    )
    # SRT from Subs/ should be moved as companion
    srt_files = list(dest.parent.rglob("*.srt"))
    assert len(srt_files) == 1, f"Expected 1 SRT companion, found {srt_files}"

    assert_db_record(repo, count=1, title="Movie Name", year=2021)


# ---------------------------------------------------------------------------
# C5: Single file import (pass file path, not directory)
# ---------------------------------------------------------------------------


@responses.activate
def test_c5_single_file_import(source_dir, library, make_service):
    """Pass a single file path (not directory) to import_path().

    scan_media_files returns [file] directly when given a file path.
    """
    video = make_video(source_dir, "Dune.2021.mkv")
    mock_tmdb(DUNE_2021)

    service, repo = make_service()
    # Pass the FILE path, not the directory
    summary = service.import_path(video)

    assert summary["imported"] == 1
    assert summary["errors"] == 0

    assert_imported(
        library["movies"],
        "Dune (2021)/Dune (2021).mkv",
        source=video,
        mode="copy",
    )
    assert_db_record(repo, count=1, title="Dune", year=2021)


# ---------------------------------------------------------------------------
# C6: Empty directory
# ---------------------------------------------------------------------------


def test_c6_empty_directory(source_dir, library, make_service):
    """Empty subdirectory -- no crash, summary shows 0 imported, 0 errors."""
    empty = source_dir / "empty"
    empty.mkdir()

    service, _repo = make_service()
    summary = service.import_path(empty)

    assert summary["imported"] == 0
    assert summary["errors"] == 0


# ---------------------------------------------------------------------------
# C7: Non-video files only
# ---------------------------------------------------------------------------


def test_c7_non_video_files_only(source_dir, library, make_service):
    """Directory with only non-video files -- no crash, nothing imported."""
    (source_dir / "readme.txt").write_text("hello")
    (source_dir / "poster.jpg").write_bytes(b"\xff\xd8" + b"\x00" * 100)
    (source_dir / "movie.nfo").write_text("<movie></movie>")

    service, _repo = make_service()
    summary = service.import_path(source_dir)

    assert summary["imported"] == 0
    assert summary["errors"] == 0
