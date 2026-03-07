"""Interactive Textual widget for the detail view with cursor and editing."""
from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual import events
from textual.reactive import reactive
from textual.widget import Widget

from tapes.ui.detail_render import (
    COL_WIDTH,
    LABEL_WIDTH,
    col,
    display_val,
    get_display_fields,
    render_detail_header,
)
from tapes.ui.tree_model import FileNode
from tapes.ui.tree_render import compute_dest

if TYPE_CHECKING:
    from rich.console import RenderableType


class DetailView(Widget):
    """Detail view showing a file's metadata grid with cursor navigation."""

    can_focus = True

    cursor_row: reactive[int] = reactive(0)   # -1 = header, 0+ = fields
    cursor_col: reactive[int] = reactive(0)   # 0 = result, 1+ = sources
    editing: reactive[bool] = reactive(False)

    def __init__(self, node: FileNode, template: str) -> None:
        super().__init__()
        self.node = node
        self.template = template
        self._fields: list[str] = []
        self._edit_value: str = ""

    def on_mount(self) -> None:
        self._fields = get_display_fields(self.template)

    def set_node(self, node: FileNode) -> None:
        """Switch to a new file node, resetting cursor and edit state."""
        self.node = node
        self.cursor_row = 0
        self.cursor_col = 0
        self._fields = get_display_fields(self.template)
        self.editing = False
        self.refresh()

    def render(self) -> RenderableType:
        """Build Rich Text with cursor highlighting."""
        lines: list[Text] = []

        # Header: filename + destination
        header_lines = render_detail_header(self.node, self.template)
        for hl in header_lines:
            lines.append(Text(hl))

        # Separator
        lines.append(Text("\u2576" + "\u2500" * 78 + "\u2574"))

        # Grid header row
        lines.append(self._render_grid_header())

        # Field rows
        for row_idx, field_name in enumerate(self._fields):
            lines.append(self._render_field_row(row_idx, field_name))

        # Bottom separator
        lines.append(Text("\u2576" + "\u2500" * 78 + "\u2574"))

        # Help line
        lines.append(Text(" enter: apply/edit   shift-enter: apply all   esc: back"))

        return Text("\n").join(lines)

    def _render_grid_header(self) -> Text:
        """Render the column header row with optional cursor highlight."""
        parts: list[tuple[str, str]] = []

        # Label area (empty for header)
        parts.append((" " * LABEL_WIDTH, ""))

        # Result column header
        result_text = col("result")
        style = "reverse" if self.cursor_row == -1 and self.cursor_col == 0 else ""
        parts.append((result_text, style))

        # Separator
        parts.append(("\u2503", ""))

        # Source headers
        for i, src in enumerate(self.node.sources):
            conf = f" ({src.confidence:.0%})" if src.confidence else ""
            col_text = col(f"  {src.name}{conf}")
            style = (
                "reverse"
                if self.cursor_row == -1 and self.cursor_col == i + 1
                else ""
            )
            parts.append((col_text, style))

        line = Text()
        for text, style in parts:
            line.append(text, style=style)
        return line

    def _render_field_row(self, row_idx: int, field_name: str) -> Text:
        """Render a single field row with optional cursor highlight."""
        parts: list[tuple[str, str]] = []

        # Label
        label = f" {field_name:<{LABEL_WIDTH - 1}}"
        parts.append((label, ""))

        # Result value
        if self.editing and self.cursor_row == row_idx and self.cursor_col == 0:
            # Show edit input
            edit_display = self._edit_value + "\u2588"  # block cursor
            result_text = col(edit_display)
            parts.append((result_text, "underline"))
        else:
            result_val = display_val(self.node.result.get(field_name))
            result_text = col(result_val)
            style = (
                "reverse"
                if self.cursor_row == row_idx and self.cursor_col == 0
                else ""
            )
            parts.append((result_text, style))

        # Separator
        parts.append(("\u2503", ""))

        # Source values
        for i, src in enumerate(self.node.sources):
            src_val = display_val(src.fields.get(field_name))
            col_text = col(f"  {src_val}")
            style = (
                "reverse"
                if self.cursor_row == row_idx and self.cursor_col == i + 1
                else ""
            )
            parts.append((col_text, style))

        line = Text()
        for text, style in parts:
            line.append(text, style=style)
        return line

    def move_cursor(self, row_delta: int = 0, col_delta: int = 0) -> None:
        """Move cursor, clamping to valid range."""
        if self.editing:
            return
        max_row = len(self._fields) - 1
        max_col = len(self.node.sources)  # 0 = result, 1..n = sources

        new_row = self.cursor_row + row_delta
        new_col = self.cursor_col + col_delta

        self.cursor_row = max(-1, min(max_row, new_row))
        self.cursor_col = max(0, min(max_col, new_col))

    def apply_source_field(self) -> None:
        """Handle enter on the current cursor cell."""
        if self.cursor_col == 0:
            # Result column: start inline edit
            self._start_edit()
            return

        src_idx = self.cursor_col - 1
        if src_idx >= len(self.node.sources):
            return

        if self.cursor_row == -1:
            # Header row: apply all non-empty from this source
            self._apply_source_all(src_idx)
        else:
            # Single field: copy value to result
            field_name = self._fields[self.cursor_row]
            val = self.node.sources[src_idx].fields.get(field_name)
            if val is not None:
                self.node.result[field_name] = val
        self.refresh()

    def apply_source_all_clear(self) -> None:
        """Handle shift-enter: apply all fields from source including empties."""
        if self.cursor_col == 0 or self.cursor_row != -1:
            return
        src_idx = self.cursor_col - 1
        if src_idx >= len(self.node.sources):
            return
        src = self.node.sources[src_idx]
        for field_name in self._fields:
            val = src.fields.get(field_name)
            if val is not None:
                self.node.result[field_name] = val
            else:
                self.node.result.pop(field_name, None)
        self.refresh()

    def _apply_source_all(self, src_idx: int) -> None:
        """Apply all non-empty fields from a source to result."""
        src = self.node.sources[src_idx]
        for field_name in self._fields:
            val = src.fields.get(field_name)
            if val is not None:
                self.node.result[field_name] = val

    def _start_edit(self) -> None:
        """Enter inline edit mode for the current result field."""
        if self.cursor_row < 0:
            return
        field_name = self._fields[self.cursor_row]
        current = self.node.result.get(field_name)
        self._edit_value = str(current) if current is not None else ""
        self.editing = True
        self.refresh()

    def _commit_edit(self) -> None:
        """Save the edited value to the result."""
        field_name = self._fields[self.cursor_row]
        val: str | int = self._edit_value
        if field_name in ("year", "season", "episode"):
            try:
                val = int(val)
            except ValueError:
                pass
        self.node.result[field_name] = val
        self.editing = False
        self.refresh()

    def _cancel_edit(self) -> None:
        """Discard the edit and exit edit mode."""
        self.editing = False
        self.refresh()

    def on_key(self, event: events.Key) -> None:
        """Handle key events for inline editing."""
        if not self.editing:
            return

        if event.key == "enter":
            self._commit_edit()
            event.prevent_default()
            event.stop()
        elif event.key == "escape":
            self._cancel_edit()
            event.prevent_default()
            event.stop()
        elif event.key == "backspace":
            self._edit_value = self._edit_value[:-1]
            self.refresh()
            event.prevent_default()
            event.stop()
        elif event.character and event.is_printable:
            self._edit_value += event.character
            self.refresh()
            event.prevent_default()
            event.stop()

    def watch_cursor_row(self) -> None:
        """React to cursor row changes."""
        self.refresh()

    def watch_cursor_col(self) -> None:
        """React to cursor col changes."""
        self.refresh()
