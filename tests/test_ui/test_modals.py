"""Tests for TUI modals: split, merge, file editor."""

from __future__ import annotations

from pathlib import Path

from tapes.models import FileEntry, FileMetadata, ImportGroup
from tapes.ui.app import ReviewApp


def _make_group(
    title: str, year: int = 2021, n_videos: int = 1, n_companions: int = 0
) -> ImportGroup:
    meta = FileMetadata(media_type="movie", title=title, year=year)
    group = ImportGroup(metadata=meta)
    for i in range(n_videos):
        group.add_file(FileEntry(path=Path(f"/fake/{title.lower()}.part{i}.mkv")))
    for i in range(n_companions):
        group.add_file(FileEntry(path=Path(f"/fake/{title.lower()}.sub{i}.srt")))
    return group


# -- Split modal -----------------------------------------------------------


async def test_split_modal_opens_and_closes():
    """Press p to open split modal, then escape to cancel. State unchanged."""
    groups = [_make_group("Dune", n_videos=2)]
    app = ReviewApp(groups)
    async with app.run_test() as pilot:
        original_files = [f.path for f in app.get_state()[0].files]
        await pilot.press("p")
        await pilot.press("escape")
        state = app.get_state()
        assert len(state) == 1
        assert [f.path for f in state[0].files] == original_files


async def test_split_modal_no_open_single_file():
    """Split should not open when group has only one file."""
    groups = [_make_group("Dune", n_videos=1)]
    app = ReviewApp(groups)
    async with app.run_test() as pilot:
        await pilot.press("p")
        # No modal should be open; state unchanged
        state = app.get_state()
        assert len(state) == 1


async def test_split_modal_confirm_creates_new_group():
    """Select a file and confirm to create a new group."""
    groups = [_make_group("Dune", n_videos=2, n_companions=1)]
    app = ReviewApp(groups)
    async with app.run_test() as pilot:
        assert len(app.get_state()) == 1
        await pilot.press("p")
        # Toggle first file
        await pilot.press("space")
        await pilot.press("enter")
        state = app.get_state()
        assert len(state) == 2
        # Total files should be preserved
        total = sum(len(g.files) for g in state)
        assert total == 3


# -- Merge modal -----------------------------------------------------------


async def test_merge_modal_opens_and_closes():
    """Press j to open merge modal, then escape to cancel. State unchanged."""
    groups = [_make_group("Dune"), _make_group("Arrival")]
    app = ReviewApp(groups)
    async with app.run_test() as pilot:
        await pilot.press("j")
        await pilot.press("escape")
        state = app.get_state()
        assert len(state) == 2


async def test_merge_modal_no_open_single_group():
    """Merge should not open when there is only one group."""
    groups = [_make_group("Dune")]
    app = ReviewApp(groups)
    async with app.run_test() as pilot:
        await pilot.press("j")
        state = app.get_state()
        assert len(state) == 1


async def test_merge_modal_confirm_merges_groups():
    """Select a group and confirm to merge into focused group."""
    g1 = _make_group("Dune", n_videos=1)
    g2 = _make_group("Arrival", n_videos=1)
    app = ReviewApp([g1, g2])
    async with app.run_test() as pilot:
        assert len(app.get_state()) == 2
        await pilot.press("j")
        # Toggle first (only) other group
        await pilot.press("space")
        await pilot.press("enter")
        state = app.get_state()
        # Arrival merged into Dune; empty Arrival removed
        assert len(state) == 1
        assert len(state[0].files) == 2


# -- File editor modal ----------------------------------------------------


async def test_file_editor_opens_and_closes():
    """Press e to open file editor, then escape to cancel. State unchanged."""
    groups = [_make_group("Dune"), _make_group("Arrival")]
    app = ReviewApp(groups)
    async with app.run_test() as pilot:
        await pilot.press("e")
        await pilot.press("escape")
        state = app.get_state()
        assert len(state) == 2


async def test_file_editor_move_file():
    """Select a file from another group and confirm to move it."""
    g1 = _make_group("Dune", n_videos=1)
    g2 = _make_group("Arrival", n_videos=2)
    app = ReviewApp([g1, g2])
    async with app.run_test() as pilot:
        await pilot.press("e")
        # Toggle first file from the other group
        await pilot.press("space")
        await pilot.press("enter")
        state = app.get_state()
        # File moved from Arrival to Dune
        assert len(state[0].files) == 2
        # Arrival should still have 1 file
        assert len(state[1].files) == 1
