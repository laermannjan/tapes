"""Interactive Textual widget for the detail view with cursor and editing."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from rich.text import Text
from textual import events
from textual.reactive import reactive
from textual.widget import Widget

from tapes.fields import INT_FIELDS
from tapes.ui.detail_render import (
    LABEL_WIDTH,
    confidence_style,
    diff_style,
    display_val,
    get_display_fields,
    is_multi_value,
    render_compact_preview,
    render_detail_header,
    render_folder_preview,
)
from tapes.ui.tree_model import FileNode, FolderNode, compute_shared_fields
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
    source_index: reactive[int] = reactive(0)  # which TMDB source to display
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
        self.on_editing_changed: Callable[[bool], None] | None = None
        self._preview_node: FileNode | FolderNode | None = None

    def watch_editing(self, value: bool) -> None:
        """Notify parent when editing state changes."""
        if self.on_editing_changed is not None:
            self.on_editing_changed(value)

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
        self.source_index = 0
        self._fields = get_display_fields(self._active_template(node))
        self.editing = False
        self.refresh()

    def set_nodes(self, nodes: list[FileNode]) -> None:
        """Switch to multiple file nodes for multi-file detail view.

        The first node is used as the primary for sources display.
        Result column shows shared values, '(N values)' for differing.
        """
        if not nodes:
            return
        self._file_nodes = list(nodes)
        self.node = nodes[0]
        self.cursor_row = 0
        self.source_index = 0
        self._fields = get_display_fields(self._active_template(self.node))
        self.editing = False
        self.refresh()

    def set_preview_node(self, node: FileNode | FolderNode | None) -> None:
        """Set the node to show in compact preview mode."""
        self._preview_node = node
        self.refresh()

    def _shared_result(self) -> dict[str, Any]:
        """Compute the shared result for multi-node display."""
        if not self.is_multi:
            return self.node.result
        return compute_shared_fields(self._file_nodes)

    BORDER_TITLE = "Detail"

    def watch_active(self, value: bool) -> None:
        """React to active state changes by toggling CSS classes."""
        if value:
            self.add_class("-active")
            self.remove_class("-inactive")
        else:
            self.add_class("-inactive")
            self.remove_class("-active")
        self.refresh()

    def render(self) -> RenderableType:
        """Build Rich Text content (borders handled by Textual CSS)."""
        w = self.size.width
        inner_width = max(0, w - 2)  # account for CSS border + padding

        is_expanded = self.has_class("expanded")

        if is_expanded:
            content = self._render_expanded_content(inner_width)
        else:
            content = self._render_compact_content()

        return Text("\n").join(content)

    def _render_compact_content(self) -> list[Text]:
        """Render 2-line compact preview for the hovered node."""
        preview = self._preview_node
        if preview is None:
            return [Text(" (no file selected)", style="dim")]

        if isinstance(preview, FolderNode):
            preview_text = render_folder_preview(preview)
        elif isinstance(preview, FileNode):
            template = select_template(
                preview, self.movie_template, self.tv_template
            )
            preview_text = render_compact_preview(preview, template)
        else:
            return [Text(" (no file selected)", style="dim")]

        # The render functions return Text with a "\n" separator.
        # Split into individual lines preserving styles.
        return list(preview_text.split("\n"))

    def _render_expanded_content(self, inner_width: int) -> list[Text]:
        """Render the full detail grid (existing expanded behavior)."""
        content: list[Text] = []

        # Header: filename + destination (or multi-file summary)
        if self.is_multi:
            for hl in self._render_multi_header():
                content.append(hl)
        else:
            for hl in render_detail_header(self.node, self._active_template()):
                content.append(Text(hl))

        # Separator
        content.append(Text("\u2500" * inner_width, style="dim"))

        # Grid header row
        content.append(self._render_grid_header())

        # Field rows
        for row_idx, field_name in enumerate(self._fields):
            content.append(self._render_field_row(row_idx, field_name))

        # Bottom separator
        content.append(Text("\u2500" * inner_width, style="dim"))

        return content

    def _render_multi_header(self) -> list[Text]:
        """Render header for multi-file view."""
        count = len(self._file_nodes)
        header = Text(f" {count} files selected", style="bold")

        # Compute destinations
        dests: set[str] = set()
        for n in self._file_nodes:
            d = compute_dest(n, self._active_template(n))
            dests.add(d or "???")

        if len(dests) == 1:
            dest_line = Text(f" \u2192 {dests.pop()}")
        else:
            dest_line = Text(" \u2192 (various destinations)")

        return [header, dest_line]

    def _col_widths(self) -> tuple[int, int]:
        """Compute dynamic column widths based on widget width.

        Returns (result_col_width, source_col_width).
        """
        inner = max(0, self.size.width - 4)  # border + padding
        available = inner - LABEL_WIDTH - 1  # -1 for ┃ separator
        if available < 20:
            return (10, 10)
        half = available // 2
        return (half, available - half)

    def _col(self, text: str, width: int) -> str:
        """Pad or truncate text to width."""
        if len(text) > width:
            return text[: width - 1] + "\u2026"
        return text.ljust(width)

    def _render_grid_header(self) -> Text:
        """Render the column header row with optional cursor highlight."""
        result_w, source_w = self._col_widths()

        line = Text()

        # Label area (empty for header)
        line.append(" " * LABEL_WIDTH)

        # Result column header
        result_text = self._col("result", result_w)
        style = "on #264f78" if self.cursor_row == -1 else ""
        line.append(result_text, style=style)

        # Separator
        line.append("\u2503", style="dim")

        # Current source header with [N/M] indicator
        sources = self.node.sources
        if sources:
            idx = self.source_index
            src = sources[idx]
            src_header = Text()
            src_header.append(f"  {src.name}", style="#6796C0")
            if src.confidence:
                conf_text = f" ({src.confidence:.0%})"
                src_header.append(conf_text, style=confidence_style(src.confidence))
            indicator = f"  [{idx + 1}/{len(sources)}]"
            src_header.append(indicator, style="dim")
            # Pad to source column width
            plain_len = len(src_header.plain)
            if plain_len < source_w:
                src_header.append(" " * (source_w - plain_len))
            line.append_text(src_header)
        else:
            line.append(self._col("  (no sources)", source_w), style="dim")

        return line

    def _render_field_row(self, row_idx: int, field_name: str) -> Text:
        """Render a single field row with optional cursor highlight."""
        result_w, source_w = self._col_widths()
        shared = self._shared_result()

        line = Text()

        # Label
        label = f" {field_name:<{LABEL_WIDTH - 1}}"
        line.append(label, style="dim")

        # Result value
        result_raw = shared.get(field_name)
        if self.editing and self.cursor_row == row_idx:
            edit_display = self._edit_value + "\u2588"
            line.append(self._col(edit_display, result_w), style="underline")
        else:
            result_val = display_val(result_raw)
            style = ""
            if self.cursor_row == row_idx:
                style = "on #264f78"
            line.append(self._col(result_val, result_w), style=style)

        # Separator
        line.append("\u2503", style="dim")

        # Current source value (diff-styled relative to result)
        sources = self.node.sources
        if sources:
            src = sources[self.source_index]
            src_raw = src.fields.get(field_name)
            src_val = display_val(src_raw)
            if is_multi_value(result_raw):
                base_style = "dim"
            else:
                base_style = diff_style(result_raw, src_raw)
            if self.cursor_row == row_idx:
                base_style = "on #264f78"
            line.append(self._col(f"  {src_val}", source_w), style=base_style)
        else:
            line.append(self._col("  \u00b7", source_w), style="dim")

        return line

    def move_cursor(self, row_delta: int = 0) -> None:
        """Move cursor row, clamping to valid range."""
        if self.editing:
            return
        max_row = len(self._fields) - 1

        new_row = self.cursor_row + row_delta
        self.cursor_row = max(-1, min(max_row, new_row))

    def cycle_source(self, delta: int) -> None:
        """Cycle through sources with h/l. Clamp to [0, len(sources)-1]."""
        if self.editing:
            return
        sources = self.node.sources
        if not sources:
            return
        max_idx = len(sources) - 1
        new_idx = self.source_index + delta
        self.source_index = max(0, min(max_idx, new_idx))

    def _notify_before_mutate(self) -> None:
        """Notify the on_before_mutate callback before a mutation."""
        if self.on_before_mutate is not None:
            self.on_before_mutate(list(self._file_nodes))

    def apply_source_field(self) -> None:
        """Apply the current source field value to the result.

        If no sources exist, starts inline edit instead. When the cursor
        is on the header row (-1), applies all non-empty fields from the
        current source. Otherwise applies the single field at cursor_row.
        """
        sources = self.node.sources
        if not sources:
            # No sources, just allow editing result
            self._start_edit()
            return

        src_idx = self.source_index
        if src_idx >= len(sources):
            return

        self._notify_before_mutate()
        if self.cursor_row == -1:
            # Header row: apply all non-empty from this source
            self._apply_source_all(src_idx)
        else:
            # Single field: copy value to result for all nodes
            field_name = self._fields[self.cursor_row]
            val = sources[src_idx].fields.get(field_name)
            if val is not None:
                for n in self._file_nodes:
                    n.result[field_name] = val
        self.refresh()

    def apply_source_all_clear(self) -> None:
        """Handle shift-enter: apply all fields from source including empties."""
        if self.cursor_row != -1:
            return
        sources = self.node.sources
        if not sources:
            return
        src_idx = self.source_index
        if src_idx >= len(sources):
            return
        self._notify_before_mutate()
        src = sources[src_idx]
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
        if is_multi_value(current):
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

    def watch_source_index(self) -> None:
        """React to source index changes."""
        self.refresh()
