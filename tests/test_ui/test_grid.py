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
