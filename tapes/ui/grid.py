"""Grid TUI app for tapes."""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Static
from rich.text import Text

from tapes.models import ImportGroup
from tapes.ui.models import GridRow, RowKind, build_grid_rows
from tapes.ui.render import render_row, FIELD_COLS


class GridWidget(Static):
    """Renders the entire grid as styled text lines."""

    def __init__(self, rows: list[GridRow], **kwargs) -> None:
        super().__init__(**kwargs)
        self.rows = rows
        self._cursor_row = 0
        self._cursor_col = 0

    def render_grid(self) -> Text:
        out = Text()
        for i, row in enumerate(self.rows):
            if i > 0:
                out.append("\n")
            line = render_row(
                row,
                cursor_col=self._cursor_col,
                is_cursor_row=(i == self._cursor_row),
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
        Binding("q", "quit", "Quit", show=False),
    ]

    def __init__(self, groups: list[ImportGroup], **kwargs) -> None:
        super().__init__(**kwargs)
        self._groups = groups
        self._rows = build_grid_rows(groups)
        self._grid: GridWidget | None = None

    @property
    def cursor_row(self) -> int:
        return self._grid._cursor_row if self._grid else 0

    @property
    def cursor_col(self) -> int:
        return self._grid._cursor_col if self._grid else 0

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="grid-scroll"):
            self._grid = GridWidget(self._rows, id="grid")
            yield self._grid

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

    def action_cursor_down(self) -> None:
        if not self._grid:
            return
        file_rows = self._file_rows()
        cur = self._grid._cursor_row
        for idx in file_rows:
            if idx > cur:
                self._grid._cursor_row = idx
                self._grid.refresh_grid()
                return

    def action_cursor_up(self) -> None:
        if not self._grid:
            return
        file_rows = self._file_rows()
        cur = self._grid._cursor_row
        for idx in reversed(file_rows):
            if idx < cur:
                self._grid._cursor_row = idx
                self._grid.refresh_grid()
                return

    def action_cursor_right(self) -> None:
        if not self._grid:
            return
        if self._grid._cursor_col < len(FIELD_COLS) - 1:
            self._grid._cursor_col += 1
            self._grid.refresh_grid()

    def action_cursor_left(self) -> None:
        if not self._grid:
            return
        if self._grid._cursor_col > 0:
            self._grid._cursor_col -= 1
            self._grid.refresh_grid()
