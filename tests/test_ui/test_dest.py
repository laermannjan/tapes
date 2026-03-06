"""Tests for destination path computation."""
from tapes.ui.dest import compute_dest_path, missing_template_fields, compute_dest_path_with_unknown
from tapes.ui.models import GridRow, RowKind
from tapes.models import FileEntry, FileMetadata, ImportGroup
from pathlib import Path


def _row(path, title=None, year=None, season=None, episode=None,
         episode_title=None, media_type="movie"):
    meta = FileMetadata(
        title=title, year=year, season=season, episode=episode,
        media_type=media_type,
    )
    group = ImportGroup(metadata=meta)
    entry = FileEntry(path=Path(path), metadata=meta)
    group.add_file(entry)
    row = GridRow(kind=RowKind.FILE, entry=entry, group=group)
    if episode_title is not None:
        row.set_field("episode_title", episode_title)
    return row


def test_movie_dest_path():
    row = _row("Dune.2021.mkv", title="Dune", year=2021)
    template = "{title} ({year})/{title} ({year}).{ext}"
    result = compute_dest_path(row, template)
    assert result == "Dune (2021)/Dune (2021).mkv"


def test_tv_dest_path():
    row = _row("bb.s01e01.mkv", title="Breaking Bad", year=2008,
               season=1, episode=1, episode_title="Pilot", media_type="episode")
    template = (
        "{title} ({year})/Season {season:02d}/"
        "{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"
    )
    result = compute_dest_path(row, template)
    assert result == "Breaking Bad (2008)/Season 01/Breaking Bad - S01E01 - Pilot.mkv"


def test_missing_fields_returns_none():
    row = _row("test.mkv", title="Test")  # missing year
    template = "{title} ({year})/{title} ({year}).{ext}"
    result = compute_dest_path(row, template)
    assert result is None


def test_missing_fields_list():
    row = _row("test.mkv", title="Test")  # missing year
    template = "{title} ({year})/{title} ({year}).{ext}"
    missing = missing_template_fields(row, template)
    assert missing == ["year"]


def test_missing_fields_episode():
    row = _row("test.mkv", title="Test", year=2020, season=1, episode=1,
               media_type="episode")  # missing episode_title
    template = "{title} - S{season:02d}E{episode:02d} - {episode_title}.{ext}"
    missing = missing_template_fields(row, template)
    assert missing == ["episode_title"]


def test_fill_unknown():
    row = _row("test.mkv", title="Test")
    template = "{title} ({year})/{title} ({year}).{ext}"
    result = compute_dest_path_with_unknown(row, template)
    assert result == "Test (unknown)/Test (unknown).mkv"
