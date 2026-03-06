"""Grid TUI app for tapes."""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.events import Key
from textual.widgets import Static
from rich.text import Text

from tapes.models import ImportGroup
from tapes.ui.models import GridRow, RowKind, RowStatus, build_grid_rows
from tapes.ui.query import mock_tmdb_lookup
from tapes.ui.render import render_row, FIELD_COLS, COL_WIDTHS, _pad

# Fields that should be stored as int
_INT_FIELDS = {"year", "season", "episode"}


class GridFooter(Static):
    """Bottom bar with file/group counts and keybinding hints."""

    DEFAULT_CSS = """
    GridFooter {
        dock: bottom;
        height: 1;
        background: #0e0e0e;
        border-top: solid #1e1e1e;
    }
    """

    def __init__(self, rows: list[GridRow], **kwargs) -> None:
        super().__init__(**kwargs)
        self._rows = rows
        self._n_selected = 0

    def update_selection(self, n_selected: int) -> None:
        self._n_selected = n_selected
        self.refresh()

    def render(self) -> Text:  # type: ignore[override]
        t = Text()
        t.append(" ")

        if self._n_selected > 0:
            # Selection mode footer
            t.append(str(self._n_selected), style="#dddddd")
            t.append(" selected  ", style="#555555")
            t.append("    ", style="")
            hints = [
                ("v", "toggle"),
                ("esc", "clear"),
                ("e", "edit"),
            ]
        else:
            # Normal mode footer
            file_rows = [r for r in self._rows if r.kind == RowKind.FILE]
            n_files = len(file_rows)
            n_videos = sum(1 for r in file_rows if r.is_video)
            n_companions = sum(1 for r in file_rows if r.is_companion)
            n_groups = sum(1 for r in self._rows if r.kind == RowKind.BLANK) + 1

            for count, label in [
                (n_files, "files"),
                (n_groups, "groups"),
                (n_videos, "videos"),
                (n_companions, "companions"),
            ]:
                t.append(str(count), style="#dddddd")
                t.append(f" {label}  ", style="#555555")

            t.append("    ", style="")
            hints = [
                ("e", "edit"),
                ("v", "select"),
                ("q", "query"),
                ("f", "freeze"),
                ("r", "reorg"),
                ("p", "process"),
                ("E", "all fields"),
            ]

        for key, desc in hints:
            t.append(key, style="#777777 underline")
            t.append(f" {desc}  ", style="#444444")

        return t


class GridCommandLine(Static):
    """Displays the 'tapes import ./downloads' line at the top."""

    DEFAULT_CSS = """
    GridCommandLine {
        height: 1;
        padding: 0 2;
        background: #111111;
    }
    """

    def __init__(self, path: str = "./downloads", **kwargs) -> None:
        super().__init__(**kwargs)
        self._path = path

    def render(self) -> Text:  # type: ignore[override]
        t = Text()
        t.append("tapes import ", style="#555555")
        t.append(self._path, style="#dddddd")
        return t


class GridColumnHeader(Static):
    """Column header row aligned with the grid columns."""

    DEFAULT_CSS = """
    GridColumnHeader {
        height: 2;
        padding: 0 2;
        background: #111111;
    }
    """

    def render(self) -> Text:  # type: ignore[override]
        labels = ["", "filepath", "title", "year", "S", "E", "episode title"]
        col_keys = ["status", "filepath", "title", "year", "season", "episode", "episode_title"]
        t = Text()
        for label, key in zip(labels, col_keys):
            t.append(_pad(label, COL_WIDTHS[key]), style="#333333")
        t.append("\n")
        total_width = sum(COL_WIDTHS[k] for k in col_keys)
        t.append("\u2500" * total_width, style="#1e1e1e")
        return t


class GridWidget(Static):
    """Renders the entire grid as styled text lines."""

    def __init__(self, rows: list[GridRow], **kwargs) -> None:
        super().__init__(**kwargs)
        self.rows = rows
        self._cursor_row = 0
        self._cursor_col = 0
        self._selected_rows: set[int] = set()
        self._sel_col: int | None = None
        self._edit_col: int | None = None
        self._edit_value: str | None = None

    @property
    def selection(self) -> set[tuple[int, int]]:
        """Return set of (row, col) for all selected cells."""
        if self._sel_col is None:
            return set()
        return {(r, self._sel_col) for r in self._selected_rows}

    def clear_selection(self) -> None:
        self._selected_rows.clear()
        self._sel_col = None

    def render_grid(self) -> Text:
        out = Text()
        for i, row in enumerate(self.rows):
            if i > 0:
                out.append("\n")
            selected_cols: set[int] | None = None
            if self._sel_col is not None and i in self._selected_rows:
                selected_cols = {self._sel_col}
            # Only pass edit info for the cursor row
            edit_col = self._edit_col if i == self._cursor_row else None
            edit_value = self._edit_value if i == self._cursor_row else None
            line = render_row(
                row,
                cursor_col=self._cursor_col,
                is_cursor_row=(i == self._cursor_row),
                selected_cols=selected_cols,
                is_sel_cursor_row=(
                    i == self._cursor_row
                    and self._sel_col is not None
                    and i in self._selected_rows
                ),
                edit_col=edit_col,
                edit_value=edit_value,
            )
            out.append_text(line)
        return out

    def refresh_grid(self) -> None:
        self.update(self.render_grid())


class GridApp(App):
    """Spreadsheet-like grid TUI for reviewing imports."""

    TITLE = "tapes"
    CSS = """
    Screen { background: #111111; }
    #grid-scroll { background: #111111; }
    #grid { padding: 1 2; }
    """

    BINDINGS = [
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("left", "cursor_left", "Left", show=False),
        Binding("right", "cursor_right", "Right", show=False),
        Binding("v", "toggle_select", "Select", show=False),
        Binding("e", "start_edit", "Edit", show=False),
        Binding("escape", "cancel_edit", "Cancel / Clear", show=False),
        Binding("q", "query", "Query", show=False),
        Binding("u", "undo", "Undo", show=False),
        Binding("f", "freeze", "Freeze cell", show=False),
        Binding("F", "freeze_row", "Freeze row", show=False, key_display="shift+f"),
    ]

    def __init__(self, groups: list[ImportGroup], **kwargs) -> None:
        super().__init__(**kwargs)
        self._groups = groups
        self._rows = build_grid_rows(groups)
        self._grid: GridWidget | None = None
        self._editing: bool = False
        self._edit_field: str | None = None
        self._edit_targets: list[int] = []  # row indices being edited
        self._edit_buffer: str | None = None
        self._edit_original: str = ""
        # Undo: stores (field_name, [(row_idx, old_value), ...]) for last edit
        self._undo: tuple[str, list[tuple[int, Any]]] | None = None

    @property
    def editing(self) -> bool:
        return self._editing

    @property
    def cursor_row(self) -> int:
        return self._grid._cursor_row if self._grid else 0

    @property
    def cursor_col(self) -> int:
        return self._grid._cursor_col if self._grid else 0

    @property
    def selection(self) -> set[tuple[int, int]]:
        """Return set of (row, col) for all selected cells."""
        return self._grid.selection if self._grid else set()

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="grid-scroll"):
            yield GridCommandLine()
            yield GridColumnHeader()
            self._grid = GridWidget(self._rows, id="grid")
            yield self._grid
        yield GridFooter(self._rows)

    def on_mount(self) -> None:
        self._skip_to_file(1)
        if self._grid:
            self._grid.refresh_grid()

    def _skip_to_file(self, direction: int) -> None:
        if not self._grid:
            return
        row = self._grid._cursor_row
        while 0 <= row < len(self._rows) and self._rows[row].kind != RowKind.FILE:
            row += direction
        if 0 <= row < len(self._rows):
            self._grid._cursor_row = row

    def _file_rows(self) -> list[int]:
        return [i for i, r in enumerate(self._rows) if r.kind == RowKind.FILE]

    def _target_rows(self) -> list[int]:
        """Return selected rows if any, otherwise just the cursor row."""
        if self._grid._sel_col is not None and self._grid._selected_rows:
            return sorted(self._grid._selected_rows)
        return [self._grid._cursor_row]

    def _jump_to_top_target(self, targets: list[int]) -> None:
        """Move cursor to the topmost target row and the selection column."""
        if not self._grid or not targets:
            return
        self._grid._cursor_row = targets[0]
        if self._grid._sel_col is not None:
            self._grid._cursor_col = self._grid._sel_col

    def action_toggle_select(self) -> None:
        if not self._grid or self._editing:
            return
        row = self._grid._cursor_row
        col = self._grid._cursor_col
        if self._grid._sel_col is None:
            # Start new selection, lock column
            self._grid._sel_col = col
            self._grid._selected_rows.add(row)
        elif row in self._grid._selected_rows:
            # Already selected -- deselect
            self._grid._selected_rows.discard(row)
            if not self._grid._selected_rows:
                self._grid._sel_col = None
        else:
            self._grid._selected_rows.add(row)
        self._grid.refresh_grid()
        self._refresh_footer()

    def action_start_edit(self) -> None:
        if not self._grid or self._editing:
            return
        col = self._grid._cursor_col
        field_name = FIELD_COLS[col]

        # Determine target rows
        self._edit_targets = self._target_rows()

        # Check if the field is frozen on the first target
        target_row = self._rows[self._edit_targets[0]]
        if target_row.is_frozen(field_name):
            return

        self._edit_field = field_name

        # Get current value from first target row
        current_value = str(getattr(target_row, field_name) or "")

        self._editing = True
        self._edit_original = current_value
        self._edit_buffer = current_value

        # Update grid widget for inline rendering
        self._grid._edit_col = col
        self._grid._edit_value = self._edit_buffer
        self._grid.refresh_grid()

    def on_key(self, event: Key) -> None:
        """Capture keypresses during inline edit mode."""
        if not self._editing:
            return

        event.prevent_default()
        event.stop()

        if event.key == "enter":
            self._commit_edit(self._edit_buffer or "")
            return
        elif event.key == "escape":
            self._dismiss_edit()
            if self._grid:
                self._grid.refresh_grid()
            return
        elif event.key == "backspace":
            if self._edit_buffer:
                self._edit_buffer = self._edit_buffer[:-1]
        elif event.character and event.is_printable:
            self._edit_buffer = (self._edit_buffer or "") + event.character

        # Update inline display
        if self._grid:
            self._grid._edit_value = self._edit_buffer
            self._grid.refresh_grid()

    def _commit_edit(self, value: str) -> None:
        """Apply the edited value to target rows."""
        field_name = self._edit_field
        if not field_name:
            return

        # Type conversion
        if field_name in _INT_FIELDS:
            try:
                converted: str | int = int(value)
            except (ValueError, TypeError):
                # Invalid int -- cancel silently
                self._dismiss_edit()
                if self._grid:
                    self._grid.refresh_grid()
                return
        else:
            converted = value

        # Store undo info before applying
        undo_entries: list[tuple[int, Any]] = []
        for row_idx in self._edit_targets:
            old_value = getattr(self._rows[row_idx], field_name)
            undo_entries.append((row_idx, old_value))
            self._rows[row_idx].set_field(field_name, converted)
        self._undo = (field_name, undo_entries)

        targets = self._edit_targets
        self._dismiss_edit()
        if self._grid:
            self._jump_to_top_target(targets)
            self._grid.refresh_grid()

    def _dismiss_edit(self) -> None:
        """Reset edit state."""
        self._editing = False
        self._edit_field = None
        self._edit_targets = []
        self._edit_buffer = None
        self._edit_original = ""
        if self._grid:
            self._grid._edit_col = None
            self._grid._edit_value = None

    def action_cancel_edit(self) -> None:
        if self._editing:
            self._dismiss_edit()
            if self._grid:
                self._grid.refresh_grid()
            return
        if not self._grid:
            return
        self._grid.clear_selection()
        self._undo = None
        self._grid.refresh_grid()
        self._refresh_footer()

    def action_undo(self) -> None:
        """Undo the last edit. Only available while selection is active."""
        if not self._grid or self._editing or self._undo is None:
            return
        field_name, entries = self._undo
        for row_idx, old_value in entries:
            row = self._rows[row_idx]
            if old_value is None:
                row._overrides.pop(field_name, None)
            else:
                row._overrides[field_name] = old_value
            row.edited_fields.discard(field_name)
            # Revert status if no edited fields remain
            if not row.edited_fields:
                row.status = RowStatus.RAW
        self._undo = None
        self._grid.refresh_grid()

    def _refresh_footer(self) -> None:
        footer = self.query_one(GridFooter)
        n_sel = len(self._grid._selected_rows) if self._grid and self._grid._sel_col is not None else 0
        footer.update_selection(n_sel)

    def action_query(self) -> None:
        """Query mock TMDB for cursor row or all selected rows."""
        if not self._grid or self._editing:
            return

        targets = self._target_rows()

        for row_idx in targets:
            row = self._rows[row_idx]
            if row.kind != RowKind.FILE:
                continue
            result = mock_tmdb_lookup(row.title or "")
            if result is not None:
                row.apply_match(result)

        self._jump_to_top_target(targets)
        self._grid.refresh_grid()

    def action_freeze(self) -> None:
        """Toggle freeze on the current field for target rows."""
        if not self._grid or self._editing:
            return

        col = self._grid._cursor_col
        field_name = FIELD_COLS[col]
        targets = self._target_rows()

        for row_idx in targets:
            row = self._rows[row_idx]
            if row.kind != RowKind.FILE:
                continue
            row.toggle_freeze_field(field_name)
            # Update status based on freeze state
            if all(row.is_frozen(f) for f in FIELD_COLS):
                row.status = RowStatus.FROZEN
            elif row.status == RowStatus.FROZEN:
                row.status = RowStatus.RAW

        self._jump_to_top_target(targets)
        self._grid.refresh_grid()

    def action_freeze_row(self) -> None:
        """Toggle freeze on ALL fields for target rows."""
        if not self._grid or self._editing:
            return

        targets = self._target_rows()

        for row_idx in targets:
            row = self._rows[row_idx]
            if row.kind != RowKind.FILE:
                continue
            row.toggle_freeze_all_fields()
            if all(row.is_frozen(f) for f in FIELD_COLS):
                row.status = RowStatus.FROZEN
            else:
                row.status = RowStatus.RAW

        self._jump_to_top_target(targets)
        self._grid.refresh_grid()

    def action_cursor_down(self) -> None:
        if not self._grid or self._editing:
            return
        file_rows = self._file_rows()
        cur = self._grid._cursor_row
        for idx in file_rows:
            if idx > cur:
                self._grid._cursor_row = idx
                self._grid.refresh_grid()
                return

    def action_cursor_up(self) -> None:
        if not self._grid or self._editing:
            return
        file_rows = self._file_rows()
        cur = self._grid._cursor_row
        for idx in reversed(file_rows):
            if idx < cur:
                self._grid._cursor_row = idx
                self._grid.refresh_grid()
                return

    def action_cursor_right(self) -> None:
        if not self._grid or self._editing:
            return
        # Block column change while selection is active
        if self._grid._sel_col is not None:
            return
        if self._grid._cursor_col < len(FIELD_COLS) - 1:
            self._grid._cursor_col += 1
            self._grid.refresh_grid()

    def action_cursor_left(self) -> None:
        if not self._grid or self._editing:
            return
        # Block column change while selection is active
        if self._grid._sel_col is not None:
            return
        if self._grid._cursor_col > 0:
            self._grid._cursor_col -= 1
            self._grid.refresh_grid()
