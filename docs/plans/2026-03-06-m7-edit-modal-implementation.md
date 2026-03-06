# M7: Edit Modal Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `Shift+E` modal overlay that lets users edit all metadata fields at once, with `(various)` placeholders for multi-selection divergence, freeze toggling, and atomic commit/cancel.

**Architecture:** A Textual `ModalScreen` (`EditModal`) renders a vertical form with one row per field. The modal receives target rows, computes initial values (detecting `(various)`), tracks per-field dirty state, and returns a dict of changed fields on confirm. `GridApp` handles applying changes and undo.

**Tech Stack:** Textual `ModalScreen`, Rich `Text` for rendering, existing `GridRow` model.

---

### Task 1: EditModal skeleton with render and dismiss

**Files:**
- Create: `tapes/ui/edit_modal.py`
- Test: `tests/test_ui/test_edit_modal.py`

**Step 1: Write the failing test**

```python
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
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ui/test_edit_modal.py -v`
Expected: FAIL (module not found)

**Step 3: Write minimal implementation**

Create `tapes/ui/edit_modal.py`:

```python
"""Shift+E edit modal -- edit all metadata fields at once."""
from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static
from rich.text import Text

from tapes.ui.models import GridRow
from tapes.ui.render import FIELD_COLS


# Sentinel for "various" placeholder
_VARIOUS = "(various)"


class EditModal(ModalScreen[dict[str, Any] | None]):
    """Modal for editing all metadata fields of one or more rows."""

    DEFAULT_CSS = """
    EditModal {
        align: center middle;
    }
    #edit-modal-container {
        width: 50;
        height: auto;
        max-height: 80%;
        background: #1a1a1a;
        border: solid #444444;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("enter", "confirm", "Confirm", priority=True),
        Binding("tab", "next_field", "Next", show=False, priority=True),
        Binding("shift+tab", "prev_field", "Prev", show=False, priority=True),
        Binding("f", "toggle_freeze", "Freeze", show=False),
    ]

    def __init__(self, rows: list[GridRow], **kwargs) -> None:
        super().__init__(**kwargs)
        self._rows = rows
        self._fields = list(FIELD_COLS)
        self._cursor = 0

        # Compute initial values and various flags
        self._values: dict[str, str] = {}
        self._various: dict[str, bool] = {}
        self._dirty: dict[str, bool] = {}
        self._frozen: dict[str, bool] = {}

        first = rows[0]
        for f in self._fields:
            val = str(getattr(first, f) or "")
            self._values[f] = val
            self._dirty[f] = False
            self._frozen[f] = first.is_frozen(f)

            # Check if values differ across rows
            is_various = False
            for r in rows[1:]:
                other_val = str(getattr(r, f) or "")
                if other_val != val:
                    is_various = True
                    break
            self._various[f] = is_various

    def compose(self) -> ComposeResult:
        with Static(id="edit-modal-container"):
            yield Static(self._render(), id="edit-modal-body")

    def _render(self) -> Text:
        t = Text()
        t.append("Edit metadata\n\n", style="bold")

        for i, f in enumerate(self._fields):
            is_focused = i == self._cursor
            is_frozen = self._frozen[f]
            is_various = self._various[f] and not self._dirty[f]

            # Label
            label = f"{f}:".ljust(16)
            label_style = "#555555" if is_frozen else "#888888"
            t.append("  ")
            t.append(label, style=label_style)

            # Value
            if is_various:
                display = _VARIOUS
                val_style = "#666666 italic"
            elif is_frozen:
                display = self._values[f]
                val_style = "#555555"
            else:
                display = self._values[f]
                val_style = "#dddddd"

            if is_focused and not is_frozen:
                t.append(display, style="underline " + val_style)
                t.append("_", style="blink")
            else:
                t.append(display, style=val_style)

            if is_frozen:
                t.append("  [frozen]", style="#555555 italic")

            t.append("\n")

        t.append("\n")
        t.append("  tab", style="#888888")
        t.append("/", style="#555555")
        t.append("shift-tab", style="#888888")
        t.append(": navigate  ", style="#555555")
        t.append("f", style="#888888")
        t.append(": freeze  ", style="#555555")
        t.append("enter", style="#888888")
        t.append(": ok  ", style="#555555")
        t.append("esc", style="#888888")
        t.append(": cancel", style="#555555")

        return t

    def _refresh(self) -> None:
        body = self.query_one("#edit-modal-body", Static)
        body.update(self._render())

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_confirm(self) -> None:
        result: dict[str, Any] = {}
        for f in self._fields:
            if self._dirty[f] and not self._frozen[f]:
                result[f] = self._values[f]
        self.dismiss(result)

    def action_next_field(self) -> None:
        self._cursor = (self._cursor + 1) % len(self._fields)
        self._refresh()

    def action_prev_field(self) -> None:
        self._cursor = (self._cursor - 1) % len(self._fields)
        self._refresh()

    def action_toggle_freeze(self) -> None:
        f = self._fields[self._cursor]
        self._frozen[f] = not self._frozen[f]
        self._refresh()

    def on_key(self, event) -> None:
        f = self._fields[self._cursor]
        if self._frozen[f]:
            return

        if event.key == "backspace":
            event.prevent_default()
            event.stop()
            if self._various[f] and not self._dirty[f]:
                # First edit on various: clear to blank
                self._values[f] = ""
                self._dirty[f] = True
            elif self._values[f]:
                self._values[f] = self._values[f][:-1]
                self._dirty[f] = True
            self._refresh()
        elif event.character and event.is_printable:
            event.prevent_default()
            event.stop()
            if self._various[f] and not self._dirty[f]:
                # First edit on various: start from blank
                self._values[f] = event.character
            else:
                self._values[f] += event.character
            self._dirty[f] = True
            self._refresh()
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ui/test_edit_modal.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add tapes/ui/edit_modal.py tests/test_ui/test_edit_modal.py
git commit -m "feat(ui): add EditModal skeleton with render and dismiss"
```

---

### Task 2: Typing, backspace, and various-field behavior

**Files:**
- Modify: `tests/test_ui/test_edit_modal.py`
- Modify: `tapes/ui/edit_modal.py` (already implemented in Task 1, tests validate)

**Step 1: Write the failing tests**

Add to `tests/test_ui/test_edit_modal.py`:

```python
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
```

**Step 2: Run tests to verify they pass**

These tests validate behavior already implemented in Task 1. They should pass immediately.

Run: `uv run pytest tests/test_ui/test_edit_modal.py -v`
Expected: All 8 tests PASS

**Step 3: Commit**

```bash
git add tests/test_ui/test_edit_modal.py
git commit -m "test(ui): add typing and various-field behavior tests for EditModal"
```

---

### Task 3: Freeze toggle in modal

**Files:**
- Modify: `tests/test_ui/test_edit_modal.py`

**Step 1: Write the failing tests**

Add to `tests/test_ui/test_edit_modal.py`:

```python
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
            # Freeze the title field before opening modal
            rows[0].frozen_fields.add("title")
            self.push_screen(EditModal(rows), callback=self._on_result)

        def _on_result(self, result):
            self.result = result
            self.exit()

    app = TestApp()
    async with app.run_test(size=(80, 24)) as pilot:
        # Try typing on frozen title field
        await pilot.press("x", "y", "z")
        await pilot.press("enter")
        await pilot.pause()
    # Title was frozen, so no changes
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
        # Unfreeze title with f, then type
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
        # Type something, then freeze, then type more (ignored)
        await pilot.press("x")
        await pilot.press("f")
        await pilot.press("y")
        await pilot.press("enter")
        await pilot.pause()
    # Only the "x" typed before freeze should be in the result
    assert app.result == {"title": "Inceptionx"}
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_ui/test_edit_modal.py -v`
Expected: All 11 tests PASS (freeze logic already implemented in Task 1)

**Step 3: Commit**

```bash
git add tests/test_ui/test_edit_modal.py
git commit -m "test(ui): add freeze toggle tests for EditModal"
```

---

### Task 4: Wire Shift+E binding in GridApp

**Files:**
- Modify: `tapes/ui/grid.py`
- Modify: `tests/test_ui/test_grid.py`

**Step 1: Write the failing test**

Add to `tests/test_ui/test_grid.py`:

```python
async def test_shift_e_opens_edit_modal():
    """Shift+E opens the edit modal and applies changes on enter."""
    groups = [_movie_group()]
    app = GridApp(groups)
    async with app.run_test(size=(80, 30)) as pilot:
        # Open modal
        await pilot.press("E")
        await pilot.pause()
        # Type into title field (backspace 3 chars, add "!!!"))
        await pilot.press("backspace", "backspace", "backspace")
        await pilot.press("!", "!", "!")
        # Move to year, change it
        await pilot.press("tab")
        await pilot.press("backspace", "backspace", "backspace", "backspace")
        await pilot.press("2", "0", "2", "5")
        # Confirm
        await pilot.press("enter")
        await pilot.pause()
        # Check row was updated
        row = app._rows[0]
        assert row.title == "Incept!!!"
        assert row.year == 2025


async def test_shift_e_cancel_discards_changes():
    """Shift+E then escape discards all edits."""
    groups = [_movie_group()]
    app = GridApp(groups)
    async with app.run_test(size=(80, 30)) as pilot:
        await pilot.press("E")
        await pilot.pause()
        await pilot.press("x", "y", "z")
        await pilot.press("escape")
        await pilot.pause()
        row = app._rows[0]
        assert row.title == "Inception"


async def test_shift_e_undoable():
    """Modal edits can be undone with u."""
    groups = [_movie_group()]
    app = GridApp(groups)
    async with app.run_test(size=(80, 30)) as pilot:
        await pilot.press("E")
        await pilot.pause()
        await pilot.press("x")
        await pilot.press("enter")
        await pilot.pause()
        assert app._rows[0].title == "Inceptionx"
        await pilot.press("u")
        await pilot.pause()
        assert app._rows[0].title == "Inception"


async def test_shift_e_disabled_in_dest_mode():
    """Shift+E does nothing in destination view."""
    groups = [_movie_group()]
    app = GridApp(groups)
    async with app.run_test(size=(80, 30)) as pilot:
        await pilot.press("tab")  # enter dest mode
        await pilot.pause()
        await pilot.press("E")
        await pilot.pause()
        # Should still be in dest mode, no modal
        assert app.dest_mode is True
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ui/test_grid.py::test_shift_e_opens_edit_modal -v`
Expected: FAIL (no binding for E)

**Step 3: Write the implementation**

Add to `GridApp.BINDINGS` in `tapes/ui/grid.py`:

```python
Binding("E", "open_edit_modal", "Edit all", show=False, key_display="shift+e"),
```

Add import at top of `grid.py`:

```python
from tapes.ui.edit_modal import EditModal
```

Add method to `GridApp`:

```python
def action_open_edit_modal(self) -> None:
    """Open the full edit modal for cursor row or selection."""
    if not self._grid or self._editing or self._dest_mode:
        return
    targets = self._target_rows()
    target_rows = [self._rows[i] for i in targets if self._rows[i].kind == RowKind.FILE]
    if not target_rows:
        return

    # Snapshot for undo
    self._undo = self._snapshot_rows(targets)
    self._undo_rows = None

    def _on_modal_result(result: dict[str, Any] | None) -> None:
        if result is None or not result:
            self._undo = None  # Nothing to undo
            return
        # Apply changes to all target rows
        for row_idx in targets:
            row = self._rows[row_idx]
            if row.kind != RowKind.FILE:
                continue
            for field_name, value in result.items():
                # Type conversion for int fields
                if field_name in _INT_FIELDS:
                    try:
                        row.set_field(field_name, int(value))
                    except (ValueError, TypeError):
                        pass  # Skip invalid int
                else:
                    row.set_field(field_name, value)
        # Sync freeze state from modal back to rows
        modal = self._last_modal
        if modal:
            for row_idx in targets:
                row = self._rows[row_idx]
                if row.kind != RowKind.FILE:
                    continue
                for f in FIELD_COLS:
                    if modal._frozen[f]:
                        row.frozen_fields.add(f)
                    else:
                        row.frozen_fields.discard(f)
        if self._grid:
            self._grid.refresh_grid()

    modal = EditModal(target_rows)
    self._last_modal = modal
    self.push_screen(modal, callback=_on_modal_result)
```

Add `self._last_modal: EditModal | None = None` to `__init__`.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ui/test_grid.py::test_shift_e_opens_edit_modal tests/test_ui/test_grid.py::test_shift_e_cancel_discards_changes tests/test_ui/test_grid.py::test_shift_e_undoable tests/test_ui/test_grid.py::test_shift_e_disabled_in_dest_mode -v`
Expected: All 4 PASS

**Step 5: Commit**

```bash
git add tapes/ui/grid.py tests/test_ui/test_grid.py
git commit -m "feat(ui): wire Shift+E edit modal into GridApp"
```

---

### Task 5: Freeze state sync and multi-selection integration

**Files:**
- Modify: `tests/test_ui/test_grid.py`

**Step 1: Write the failing tests**

Add to `tests/test_ui/test_grid.py`:

```python
async def test_shift_e_with_selection_applies_to_all():
    """Modal edits apply to all selected rows."""
    groups = _episode_groups()
    app = GridApp(groups)
    async with app.run_test(size=(80, 30)) as pilot:
        # Select all show rows
        await pilot.press("A")
        await pilot.pause()
        # Open modal
        await pilot.press("E")
        await pilot.pause()
        # Edit title
        await pilot.press("backspace")
        await pilot.press("!")
        await pilot.press("enter")
        await pilot.pause()
        # All file rows should have the new title
        for r in app._rows:
            if r.kind == RowKind.FILE:
                assert r.title == "Breaking Ba!"


async def test_shift_e_freeze_syncs_back():
    """Toggling freeze in modal updates the row's frozen_fields."""
    groups = [_movie_group()]
    app = GridApp(groups)
    async with app.run_test(size=(80, 30)) as pilot:
        await pilot.press("E")
        await pilot.pause()
        # Freeze title (cursor starts on title)
        await pilot.press("f")
        # Confirm
        await pilot.press("enter")
        await pilot.pause()
        assert "title" in app._rows[0].frozen_fields
```

**Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_ui/test_grid.py::test_shift_e_with_selection_applies_to_all tests/test_ui/test_grid.py::test_shift_e_freeze_syncs_back -v`
Expected: All PASS (logic already in Task 4)

**Step 3: Commit**

```bash
git add tests/test_ui/test_grid.py
git commit -m "test(ui): add multi-selection and freeze sync tests for edit modal"
```

---

### Task 6: Final integration and full test run

**Files:**
- Modify: `docs/plans/2026-03-06-grid-tui.md` (update M7 section)

**Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS (316 existing + new modal tests)

**Step 2: Update grid TUI plan with M7 notes**

Add implementation notes to the M7 section in `docs/plans/2026-03-06-grid-tui.md`:

```markdown
## M7: Shift+E modal -- DONE

- `EditModal` (`tapes/ui/edit_modal.py`): Textual `ModalScreen` with vertical form
- All 5 metadata fields shown, `tab`/`shift-tab` navigation
- `(various)` placeholder for multi-selection divergence (virtual, not editable)
- `f` toggles freeze per field; freeze state syncs back to rows on confirm
- Atomic: `esc` discards all, `enter` commits all dirty fields
- Undoable with `u`
- Disabled in dest mode

### M7 implementation notes
- `EditModal` returns `dict[str, Any] | None` -- `None` for cancel, empty dict for no changes
- Freeze toggle in modal updates `GridRow.frozen_fields` on confirm
- Int fields validated on commit, invalid silently skipped
```

**Step 3: Commit**

```bash
git add docs/plans/2026-03-06-grid-tui.md
git commit -m "docs: update grid TUI plan with M7 implementation notes"
```
