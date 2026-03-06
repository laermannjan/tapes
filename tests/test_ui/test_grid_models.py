"""Tests for grid view models."""
from pathlib import Path
from tapes.models import FileEntry, FileMetadata, ImportGroup
from tapes.ui.models import GridRow, RowKind, build_grid_rows


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
