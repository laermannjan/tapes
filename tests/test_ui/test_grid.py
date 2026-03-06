"""Tests for the grid Textual app."""
from pathlib import Path

from tapes.models import FileEntry, FileMetadata, ImportGroup
from tapes.ui.grid import GridApp


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


async def test_selection_extends_on_arrow():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        # rows: 0=Dune.mkv 1=Dune.en.srt 2=Dune.de.srt 3=BLANK 4=Arrival.mkv 5=Arrival.en.srt
        await pilot.press("v")
        assert app.selection == {(0, 0)}
        await pilot.press("down")
        assert app.selection == {(0, 0), (1, 0)}


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
        # Select row 0
        await pilot.press("v")
        assert app.selection == {(0, 0)}
        # Move down two rows (selection extends)
        await pilot.press("down")
        await pilot.press("down")
        assert app.cursor_row == 2
        # Both rows 0, 1, 2 are selected (extended via arrow)
        assert app.selection == {(0, 0), (1, 0), (2, 0)}
        # Press v to deselect row 2 (non-adjacent: rows 0 and 1 remain)
        await pilot.press("v")
        assert app.selection == {(0, 0), (1, 0)}
        # Press v again to re-add row 2
        await pilot.press("v")
        assert app.selection == {(0, 0), (1, 0), (2, 0)}


async def test_selection_locks_column():
    app = GridApp(_groups())
    async with app.run_test() as pilot:
        await pilot.press("v")
        assert app.selection == {(0, 0)}
        # Moving right should clear the selection
        await pilot.press("right")
        assert app.selection == set()
        assert app.cursor_col == 1
