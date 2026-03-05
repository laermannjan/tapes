"""Tests for the ReviewApp TUI."""

from __future__ import annotations

from pathlib import Path

from tapes.models import FileEntry, FileMetadata, GroupStatus, ImportGroup
from tapes.ui.app import ReviewApp


def _make_group(title: str, year: int = 2021, n_videos: int = 1, n_companions: int = 0) -> ImportGroup:
    meta = FileMetadata(media_type="movie", title=title, year=year)
    group = ImportGroup(metadata=meta)
    for i in range(n_videos):
        group.add_file(FileEntry(path=Path(f"/fake/{title.lower()}.part{i}.mkv")))
    for i in range(n_companions):
        group.add_file(FileEntry(path=Path(f"/fake/{title.lower()}.part{i}.srt")))
    return group


async def test_get_state_returns_groups():
    groups = [_make_group("Dune"), _make_group("Arrival", year=2016)]
    app = ReviewApp(groups)
    async with app.run_test() as pilot:
        state = app.get_state()
        assert len(state) == 2
        assert state[0].label == "Dune (2021)"
        assert state[1].label == "Arrival (2016)"


async def test_navigation_down_changes_focused_index():
    groups = [_make_group("Dune"), _make_group("Arrival"), _make_group("Blade Runner")]
    app = ReviewApp(groups)
    async with app.run_test() as pilot:
        assert app.focused_index == 0
        await pilot.press("ctrl+down")
        assert app.focused_index == 1
        await pilot.press("ctrl+down")
        assert app.focused_index == 2
        # Should not go past the last group
        await pilot.press("ctrl+down")
        assert app.focused_index == 2


async def test_navigation_up_changes_focused_index():
    groups = [_make_group("Dune"), _make_group("Arrival"), _make_group("Blade Runner")]
    app = ReviewApp(groups)
    async with app.run_test() as pilot:
        # Move down first
        await pilot.press("ctrl+down")
        await pilot.press("ctrl+down")
        assert app.focused_index == 2
        # Now navigate up
        await pilot.press("ctrl+up")
        assert app.focused_index == 1
        await pilot.press("ctrl+up")
        assert app.focused_index == 0
        # Should not go below 0
        await pilot.press("ctrl+up")
        assert app.focused_index == 0


async def test_quit_exits_app():
    groups = [_make_group("Dune")]
    app = ReviewApp(groups)
    async with app.run_test() as pilot:
        await pilot.press("q")


async def test_summary_widget_exists():
    groups = [_make_group("Dune", n_videos=2, n_companions=1)]
    app = ReviewApp(groups)
    async with app.run_test() as pilot:
        summary = app.query_one("#summary")
        assert summary is not None
        rendered = summary.renderable
        assert "1 group(s)" in str(rendered)
        assert "2 video(s)" in str(rendered)
        assert "1 companion(s)" in str(rendered)
