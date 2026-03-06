"""Tests for the Shift+E edit modal."""
import pytest
from pathlib import Path

from tapes.models import ImportGroup, FileEntry, FileMetadata
from tapes.ui.models import GridRow, RowKind, build_grid_rows
from tapes.ui.edit_modal import EditModal
from tapes.ui.render import FIELD_COLS


def _single_row():
    """A single movie file row."""
    meta = FileMetadata(media_type="movie", title="Inception", year=2010)
    g = ImportGroup(metadata=meta)
    g.add_file(FileEntry(path=Path("inception.mkv"), metadata=meta))
    rows = build_grid_rows([g])
    return [r for r in rows if r.kind == RowKind.FILE]


def _multi_rows_various():
    """Two movie rows with different years."""
    rows = []
    for title, year in [("Inception", 2010), ("Inception", 2011)]:
        meta = FileMetadata(media_type="movie", title=title, year=year)
        g = ImportGroup(metadata=meta)
        g.add_file(FileEntry(path=Path(f"{title.lower()}-{year}.mkv"), metadata=meta))
        built = build_grid_rows([g])
        rows.extend(r for r in built if r.kind == RowKind.FILE)
    return rows


@pytest.mark.asyncio
async def test_modal_renders_all_fields():
    """Modal shows all 5 metadata fields."""
    rows = _single_row()
    modal = EditModal(rows)
    assert modal._fields == FIELD_COLS
    assert len(modal._values) == len(FIELD_COLS)


@pytest.mark.asyncio
async def test_modal_initial_values():
    """Modal populates values from first target row."""
    rows = _single_row()
    modal = EditModal(rows)
    assert modal._values["title"] == "Inception"
    assert modal._values["year"] == "2010"


@pytest.mark.asyncio
async def test_modal_detects_various():
    """Fields with differing values across rows show as various."""
    rows = _multi_rows_various()
    modal = EditModal(rows)
    assert modal._various["year"] is True
    assert modal._various["title"] is False


@pytest.mark.asyncio
async def test_modal_escape_returns_none():
    """Pressing escape dismisses with None (no changes)."""
    from textual.app import App, ComposeResult
    from textual.widgets import Static

    class TestApp(App):
        result = "not_set"

        def compose(self) -> ComposeResult:
            yield Static("bg")

        def on_mount(self) -> None:
            rows = _single_row()
            self.push_screen(EditModal(rows), callback=self._on_result)

        def _on_result(self, result):
            self.result = result
            self.exit()

    app = TestApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("escape")
        await pilot.pause()
    assert app.result is None


@pytest.mark.asyncio
async def test_modal_enter_returns_empty_when_untouched():
    """Pressing enter without edits returns empty dict."""
    from textual.app import App, ComposeResult
    from textual.widgets import Static

    class TestApp(App):
        result = "not_set"

        def compose(self) -> ComposeResult:
            yield Static("bg")

        def on_mount(self) -> None:
            rows = _single_row()
            self.push_screen(EditModal(rows), callback=self._on_result)

        def _on_result(self, result):
            self.result = result
            self.exit()

    app = TestApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("enter")
        await pilot.pause()
    assert app.result == {}


@pytest.mark.asyncio
async def test_typing_updates_value():
    """Typing into a field updates its value."""
    from textual.app import App, ComposeResult
    from textual.widgets import Static

    class TestApp(App):
        result = "not_set"
        modal = None

        def compose(self) -> ComposeResult:
            yield Static("bg")

        def on_mount(self) -> None:
            rows = _single_row()
            self.modal = EditModal(rows)
            self.push_screen(self.modal, callback=self._on_result)

        def _on_result(self, result):
            self.result = result
            self.exit()

    app = TestApp()
    async with app.run_test(size=(80, 24)) as pilot:
        # Cursor starts on title field, type some chars
        await pilot.press("backspace", "backspace", "backspace")
        await pilot.press("enter")
        await pilot.pause()
    assert app.result == {"title": "Incept"}


@pytest.mark.asyncio
async def test_various_field_clears_on_first_keypress():
    """Typing into a various field starts from blank."""
    from textual.app import App, ComposeResult
    from textual.widgets import Static

    class TestApp(App):
        result = "not_set"
        modal = None

        def compose(self) -> ComposeResult:
            yield Static("bg")

        def on_mount(self) -> None:
            rows = _multi_rows_various()
            self.modal = EditModal(rows)
            self.push_screen(self.modal, callback=self._on_result)

        def _on_result(self, result):
            self.result = result
            self.exit()

    app = TestApp()
    async with app.run_test(size=(80, 24)) as pilot:
        # Navigate to year field (index 1), which is (various)
        await pilot.press("tab")
        await pilot.press("2", "0", "2", "5")
        await pilot.press("enter")
        await pilot.pause()
    assert app.result == {"year": "2025"}


@pytest.mark.asyncio
async def test_various_untouched_not_in_result():
    """Various fields left untouched are not in the result dict."""
    from textual.app import App, ComposeResult
    from textual.widgets import Static

    class TestApp(App):
        result = "not_set"

        def compose(self) -> ComposeResult:
            yield Static("bg")

        def on_mount(self) -> None:
            rows = _multi_rows_various()
            self.push_screen(EditModal(rows), callback=self._on_result)

        def _on_result(self, result):
            self.result = result
            self.exit()

    app = TestApp()
    async with app.run_test(size=(80, 24)) as pilot:
        # Just press enter without touching anything
        await pilot.press("enter")
        await pilot.pause()
    # year is various but untouched, so not in result
    assert "year" not in app.result


@pytest.mark.asyncio
async def test_frozen_field_blocks_typing():
    """Typing into a frozen field has no effect."""
    from textual.app import App, ComposeResult
    from textual.widgets import Static

    class TestApp(App):
        result = "not_set"

        def compose(self) -> ComposeResult:
            yield Static("bg")

        def on_mount(self) -> None:
            rows = _single_row()
            rows[0].frozen_fields.add("title")
            self.push_screen(EditModal(rows), callback=self._on_result)

        def _on_result(self, result):
            self.result = result
            self.exit()

    app = TestApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("x", "y", "z")
        await pilot.press("enter")
        await pilot.pause()
    assert "title" not in app.result


@pytest.mark.asyncio
async def test_toggle_freeze_in_modal():
    """Pressing f unfreezes a frozen field, allowing edits."""
    from textual.app import App, ComposeResult
    from textual.widgets import Static

    class TestApp(App):
        result = "not_set"

        def compose(self) -> ComposeResult:
            yield Static("bg")

        def on_mount(self) -> None:
            rows = _single_row()
            rows[0].frozen_fields.add("title")
            self.push_screen(EditModal(rows), callback=self._on_result)

        def _on_result(self, result):
            self.result = result
            self.exit()

    app = TestApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("f")
        await pilot.press("x")
        await pilot.press("enter")
        await pilot.pause()
    assert app.result == {"title": "Inceptionx"}


@pytest.mark.asyncio
async def test_freeze_field_in_modal():
    """Pressing f on an unfrozen field freezes it, blocking further edits."""
    from textual.app import App, ComposeResult
    from textual.widgets import Static

    class TestApp(App):
        result = "not_set"

        def compose(self) -> ComposeResult:
            yield Static("bg")

        def on_mount(self) -> None:
            rows = _single_row()
            self.push_screen(EditModal(rows), callback=self._on_result)

        def _on_result(self, result):
            self.result = result
            self.exit()

    app = TestApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("x")
        await pilot.press("f")
        await pilot.press("y")
        await pilot.press("enter")
        await pilot.pause()
    assert app.result == {"title": "Inceptionx"}
