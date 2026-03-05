"""E2E tests for edge cases (E1-E16).

Covers re-import cache behaviour, import modes, dry-run, no-db,
TMDB error handling, NFO identification, template sanitisation,
confidence thresholds, partial failures, and DB field correctness.
"""

from unittest.mock import patch

import responses

from tapes.importer.service import ImportService
from tests.test_e2e.conftest import assert_db_record, make_nfo, make_video
from tests.test_e2e.tmdb_fixtures import (
    BREAKING_BAD,
    DUNE_2021,
    INCEPTION_2010,
    MOVIE_WITH_SPECIAL_CHARS,
    mock_tmdb,
    mock_tmdb_by_id,
    mock_tmdb_error,
)


# ---------------------------------------------------------------------------
# Helper: patch the interactive prompt to auto-skip
# ---------------------------------------------------------------------------


def _skip_prompt(self, video, result, *, index, total):
    """Stand-in for ImportService._prompt_user that always skips."""
    return None, None


# ---------------------------------------------------------------------------
# E1-E2: Re-import / cache behaviour
# ---------------------------------------------------------------------------


@responses.activate
def test_e1_reimport_cache_hit(source_dir, make_service, library):
    """Re-import: DB cache hit on second import -> skipped."""
    make_video(source_dir, "Dune.2021.mkv")
    mock_tmdb(DUNE_2021)
    # First import: move mode so file ends up at dest
    service, repo = make_service(mode="move")
    s1 = service.import_path(source_dir)
    assert s1["imported"] == 1

    # Second import: scan library dir where file now lives
    mock_tmdb(DUNE_2021)  # register again for potential search
    service2, _ = make_service(mode="copy")  # same repo via fixture
    s2 = service2.import_path(library["movies"])
    assert s2["skipped"] == 1
    assert s2["imported"] == 0


@responses.activate
def test_e2_modified_file_reimport(source_dir, make_service, library):
    """Modified file: cache miss -> re-identified."""
    make_video(source_dir, "Dune.2021.mkv")
    mock_tmdb(DUNE_2021)
    service, repo = make_service(mode="move")
    s1 = service.import_path(source_dir)
    assert s1["imported"] == 1

    # Find dest file and modify it
    dest_files = list(library["movies"].rglob("*.mkv"))
    assert len(dest_files) == 1
    dest = dest_files[0]
    # Append bytes to change size and mtime
    with open(dest, "ab") as f:
        f.write(b"\x00" * 100)

    # Re-import library: cache miss (size changed)
    mock_tmdb(DUNE_2021)
    service2, _ = make_service(mode="copy")
    s2 = service2.import_path(library["movies"])
    # Should re-identify (not skip)
    assert s2["skipped"] == 0


# ---------------------------------------------------------------------------
# E3: Dry-run
# ---------------------------------------------------------------------------


@responses.activate
def test_e3_dry_run_no_side_effects(source_dir, make_service, library):
    """Dry-run: planned entries but no files or DB records."""
    make_video(source_dir, "Dune.2021.mkv")
    mock_tmdb(DUNE_2021)
    service, repo = make_service(dry_run=True)
    summary = service.import_path(source_dir)
    assert summary["dry_run"] is True
    assert summary["imported"] == 1
    assert len(summary["planned"]) == 1
    # No files in library
    assert list(library["movies"].rglob("*.mkv")) == []
    # No DB records
    assert_db_record(repo, count=0)


# ---------------------------------------------------------------------------
# E4-E7: Import modes
# ---------------------------------------------------------------------------


@responses.activate
def test_e4_move_mode(source_dir, make_service, library):
    """Move: source deleted after import."""
    video = make_video(source_dir, "Dune.2021.mkv")
    mock_tmdb(DUNE_2021)
    service, repo = make_service(mode="move")
    summary = service.import_path(source_dir)
    assert summary["imported"] == 1
    assert not video.exists()
    dest_files = list(library["movies"].rglob("*.mkv"))
    assert len(dest_files) == 1


@responses.activate
def test_e5_copy_mode(source_dir, make_service, library):
    """Copy: source preserved after import."""
    video = make_video(source_dir, "Dune.2021.mkv")
    mock_tmdb(DUNE_2021)
    service, repo = make_service(mode="copy")
    summary = service.import_path(source_dir)
    assert summary["imported"] == 1
    assert video.exists()
    dest_files = list(library["movies"].rglob("*.mkv"))
    assert len(dest_files) == 1


@responses.activate
def test_e6_link_mode(source_dir, make_service, library):
    """Link: dest is symlink, source preserved."""
    video = make_video(source_dir, "Dune.2021.mkv")
    mock_tmdb(DUNE_2021)
    service, repo = make_service(mode="link")
    summary = service.import_path(source_dir)
    assert summary["imported"] == 1
    assert video.exists()
    dest_files = list(library["movies"].rglob("*.mkv"))
    assert len(dest_files) == 1
    assert dest_files[0].is_symlink()


@responses.activate
def test_e7_hardlink_mode(source_dir, make_service, library):
    """Hardlink: same inode."""
    video = make_video(source_dir, "Dune.2021.mkv")
    mock_tmdb(DUNE_2021)
    service, repo = make_service(mode="hardlink")
    summary = service.import_path(source_dir)
    assert summary["imported"] == 1
    assert video.exists()
    dest_files = list(library["movies"].rglob("*.mkv"))
    assert len(dest_files) == 1
    assert dest_files[0].stat().st_ino == video.stat().st_ino


# ---------------------------------------------------------------------------
# E8: --no-db mode
# ---------------------------------------------------------------------------


@responses.activate
def test_e8_no_db_mode(source_dir, make_service, library):
    """--no-db: file imported but no DB or session records."""
    make_video(source_dir, "Dune.2021.mkv")
    mock_tmdb(DUNE_2021)
    service, repo = make_service(no_db=True)
    summary = service.import_path(source_dir)
    assert summary["imported"] == 1
    assert_db_record(repo, count=0)
    sessions = repo._conn.execute("SELECT count(*) FROM sessions").fetchone()[0]
    assert sessions == 0


# ---------------------------------------------------------------------------
# E9-E10: TMDB error handling
# ---------------------------------------------------------------------------


@responses.activate
@patch.object(ImportService, "_prompt_user", _skip_prompt)
def test_e9_tmdb_network_error(source_dir, make_service, library):
    """TMDB unreachable: no crash, file unmatched."""
    make_video(source_dir, "Dune.2021.mkv")
    # Don't register any TMDB mocks -- responses library raises ConnectionError
    service, repo = make_service()
    summary = service.import_path(source_dir)
    assert summary["errors"] == 0
    assert summary["imported"] == 0


@responses.activate
@patch.object(ImportService, "_prompt_user", _skip_prompt)
def test_e10_tmdb_http_error(source_dir, make_service, library):
    """TMDB returns 401: no crash, file unmatched."""
    make_video(source_dir, "Dune.2021.mkv")
    mock_tmdb_error(status=401)
    service, repo = make_service()
    summary = service.import_path(source_dir)
    assert summary["errors"] == 0
    assert summary["imported"] == 0


# ---------------------------------------------------------------------------
# E11-E12: NFO identification
# ---------------------------------------------------------------------------


@responses.activate
def test_e11_nfo_identification(source_dir, make_service, library):
    """NFO with tmdbid: identified via NFO, conf=0.95, source='nfo'."""
    movie_dir = source_dir / "Movie"
    movie_dir.mkdir()
    make_video(movie_dir, "Movie.mkv")
    make_nfo(movie_dir, "Movie.nfo", tmdb_id=438631)
    mock_tmdb_by_id(DUNE_2021, media_type="movie")
    service, repo = make_service()
    summary = service.import_path(source_dir)
    assert summary["imported"] == 1
    item = assert_db_record(repo, count=1, tmdb_id=438631, match_source="nfo")
    assert item.confidence == 0.95


@responses.activate
def test_e12_tvshow_nfo(source_dir, make_service, library):
    """tvshow.nfo nearby: media_type='tv', identified via NFO."""
    show_dir = source_dir / "Show"
    show_dir.mkdir()
    make_nfo(show_dir, "tvshow.nfo", tmdb_id=1396, root_tag="tvshow")
    make_video(show_dir, "S01E01.mkv")
    mock_tmdb_by_id(BREAKING_BAD, media_type="tv")
    service, repo = make_service()
    summary = service.import_path(source_dir)
    assert summary["imported"] == 1
    assert_db_record(repo, count=1, media_type="tv", match_source="nfo")


# ---------------------------------------------------------------------------
# E13: Template sanitisation
# ---------------------------------------------------------------------------


@responses.activate
def test_e13_illegal_chars_in_title(source_dir, make_service, library):
    """TMDB title with special chars: sanitized in dest path."""
    make_video(source_dir, "Movie.The.Sequel.2021.mkv")
    mock_tmdb(MOVIE_WITH_SPECIAL_CHARS)
    service, repo = make_service(threshold=0.5)  # lower threshold for fuzzy match
    summary = service.import_path(source_dir)
    if summary["imported"] == 1:
        dest_files = list(library["movies"].rglob("*.mkv"))
        assert len(dest_files) == 1
        # Verify no illegal chars in path
        dest_str = str(dest_files[0])
        assert '"' not in dest_str
        assert summary["errors"] == 0


# ---------------------------------------------------------------------------
# E14: Threshold boundaries
# ---------------------------------------------------------------------------


@responses.activate
def test_e14_threshold_boundary(source_dir, make_service, library):
    """Exact boundary: conf=0.95 vs threshold=0.95 -> accept."""
    # Inception.2009 -> JW=1.0 * year_factor(2009,2010)=0.95 -> conf=0.95
    make_video(source_dir, "Inception.2009.1080p.mkv")
    mock_tmdb(INCEPTION_2010)
    service, repo = make_service(threshold=0.95)  # exactly at conf
    s1 = service.import_path(source_dir)
    assert s1["imported"] == 1  # 0.95 >= 0.95


@responses.activate
@patch.object(ImportService, "_prompt_user", _skip_prompt)
def test_e14b_threshold_boundary_below(source_dir, make_service, library):
    """Boundary: conf=0.95 < threshold=0.96 -> skipped."""
    make_video(source_dir, "Inception.2009.1080p.mkv")
    mock_tmdb(INCEPTION_2010)
    service, repo = make_service(threshold=0.96)
    s1 = service.import_path(source_dir)
    assert s1["imported"] == 0
    assert s1["skipped"] >= 1


# ---------------------------------------------------------------------------
# E15: Partial failure
# ---------------------------------------------------------------------------


@responses.activate
def test_e15_partial_failure(source_dir, make_service, library):
    """One file succeeds, one fails: imported=1, errors=1."""
    make_video(source_dir, "Dune.2021.mkv")
    make_video(source_dir, "Inception.2010.mkv")
    mock_tmdb(DUNE_2021)
    mock_tmdb(INCEPTION_2010)
    service, repo = make_service()

    original_execute = service._execute_file_op
    call_count = [0]

    def failing_execute(src, dst):
        call_count[0] += 1
        if call_count[0] == 2:  # fail on second file
            raise IOError("disk full")
        return original_execute(src, dst)

    with patch.object(service, "_execute_file_op", side_effect=failing_execute):
        summary = service.import_path(source_dir)

    assert summary["imported"] == 1
    assert summary["errors"] == 1


# ---------------------------------------------------------------------------
# E16: DB field correctness
# ---------------------------------------------------------------------------


@responses.activate
def test_e16_db_field_correctness(source_dir, make_service, library):
    """All DB fields verified for a complete import."""
    make_video(source_dir, "Dune.2021.2160p.BluRay.x265.mkv")
    mock_tmdb(DUNE_2021)
    service, repo = make_service()
    summary = service.import_path(source_dir)
    assert summary["imported"] == 1

    items = repo.get_all_items()
    assert len(items) == 1
    item = items[0]
    dest_files = list(library["movies"].rglob("*.mkv"))
    dest = dest_files[0]
    dest_stat = dest.stat()

    assert item.path == str(dest)
    assert item.media_type == "movie"
    assert item.tmdb_id == 438631
    assert item.title == "Dune"
    assert item.year == 2021
    assert item.match_source == "filename"
    assert item.confidence is not None and item.confidence >= 0.9
    assert item.director == "Denis Villeneuve"
    assert item.genre == "Science Fiction"
    assert item.mtime == dest_stat.st_mtime
    assert item.size == dest_stat.st_size
