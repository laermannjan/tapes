"""Grid TUI app for tapes."""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Static
from rich.text import Text

from tapes.models import ImportGroup
from tapes.ui.models import GridRow, RowKind, build_grid_rows
from tapes.ui.render import render_row, FIELD_COLS, COL_WIDTHS, _pad


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

    def render(self) -> Text:  # type: ignore[override]
        file_rows = [r for r in self._rows if r.kind == RowKind.FILE]
        n_files = len(file_rows)
        n_videos = sum(1 for r in file_rows if r.is_video)
        n_companions = sum(1 for r in file_rows if r.is_companion)
        n_groups = sum(1 for r in self._rows if r.kind == RowKind.BLANK) + 1

        t = Text()
        t.append(" ")
        # Counts section
        for count, label in [
            (n_files, "files"),
            (n_groups, "groups"),
            (n_videos, "videos"),
            (n_companions, "companions"),
        ]:
            t.append(str(count), style="#dddddd")
            t.append(f" {label}  ", style="#555555")

        t.append("    ", style="")

        # Keybinding hints
        hints = [
            ("e", "edit"),
            ("v", "select"),
            ("q", "query"),
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
