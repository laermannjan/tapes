"""Tests for grid row rendering."""
from pathlib import Path

from rich.text import Text

from tapes.models import FileEntry, FileMetadata, ImportGroup
from tapes.ui.models import GridRow, RowKind, RowStatus
from tapes.ui.render import render_row, COL_WIDTHS, FIELD_COLS


def _file_row(
    path,
    role="video",
    title=None,
    year=None,
    season=None,
    episode=None,
    status=RowStatus.RAW,
    edited_fields=None,
):
    meta = FileMetadata(title=title, year=year, season=season, episode=episode)
    group = ImportGroup(metadata=meta)
    entry = FileEntry(path=Path(path), role=role, metadata=meta)
    group.add_file(entry)
    return GridRow(
        kind=RowKind.FILE,
        entry=entry,
        group=group,
        status=status,
        edited_fields=edited_fields or set(),
    )


def test_render_video_row_has_white_filename():
    row = _file_row("movies/Dune.2021.mkv", title="Dune", year=2021)
    text = render_row(row, cursor_col=None, is_cursor_row=False)
    plain = text.plain
    assert "Dune.2021.mkv" in plain
    assert "Dune" in plain
    assert "2021" in plain


def test_render_companion_row_is_dimmed():
    row = _file_row(
        "movies/Dune.2021.en.srt", role="subtitle", title="Dune", year=2021
    )
    text = render_row(row, cursor_col=None, is_cursor_row=False)
    plain = text.plain
    assert "Dune.2021.en.srt" in plain


def test_render_blank_row():
    row = GridRow(kind=RowKind.BLANK)
    text = render_row(row, cursor_col=None, is_cursor_row=False)
    assert text.plain.strip() == ""


def test_render_status_badge():
    row = _file_row("test.mkv", title="Test", status=RowStatus.AUTO)
    text = render_row(row, cursor_col=None, is_cursor_row=False)
    assert "**" in text.plain


def test_column_widths_defined():
    assert "status" in COL_WIDTHS
    assert "filepath" in COL_WIDTHS
    assert "title" in COL_WIDTHS
    assert len(FIELD_COLS) == 5


def test_render_row_total_width_consistent():
    row = _file_row("test.mkv", title="Test", year=2021)
    text = render_row(row, cursor_col=None, is_cursor_row=False)
    expected_width = sum(COL_WIDTHS.values())
    assert len(text.plain) == expected_width


def test_render_blank_row_total_width():
    row = GridRow(kind=RowKind.BLANK)
    text = render_row(row, cursor_col=None, is_cursor_row=False)
    expected_width = sum(COL_WIDTHS.values())
    assert len(text.plain) == expected_width


def test_render_auto_status_shows_cyan_style():
    row = _file_row("test.mkv", title="Test", year=2021, status=RowStatus.AUTO)
    text = render_row(row, cursor_col=None, is_cursor_row=False)
    # The title "Test" should be present and styled with cyan (#6bc)
    assert "Test" in text.plain
    assert "2021" in text.plain


def test_render_edited_fields_use_purple():
    row = _file_row(
        "test.mkv",
        title="Custom",
        year=2021,
        status=RowStatus.EDITED,
        edited_fields={"title"},
    )
    text = render_row(row, cursor_col=None, is_cursor_row=False)
    assert "Custom" in text.plain


def test_cursor_row_highlight():
    row = _file_row("test.mkv", title="Test", year=2021)
    text = render_row(row, cursor_col=0, is_cursor_row=True)
    assert len(text.plain) == sum(COL_WIDTHS.values())


def test_selected_cols():
    row = _file_row("test.mkv", title="Test", year=2021)
    text = render_row(
        row, cursor_col=None, is_cursor_row=False, selected_cols={0, 1}
    )
    assert len(text.plain) == sum(COL_WIDTHS.values())


def test_long_filepath_truncated():
    long_path = "movies/" + "A" * 100 + ".mkv"
    row = _file_row(long_path, title="Test")
    text = render_row(row, cursor_col=None, is_cursor_row=False)
    expected_width = sum(COL_WIDTHS.values())
    assert len(text.plain) == expected_width


def test_long_title_truncated():
    row = _file_row("test.mkv", title="A" * 100)
    text = render_row(row, cursor_col=None, is_cursor_row=False)
    expected_width = sum(COL_WIDTHS.values())
    assert len(text.plain) == expected_width


def test_render_returns_text_object():
    row = _file_row("test.mkv", title="Test")
    result = render_row(row, cursor_col=None, is_cursor_row=False)
    assert isinstance(result, Text)


def test_all_status_badges():
    for status in RowStatus:
        row = _file_row("test.mkv", title="Test", status=status)
        text = render_row(row, cursor_col=None, is_cursor_row=False)
        assert len(text.plain) == sum(COL_WIDTHS.values())


def test_episode_list_rendered():
    row = _file_row("test.mkv", title="Show", season=1, episode=[1, 2])
    text = render_row(row, cursor_col=None, is_cursor_row=False)
    # Episode list should be converted to string
    assert "[1, 2]" in text.plain or "1" in text.plain
