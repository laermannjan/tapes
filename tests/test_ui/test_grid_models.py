"""Tests for grid view models."""
from pathlib import Path
from tapes.models import FileEntry, FileMetadata, ImportGroup
from tapes.ui.models import GridRow, RowKind, RowStatus, build_grid_rows


def _group(title, year=None, season=None, files=None):
    meta = FileMetadata(media_type="movie", title=title, year=year, season=season)
    g = ImportGroup(metadata=meta)
    for f in files or []:
        g.add_file(f)
    return g


def test_build_grid_rows_single_group():
    g = _group("Dune", 2021, files=[
        FileEntry(path=Path("movies/Dune.2021.mkv")),
        FileEntry(path=Path("movies/Dune.2021.en.srt")),
    ])
    rows = build_grid_rows([g])
    assert rows[0].kind == RowKind.FILE
    assert rows[0].entry.role == "video"
    assert rows[1].kind == RowKind.FILE
    assert rows[1].entry.role == "subtitle"
    assert len(rows) == 2


def test_build_grid_rows_multiple_groups_have_separator():
    g1 = _group("Dune", 2021, files=[FileEntry(path=Path("Dune.mkv"))])
    g2 = _group("Arrival", 2016, files=[FileEntry(path=Path("Arrival.mkv"))])
    rows = build_grid_rows([g1, g2])
    assert rows[0].kind == RowKind.FILE
    assert rows[1].kind == RowKind.BLANK
    assert rows[2].kind == RowKind.FILE


def test_grid_row_metadata_uses_entry_then_group():
    meta = FileMetadata(title="Dune", year=2021)
    g = ImportGroup(metadata=meta)
    entry = FileEntry(path=Path("Dune.mkv"), metadata=FileMetadata(title="Dune Override"))
    g.add_file(entry)
    rows = build_grid_rows([g])
    assert rows[0].title == "Dune Override"


def test_grid_row_metadata_falls_back_to_group():
    meta = FileMetadata(title="Dune", year=2021)
    g = ImportGroup(metadata=meta)
    entry = FileEntry(path=Path("Dune.mkv"))
    g.add_file(entry)
    rows = build_grid_rows([g])
    assert rows[0].title == "Dune"
    assert rows[0].year == 2021


def test_episode_groups_same_season_no_blank_between():
    """Sibling episodes (same title+season) cluster without blank rows."""
    ep1_meta = FileMetadata(media_type="episode", title="Breaking Bad", season=1, episode=1)
    ep1 = ImportGroup(metadata=ep1_meta)
    ep1.add_file(FileEntry(path=Path("BB.S01E01.mkv"), metadata=ep1_meta))

    ep2_meta = FileMetadata(media_type="episode", title="Breaking Bad", season=1, episode=2)
    ep2 = ImportGroup(metadata=ep2_meta)
    ep2.add_file(FileEntry(path=Path("BB.S01E02.mkv"), metadata=ep2_meta))

    rows = build_grid_rows([ep1, ep2])
    assert len(rows) == 2
    assert all(r.kind == RowKind.FILE for r in rows)


def test_different_seasons_get_blank_between():
    """Different seasons of same show get blank separator."""
    ep1_meta = FileMetadata(media_type="episode", title="BB", season=1, episode=1)
    ep1 = ImportGroup(metadata=ep1_meta)
    ep1.add_file(FileEntry(path=Path("BB.S01E01.mkv"), metadata=ep1_meta))

    ep2_meta = FileMetadata(media_type="episode", title="BB", season=2, episode=1)
    ep2 = ImportGroup(metadata=ep2_meta)
    ep2.add_file(FileEntry(path=Path("BB.S02E01.mkv"), metadata=ep2_meta))

    rows = build_grid_rows([ep1, ep2])
    assert len(rows) == 3
    assert rows[1].kind == RowKind.BLANK


def test_different_shows_get_blank_between():
    """Different shows get blank separator even with same season number."""
    ep1_meta = FileMetadata(media_type="episode", title="BB", season=1, episode=1)
    ep1 = ImportGroup(metadata=ep1_meta)
    ep1.add_file(FileEntry(path=Path("BB.S01E01.mkv"), metadata=ep1_meta))

    ep2_meta = FileMetadata(media_type="episode", title="Office", season=1, episode=1)
    ep2 = ImportGroup(metadata=ep2_meta)
    ep2.add_file(FileEntry(path=Path("Office.S01E01.mkv"), metadata=ep2_meta))

    rows = build_grid_rows([ep1, ep2])
    assert len(rows) == 3
    assert rows[1].kind == RowKind.BLANK


def test_movie_and_episode_get_blank_between():
    """Movie followed by episodes gets blank separator."""
    movie_meta = FileMetadata(media_type="movie", title="Dune", year=2021)
    movie = ImportGroup(metadata=movie_meta)
    movie.add_file(FileEntry(path=Path("Dune.mkv"), metadata=movie_meta))

    ep_meta = FileMetadata(media_type="episode", title="BB", season=1, episode=1)
    ep = ImportGroup(metadata=ep_meta)
    ep.add_file(FileEntry(path=Path("BB.S01E01.mkv"), metadata=ep_meta))

    rows = build_grid_rows([movie, ep])
    assert len(rows) == 3
    assert rows[1].kind == RowKind.BLANK


def test_match_row_holds_proposed_fields():
    match_row = GridRow(
        kind=RowKind.MATCH,
        group=ImportGroup(metadata=FileMetadata(title="Dune")),
        match_fields={"title": "Dune: Part One", "year": 2021},
        match_confidence=0.75,
    )
    assert match_row.match_fields["title"] == "Dune: Part One"
    assert match_row.match_confidence == 0.75


def test_no_match_row():
    no_match = GridRow(kind=RowKind.NO_MATCH, group=ImportGroup(metadata=FileMetadata()))
    assert no_match.kind == RowKind.NO_MATCH
