"""Interactive Textual widget for the detail view with cursor and editing."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from rich.text import Text
from textual import events
from textual.reactive import reactive
from textual.widget import Widget

from tapes.fields import INT_FIELDS
from tapes.ui.detail_render import (
    COL_WIDTH,
    LABEL_WIDTH,
    col,
    display_val,
    get_display_fields,
    render_detail_header,
)
from tapes.ui.tree_model import FileNode, compute_shared_fields
from tapes.ui.tree_render import compute_dest, select_template

if TYPE_CHECKING:
    from rich.console import RenderableType


class DetailView(Widget):
    """Detail view showing a file's metadata grid with cursor navigation.

    Supports single-node and multi-node modes. In multi-node mode,
    shared values are shown and edits apply to all nodes.
    """

    can_focus = True

    cursor_row: reactive[int] = reactive(0)   # -1 = header, 0+ = fields
    cursor_col: reactive[int] = reactive(0)   # 0 = result, 1+ = sources
    editing: reactive[bool] = reactive(False)
    active: reactive[bool] = reactive(False)

    def __init__(
        self,
        node: FileNode,
        movie_template: str,
        tv_template: str,
    ) -> None:
        super().__init__()
        self.node = node
        self._file_nodes: list[FileNode] = [node]
        self.movie_template = movie_template
        self.tv_template = tv_template
        self._fields: list[str] = []
        self._edit_value: str = ""
        self.on_before_mutate: Callable[[list[FileNode]], None] | None = None

    def _active_template(self, node: FileNode | None = None) -> str:
        """Return the template for the given (or primary) node.

        Selects based on the node's ``media_type``.
        """
        if node is None:
            node = self.node
        return select_template(node, self.movie_template, self.tv_template)

    @property
    def is_multi(self) -> bool:
        """Whether multiple nodes are being displayed."""
        return len(self._file_nodes) > 1

    def on_mount(self) -> None:
        self._fields = get_display_fields(self._active_template())

    def set_node(self, node: FileNode) -> None:
        """Switch to a new file node, resetting cursor and edit state."""
        self.node = node
        self._file_nodes = [node]
        self.cursor_row = 0
        self.cursor_col = 0
        self._fields = get_display_fields(self._active_template(node))
        self.editing = False
        self.refresh()

    def set_nodes(self, nodes: list[FileNode]) -> None:
        """Switch to multiple file nodes for multi-file detail view.

        The first node is used as the primary for sources display.
        Result column shows shared values, '(various)' for differing.
        """
        if not nodes:
            return
        self._file_nodes = list(nodes)
        self.node = nodes[0]
        self.cursor_row = 0
        self.cursor_col = 0
        self._fields = get_display_fields(self._active_template(self.node))
        self.editing = False
        self.refresh()

    def _shared_result(self) -> dict[str, Any]:
        """Compute the shared result for multi-node display."""
        if not self.is_multi:
            return self.node.result
        return compute_shared_fields(self._file_nodes)

    def _border_style(self) -> str:
        """Return the Rich style string for the border."""
        return "cyan" if self.active else "dim"

    def watch_active(self) -> None:
        """React to active state changes."""
        self.refresh()

    def render(self) -> RenderableType:
        """Build Rich Text with cursor highlighting, wrapped in box-drawing borders."""
        w = self.size.width
        border_style = self._border_style()
        inner_width = max(0, w - 2)

        # Build content lines (without borders)
        content: list[Text] = []

        # Header: filename + destination (or multi-file summary)
        if self.is_multi:
            header_lines = self._render_multi_header()
        else:
            header_lines = render_detail_header(self.node, self._active_template())
        for hl in header_lines:
            content.append(Text(hl))

        # Separator
        content.append(Text("\u2576" + "\u2500" * min(78, inner_width) + "\u2574"))

        # Grid header row
        content.append(self._render_grid_header())

        # Field rows
        for row_idx, field_name in enumerate(self._fields):
            content.append(self._render_field_row(row_idx, field_name))

        # Bottom separator
        content.append(Text("\u2576" + "\u2500" * min(78, inner_width) + "\u2574"))

        # Help line
        content.append(Text(" enter: apply/edit   shift-enter: apply all   esc: back"))

        # Now wrap in borders
        # Top border: ├─ Detail ─...─┤ (shares border with tree above)
        title = " Detail "
        top_fill = max(0, w - 2 - len(title))
        top_line = Text()
        top_line.append(
            f"\u251c\u2500{title}" + "\u2500" * top_fill + "\u2524",
            style=border_style,
        )

        # Bottom border: └─...─┘
        bot_line = Text()
        bot_line.append(
            "\u2514" + "\u2500" * max(0, w - 2) + "\u2518",
            style=border_style,
        )

        # Wrap content lines in side borders
        bordered: list[Text] = [top_line]
        for cline in content:
            line = Text()
            line.append("\u2502", style=border_style)
            # Pad content to inner_width using plain_text length
            plain_len = len(cline.plain)
            if plain_len < inner_width:
                padded = Text()
                padded.append_text(cline)
                padded.append(" " * (inner_width - plain_len))
                line.append_text(padded)
            else:
                line.append_text(cline)
            line.append("\u2502", style=border_style)
            bordered.append(line)

        # Fill remaining height with blank bordered rows
        content_height = max(0, self.size.height - 2)
        while len(bordered) - 1 < content_height:  # -1 for top_line already in bordered
            blank = Text()
            blank.append("\u2502", style=border_style)
            blank.append(" " * inner_width)
            blank.append("\u2502", style=border_style)
            bordered.append(blank)

        bordered.append(bot_line)
        return Text("\n").join(bordered)

    def _render_multi_header(self) -> list[str]:
        """Render header for multi-file view."""
        count = len(self._file_nodes)
        header = f" {count} files selected"

        # Compute destinations
        dests: set[str] = set()
        for n in self._file_nodes:
            d = compute_dest(n, self._active_template(n))
            dests.add(d or "???")

        if len(dests) == 1:
            dest_str = f" \u2192 {dests.pop()}"
        else:
            dest_str = " \u2192 (various destinations)"

        return [header, dest_str]

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

        # Source headers (use primary node's sources)
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
        shared = self._shared_result()

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
            result_val = display_val(shared.get(field_name))
            result_text = col(result_val)
            style = (
                "reverse"
                if self.cursor_row == row_idx and self.cursor_col == 0
                else ""
            )
            parts.append((result_text, style))

        # Separator
        parts.append(("\u2503", ""))

        # Source values (use primary node's sources)
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

    def _notify_before_mutate(self) -> None:
        """Notify the on_before_mutate callback before a mutation."""
        if self.on_before_mutate is not None:
            self.on_before_mutate(list(self._file_nodes))

    def apply_source_field(self) -> None:
        """Handle enter on the current cursor cell."""
        if self.cursor_col == 0:
            # Result column: start inline edit
            self._start_edit()
            return

        src_idx = self.cursor_col - 1
        if src_idx >= len(self.node.sources):
            return

        self._notify_before_mutate()
        if self.cursor_row == -1:
            # Header row: apply all non-empty from this source
            self._apply_source_all(src_idx)
        else:
            # Single field: copy value to result for all nodes
            field_name = self._fields[self.cursor_row]
            val = self.node.sources[src_idx].fields.get(field_name)
            if val is not None:
                for n in self._file_nodes:
                    n.result[field_name] = val
        self.refresh()

    def apply_source_all_clear(self) -> None:
        """Handle shift-enter: apply all fields from source including empties."""
        if self.cursor_col == 0 or self.cursor_row != -1:
            return
        src_idx = self.cursor_col - 1
        if src_idx >= len(self.node.sources):
            return
        self._notify_before_mutate()
        src = self.node.sources[src_idx]
        for field_name in self._fields:
            val = src.fields.get(field_name)
            if val is not None:
                for n in self._file_nodes:
                    n.result[field_name] = val
            else:
                for n in self._file_nodes:
                    n.result.pop(field_name, None)
        self.refresh()

    def _apply_source_all(self, src_idx: int) -> None:
        """Apply all non-empty fields from a source to result."""
        src = self.node.sources[src_idx]
        for field_name in self._fields:
            val = src.fields.get(field_name)
            if val is not None:
                for n in self._file_nodes:
                    n.result[field_name] = val

    def _start_edit(self) -> None:
        """Enter inline edit mode for the current result field."""
        if self.cursor_row < 0:
            return
        field_name = self._fields[self.cursor_row]
        shared = self._shared_result()
        current = shared.get(field_name)
        if current == "(various)":
            self._edit_value = ""
        else:
            self._edit_value = str(current) if current is not None else ""
        self.editing = True
        self.refresh()

    def _commit_edit(self) -> None:
        """Save the edited value to the result for all nodes."""
        self._notify_before_mutate()
        field_name = self._fields[self.cursor_row]
        val: str | int = self._edit_value
        if field_name in INT_FIELDS:
            try:
                val = int(val)
            except ValueError:
                pass
        for n in self._file_nodes:
            n.result[field_name] = val
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
