"""Tests for grid row rendering."""
from pathlib import Path

from rich.text import Text

from tapes.models import FileEntry, FileMetadata, ImportGroup
from tapes.ui.models import GridRow, RowKind, RowStatus
from tapes.ui.render import render_row, render_dest_row, COL_WIDTHS, FIELD_COLS


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


def test_render_match_subrow():
    match_row = GridRow(
        kind=RowKind.MATCH,
        group=ImportGroup(metadata=FileMetadata(title="Breaking Bad")),
        match_fields={"title": "Breaking Bad", "year": 2008, "episode_title": "Pilot"},
    )
    text = render_row(match_row, cursor_col=0, is_cursor_row=False)
    plain = text.plain
    assert "(match)" in plain
    assert "Breaking Bad" in plain
    assert "2008" in plain
    assert "Pilot" in plain


def test_render_no_match_subrow():
    no_match_row = GridRow(
        kind=RowKind.NO_MATCH,
        group=ImportGroup(metadata=FileMetadata()),
    )
    text = render_row(no_match_row, cursor_col=0, is_cursor_row=False)
    plain = text.plain
    assert "(no match)" in plain


def test_render_dest_row_valid_path():
    row = _file_row("movies/Dune.mkv", title="Dune", year=2021)
    text = render_dest_row(
        row, is_cursor_row=False, operation="copy",
        dest_path="Dune (2021)/Dune (2021).mkv", missing=None,
    )
    assert "copy" in text.plain
    assert "Dune.mkv" in text.plain
    assert "Dune (2021)/Dune (2021).mkv" in text.plain


def test_render_dest_row_missing_fields():
    row = _file_row("test.mkv", title="Test")
    text = render_dest_row(
        row, is_cursor_row=False, operation="copy",
        dest_path=None, missing=["year"],
    )
    assert "copy" in text.plain
    assert "(missing:" in text.plain
    assert "year" in text.plain


def test_render_dest_row_skipped():
    row = _file_row("test.mkv", title="Test")
    text = render_dest_row(
        row, is_cursor_row=False, operation="skip",
        dest_path=None, missing=None, skipped=True,
    )
    assert "skip" in text.plain
    assert "(skipped)" in text.plain


def test_render_dest_row_with_unknown():
    row = _file_row("test.mkv", title="Test")
    text = render_dest_row(
        row, is_cursor_row=False, operation="copy",
        dest_path="Test (unknown)/Test (unknown).mkv",
        missing=None, unknown_fields=["year"],
    )
    assert "copy" in text.plain
    assert "unknown" in text.plain


def test_render_dest_row_cursor_highlight():
    row = _file_row("test.mkv", title="Test", year=2021)
    text = render_dest_row(
        row, is_cursor_row=True, operation="copy",
        dest_path="Test (2021)/Test (2021).mkv", missing=None,
    )
    # Should render without error, with row cursor bg
    assert "Test (2021)" in text.plain


def test_render_dest_match_row():
    group = ImportGroup(metadata=FileMetadata(title="Test"))
    row = GridRow(
        kind=RowKind.MATCH, group=group,
        match_fields={"title": "Test", "year": 2021},
    )
    text = render_dest_row(
        row, is_cursor_row=False, operation="copy",
        dest_path="Test (2021)/Test (2021).mkv", missing=None,
    )
    assert "(match)" in text.plain
    assert "Test (2021)" in text.plain


def test_render_dest_blank_row():
    row = GridRow(kind=RowKind.BLANK)
    text = render_dest_row(
        row, is_cursor_row=False, operation="",
        dest_path=None, missing=None,
    )
    assert text.plain.strip() == ""


def test_render_dest_no_match_row():
    group = ImportGroup(metadata=FileMetadata(title="X"))
    row = GridRow(kind=RowKind.NO_MATCH, group=group)
    text = render_dest_row(
        row, is_cursor_row=False, operation="",
        dest_path=None, missing=None,
    )
    assert "(no match)" in text.plain
