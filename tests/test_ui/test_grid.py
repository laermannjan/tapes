"""Tests for the grid Textual app."""
from pathlib import Path

from tapes.models import FileEntry, FileMetadata, ImportGroup
from tapes.ui.grid import GridApp
from tapes.ui.models import RowStatus
from tapes.ui.render import FIELD_COLS


def _groups():
    dune_meta = FileMetadata(title="Dune", year=2021, media_type="movie")
    dune = ImportGroup(metadata=dune_meta)
    dune.add_file(
        FileEntry(path=Path("movies/Dune.2021.2160p.BluRay.x265.mkv"), metadata=dune_meta)
    )
    dune.add_file(FileEntry(path=Path("movies/Dune.2021.en.srt")))
    dune.add_file(FileEntry(path=Path("movies/Dune.2021.de.srt")))

    arr_meta = FileMetadata(title="Arrival", year=2016, media_type="movie")
    arrival = ImportGroup(metadata=arr_meta)
    arrival.add_file(
        FileEntry(path=Path("movies/Arrival.2016.1080p.WEB-DL.mkv"), metadata=arr_meta)
    )
    arrival.add_file(FileEntry(path=Path("movies/Arrival.2016.en.srt")))

    return [dune, arrival]


async def test_grid_app_starts():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        assert app.cursor_row == 0
        assert app.cursor_col == 0


async def test_cursor_moves_down_skips_blanks():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        # rows: 0=Dune.mkv 1=Dune.en.srt 2=Dune.de.srt 3=BLANK 4=Arrival.mkv 5=Arrival.en.srt
        assert app.cursor_row == 0  # Dune.mkv
        await pilot.press("down")
        assert app.cursor_row == 1  # Dune.en.srt
        await pilot.press("down")
        assert app.cursor_row == 2  # Dune.de.srt
        await pilot.press("down")
        assert app.cursor_row == 4  # Arrival.mkv (skipped blank at 3)
        await pilot.press("down")
        assert app.cursor_row == 5  # Arrival.en.srt


async def test_cursor_moves_up_skips_blanks():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        # rows: 0=Dune.mkv 1=Dune.en.srt 2=Dune.de.srt 3=BLANK 4=Arrival.mkv 5=Arrival.en.srt
        for _ in range(3):
            await pilot.press("down")
        assert app.cursor_row == 4  # Arrival.mkv (skipped blank at 3)
        await pilot.press("up")
        assert app.cursor_row == 2  # Dune.de.srt (skipped blank at 3)


async def test_cursor_moves_right_left():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        assert app.cursor_col == 0  # title
        await pilot.press("right")
        assert app.cursor_col == 1  # year
        await pilot.press("right")
        assert app.cursor_col == 2  # season
        await pilot.press("left")
        assert app.cursor_col == 1  # year
        await pilot.press("left")
        assert app.cursor_col == 0  # title


async def test_cursor_clamps_at_edges():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        await pilot.press("left")
        assert app.cursor_col == 0
        await pilot.press("up")
        assert app.cursor_row == 0


async def test_v_toggles_selection():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        assert app.selection == set()
        await pilot.press("v")
        assert app.selection == {(0, 0)}


async def test_v_toggle_deselects():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        await pilot.press("v")
        assert app.selection == {(0, 0)}
        await pilot.press("v")
        assert app.selection == set()


async def test_arrow_does_not_extend_selection():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        await pilot.press("v")
        assert app.selection == {(0, 0)}
        await pilot.press("down")
        # Arrow moves cursor but does not add to selection
        assert app.selection == {(0, 0)}
        assert app.cursor_row == 1


async def test_esc_clears_selection():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        await pilot.press("v")
        assert app.selection == {(0, 0)}
        await pilot.press("escape")
        assert app.selection == set()


async def test_non_adjacent_selection():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        # rows: 0=Dune.mkv 1=Dune.en.srt 2=Dune.de.srt 3=BLANK 4=Arrival.mkv 5=Arrival.en.srt
        await pilot.press("v")
        assert app.selection == {(0, 0)}
        # Move down two rows, then toggle row 2
        await pilot.press("down")
        await pilot.press("down")
        assert app.cursor_row == 2
        await pilot.press("v")
        assert app.selection == {(0, 0), (2, 0)}
        # Deselect row 2
        await pilot.press("v")
        assert app.selection == {(0, 0)}


async def test_selection_locks_column():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        await pilot.press("v")
        assert app.selection == {(0, 0)}
        # Moving right is blocked while selection is active
        await pilot.press("right")
        assert app.selection == {(0, 0)}
        assert app.cursor_col == 0


# --- Edit mode tests (M3) ---


async def test_e_enters_edit_mode():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        assert not app.editing
        await pilot.press("e")
        assert app.editing


async def test_edit_confirm_updates_field():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        # Cursor on row 0 (Dune), col 0 (title)
        assert app._rows[0].title == "Dune"
        await pilot.press("e")
        assert app.editing
        # Set edit buffer directly and confirm
        app._edit_buffer = "Dune 2"
        await pilot.press("enter")
        assert not app.editing
        assert app._rows[0].title == "Dune 2"


async def test_edit_cancel_preserves_field():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        assert app._rows[0].title == "Dune"
        await pilot.press("e")
        assert app.editing
        app._edit_buffer = "Changed"
        await pilot.press("escape")
        assert not app.editing
        assert app._rows[0].title == "Dune"


async def test_edit_sets_status_edited():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        assert app._rows[0].status == RowStatus.RAW
        await pilot.press("e")
        app._edit_buffer = "New Title"
        await pilot.press("enter")
        assert app._rows[0].status == RowStatus.EDITED


async def test_edit_tracks_edited_fields():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        assert "title" not in app._rows[0].edited_fields
        await pilot.press("e")
        app._edit_buffer = "New Title"
        await pilot.press("enter")
        assert "title" in app._rows[0].edited_fields


async def test_edit_year_converts_to_int():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        # Move cursor to year column (col 1)
        await pilot.press("right")
        assert app.cursor_col == 1
        await pilot.press("e")
        app._edit_buffer = "2025"
        await pilot.press("enter")
        assert app._rows[0].year == 2025
        assert isinstance(app._rows[0].year, int)


async def test_edit_invalid_int_cancels_silently():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        # Move cursor to year column
        await pilot.press("right")
        await pilot.press("e")
        app._edit_buffer = "not-a-number"
        await pilot.press("enter")
        assert not app.editing
        # Year should remain unchanged
        assert app._rows[0].year == 2021
        assert app._rows[0].status == RowStatus.RAW


async def test_edit_selected_cells():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        # rows: 0=Dune.mkv 1=Dune.en.srt 2=Dune.de.srt 3=BLANK 4=Arrival.mkv
        # Select rows 0 and 4 (both video files) on title column
        await pilot.press("v")  # select row 0
        await pilot.press("down")
        await pilot.press("down")
        await pilot.press("down")  # row 4 (Arrival)
        await pilot.press("v")  # select row 4
        assert app.selection == {(0, 0), (4, 0)}

        await pilot.press("e")
        app._edit_buffer = "Shared Title"
        await pilot.press("enter")

        assert app._rows[0].title == "Shared Title"
        assert app._rows[4].title == "Shared Title"
        assert app._rows[0].status == RowStatus.EDITED
        assert app._rows[4].status == RowStatus.EDITED
        assert "title" in app._rows[0].edited_fields
        assert "title" in app._rows[4].edited_fields
        # Selection should be cleared after edit
        assert app.selection == set()


# --- Query mode tests (M4) ---


async def test_q_queries_and_auto_accepts():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        # Row 0 is Dune.mkv, title="Dune"
        assert app._rows[0].status == RowStatus.RAW
        await pilot.press("q")
        assert app._rows[0].status == RowStatus.AUTO
        assert app._rows[0].title == "Dune"
        assert app._rows[0].year == 2021


async def test_q_no_match_stays_raw():
    # Create a group with a title not in the mock TMDB DB
    meta = FileMetadata(title="Unknown Movie", year=2020, media_type="movie")
    group = ImportGroup(metadata=meta)
    group.add_file(FileEntry(path=Path("movies/Unknown.Movie.2020.mkv"), metadata=meta))
    app = GridApp([group])
    async with app.run_test() as pilot:
        assert app._rows[0].title == "Unknown Movie"
        assert app._rows[0].status == RowStatus.RAW
        await pilot.press("q")
        assert app._rows[0].status == RowStatus.RAW


async def test_q_queries_selected_rows():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        # rows: 0=Dune.mkv 1=Dune.en.srt 2=Dune.de.srt 3=BLANK 4=Arrival.mkv
        # Select row 0 and row 4
        await pilot.press("v")  # select row 0
        await pilot.press("down", "down", "down")  # row 4
        await pilot.press("v")  # select row 4
        assert app.selection == {(0, 0), (4, 0)}

        await pilot.press("q")

        assert app._rows[0].status == RowStatus.AUTO
        assert app._rows[0].title == "Dune"
        assert app._rows[0].year == 2021
        assert app._rows[4].status == RowStatus.AUTO
        assert app._rows[4].title == "Arrival"
        assert app._rows[4].year == 2016
        # Selection should be cleared
        assert app.selection == set()


async def test_q_blocked_during_edit():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        await pilot.press("e")
        assert app.editing
        await pilot.press("q")
        # Should still be editing, row unchanged
        assert app.editing
        assert app._rows[0].status == RowStatus.RAW


# --- Freeze tests ---


async def test_f_freezes_cursor_cell():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        await pilot.press("f")
        assert "title" in app._rows[0].frozen_fields


async def test_frozen_field_blocks_edit():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        await pilot.press("f")  # freeze title
        await pilot.press("e")
        app._edit_buffer = "New"
        await pilot.press("enter")
        assert app._rows[0].title == "Dune"  # unchanged


async def test_frozen_field_blocks_query():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        # Freeze title on row 0, then query
        await pilot.press("f")
        assert "title" in app._rows[0].frozen_fields
        original_title = app._rows[0].title
        await pilot.press("q")
        # Title should not change (frozen), but year should update
        assert app._rows[0].title == original_title


async def test_shift_f_freezes_entire_row():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        await pilot.press("F")
        for field in ["title", "year", "season", "episode", "episode_title"]:
            assert field in app._rows[0].frozen_fields


async def test_esc_clears_freeze_not():
    # Esc clears selection, not freeze state
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        await pilot.press("f")
        assert "title" in app._rows[0].frozen_fields
        await pilot.press("escape")
        assert "title" in app._rows[0].frozen_fields  # still frozen
