"""End-to-end tests for companion file handling (D1-D8)."""

import os

import responses

from tests.test_e2e.conftest import assert_imported, make_video
from tests.test_e2e.tmdb_fixtures import DUNE_2021, mock_tmdb


def _make_file(directory, name, content=b"dummy content"):
    """Create a non-video file with given content."""
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


# ---------------------------------------------------------------------------
# D1: Subtitle with language tag
# ---------------------------------------------------------------------------


@responses.activate
def test_d1_subtitle_with_lang_tag(source_dir, library, make_service):
    """Dune.2021.1080p.en.srt -- language tag preserved in renamed subtitle."""
    video = make_video(source_dir, "Dune.2021.1080p.mkv")
    srt = _make_file(source_dir, "Dune.2021.1080p.en.srt")
    mock_tmdb(DUNE_2021)

    service, repo = make_service()
    summary = service.import_path(source_dir)

    assert summary["imported"] == 1
    assert summary["errors"] == 0

    assert_imported(
        library["movies"],
        "Dune (2021)/Dune (2021).mkv",
        source=video,
        mode="copy",
    )

    dest_srt = library["movies"] / "Dune (2021)" / "Dune (2021).en.srt"
    assert dest_srt.exists(), f"Expected subtitle at {dest_srt}"


# ---------------------------------------------------------------------------
# D2: Multiple subtitle languages
# ---------------------------------------------------------------------------


@responses.activate
def test_d2_multiple_subtitle_languages(source_dir, library, make_service):
    """Multiple .srt files with different language tags all renamed and moved."""
    make_video(source_dir, "Dune.2021.mkv")
    _make_file(source_dir, "Dune.2021.en.srt")
    _make_file(source_dir, "Dune.2021.de.srt")
    _make_file(source_dir, "Dune.2021.fr.srt")
    mock_tmdb(DUNE_2021)

    service, repo = make_service()
    summary = service.import_path(source_dir)

    assert summary["imported"] == 1

    for lang in ("en", "de", "fr"):
        dest = library["movies"] / "Dune (2021)" / f"Dune (2021).{lang}.srt"
        assert dest.exists(), f"Expected subtitle {dest}"


# ---------------------------------------------------------------------------
# D3: NFO companion (without tmdbid tag)
# ---------------------------------------------------------------------------


@responses.activate
def test_d3_nfo_companion(source_dir, library, make_service):
    """NFO without <tmdbid> is treated as companion, renamed alongside video."""
    make_video(source_dir, "Dune.2021.mkv")
    _make_file(
        source_dir,
        "Dune.2021.nfo",
        content=b"<movie><title>Dune</title></movie>",
    )
    mock_tmdb(DUNE_2021)

    service, repo = make_service()
    summary = service.import_path(source_dir)

    assert summary["imported"] == 1

    dest_nfo = library["movies"] / "Dune (2021)" / "Dune (2021).nfo"
    assert dest_nfo.exists(), f"Expected NFO at {dest_nfo}"


# ---------------------------------------------------------------------------
# D4: Artwork files
# ---------------------------------------------------------------------------


@responses.activate
def test_d4_artwork_files(source_dir, library, make_service):
    """poster.jpg and fanart.jpg keep original names when moved alongside video."""
    subdir = source_dir / "Dune.2021"
    subdir.mkdir()
    make_video(subdir, "Dune.2021.mkv")
    _make_file(subdir, "poster.jpg")
    _make_file(subdir, "fanart.jpg")
    mock_tmdb(DUNE_2021)

    service, repo = make_service()
    summary = service.import_path(source_dir)

    assert summary["imported"] == 1

    dest_dir = library["movies"] / "Dune (2021)"
    assert (dest_dir / "poster.jpg").exists(), "poster.jpg should be moved"
    assert (dest_dir / "fanart.jpg").exists(), "fanart.jpg should be moved"


# ---------------------------------------------------------------------------
# D5: Sample file excluded by scanner
# ---------------------------------------------------------------------------


@responses.activate
def test_d5_sample_file_excluded(source_dir, library, make_service):
    """sample-Dune.2021.mkv excluded by discovery scanner, not imported."""
    subdir = source_dir / "Dune.2021"
    subdir.mkdir()
    make_video(subdir, "Dune.2021.mkv")
    # This is a .mkv so the scanner's sample pattern excludes it
    make_video(subdir, "sample-Dune.2021.mkv", size=512)
    mock_tmdb(DUNE_2021)

    service, repo = make_service()
    summary = service.import_path(source_dir)

    assert summary["imported"] == 1

    # Only the main video should be in the library
    all_files = [f for f in library["movies"].rglob("*") if f.is_file()]
    mkv_files = [f for f in all_files if f.suffix == ".mkv"]
    assert len(mkv_files) == 1, f"Expected 1 mkv, got {mkv_files}"
    assert "sample" not in mkv_files[0].name.lower()


# ---------------------------------------------------------------------------
# D6: Companion in subdirectory -- relative path preserved
# ---------------------------------------------------------------------------


@responses.activate
def test_d6_companion_in_subdirectory(source_dir, library, make_service):
    """Subs/Dune.2021.en.srt preserves subdirectory structure in library."""
    subdir = source_dir / "Dune.2021"
    subdir.mkdir()
    make_video(subdir, "Dune.2021.mkv")
    _make_file(subdir / "Subs", "Dune.2021.en.srt")
    mock_tmdb(DUNE_2021)

    service, repo = make_service()
    summary = service.import_path(source_dir)

    assert summary["imported"] == 1

    dest_srt = library["movies"] / "Dune (2021)" / "Subs" / "Dune (2021).en.srt"
    assert dest_srt.exists(), f"Expected subtitle at {dest_srt}"


# ---------------------------------------------------------------------------
# D7: Companion move mode -- sources deleted
# ---------------------------------------------------------------------------


@responses.activate
def test_d7_companion_move_mode(source_dir, library, make_service):
    """In move mode, both video and subtitle sources are deleted."""
    video = make_video(source_dir, "Dune.2021.mkv")
    srt = _make_file(source_dir, "Dune.2021.en.srt")
    mock_tmdb(DUNE_2021)

    service, repo = make_service(mode="move")
    summary = service.import_path(source_dir)

    assert summary["imported"] == 1

    # Sources deleted
    assert not video.exists(), "Video source should be deleted in move mode"
    assert not srt.exists(), "Subtitle source should be deleted in move mode"

    # Destinations exist
    assert_imported(
        library["movies"],
        "Dune (2021)/Dune (2021).mkv",
    )
    dest_srt = library["movies"] / "Dune (2021)" / "Dune (2021).en.srt"
    assert dest_srt.exists(), f"Expected subtitle at {dest_srt}"


# ---------------------------------------------------------------------------
# D8: Companion link mode -- symlinks created
# ---------------------------------------------------------------------------


@responses.activate
def test_d8_companion_link_mode(source_dir, library, make_service):
    """In link mode, companions are symlinked; sources still exist."""
    video = make_video(source_dir, "Dune.2021.mkv")
    srt = _make_file(source_dir, "Dune.2021.en.srt")
    mock_tmdb(DUNE_2021)

    service, repo = make_service(mode="link")
    summary = service.import_path(source_dir)

    assert summary["imported"] == 1

    # Sources still exist
    assert video.exists(), "Video source should still exist in link mode"
    assert srt.exists(), "Subtitle source should still exist in link mode"

    # Destinations are symlinks
    dest_video = library["movies"] / "Dune (2021)" / "Dune (2021).mkv"
    dest_srt = library["movies"] / "Dune (2021)" / "Dune (2021).en.srt"
    assert dest_video.is_symlink(), "Video should be a symlink in link mode"
    assert dest_srt.is_symlink(), "Subtitle should be a symlink in link mode"
