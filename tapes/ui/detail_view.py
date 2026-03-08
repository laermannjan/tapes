"""Interactive Textual widget for the detail view with cursor and editing."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.text import Text
from textual import events
from textual.reactive import reactive
from textual.widget import Widget

from tapes.fields import INT_FIELDS
from tapes.ui.detail_render import (
    confidence_style,
    diff_style,
    display_val,
    get_display_fields,
    is_multi_value,
)
from tapes.ui.tree_model import FileNode, compute_shared_fields
from tapes.ui.tree_render import (
    MUTED,
    compute_dest,
    render_dest,
    render_separator,
    select_template,
)

if TYPE_CHECKING:
    from rich.console import RenderableType

# Accent color for focused panel and active tab.
ACCENT = "#B1B9F9"
# Column gap between field names, values, and source values.
COL_GAP = "   "


class DetailView(Widget):
    """Detail view showing a file's metadata grid with cursor navigation.

    Supports single-node and multi-node modes. In multi-node mode,
    shared values are shown and edits apply to all nodes.
    """

    can_focus = True

    cursor_row: reactive[int] = reactive(0)   # 0+ = fields
    source_index: reactive[int] = reactive(0)  # which TMDB source tab
    editing: reactive[bool] = reactive(False)

    def __init__(
        self,
        node: FileNode,
        movie_template: str,
        tv_template: str,
        root_path: Path | None = None,
    ) -> None:
        super().__init__()
        self.node = node
        self.file_nodes: list[FileNode] = [node]
        self.movie_template = movie_template
        self.tv_template = tv_template
        self.root_path = root_path
        self.fields: list[str] = []
        self.edit_value: str = ""

    def _active_template(self, node: FileNode | None = None) -> str:
        """Return the template for the given (or primary) node."""
        if node is None:
            node = self.node
        return select_template(node, self.movie_template, self.tv_template)

    @property
    def is_multi(self) -> bool:
        """Whether multiple nodes are being displayed."""
        return len(self.file_nodes) > 1

    def on_mount(self) -> None:
        self.fields = get_display_fields(self._active_template())

    def set_node(self, node: FileNode) -> None:
        """Switch to a new file node, resetting cursor and edit state."""
        self.node = node
        self.file_nodes = [node]
        self.cursor_row = 0
        self.source_index = 0
        self.fields = get_display_fields(self._active_template(node))
        self.editing = False
        self.refresh()

    def set_nodes(self, nodes: list[FileNode]) -> None:
        """Switch to multiple file nodes for multi-file detail view."""
        if not nodes:
            return
        self.file_nodes = list(nodes)
        self.node = nodes[0]
        self.cursor_row = 0
        self.source_index = 0
        self.fields = get_display_fields(self._active_template(self.node))
        self.editing = False
        self.refresh()

    def _shared_result(self) -> dict[str, Any]:
        """Compute the shared result for multi-node display."""
        if not self.is_multi:
            return self.node.result
        return compute_shared_fields(self.file_nodes)

    def _display_path(self, node: FileNode) -> str:
        """Return the display path for a node (relative to root or just name)."""
        if self.root_path is not None:
            try:
                return str(node.path.relative_to(self.root_path))
            except ValueError:
                pass
        return node.path.name

    def render(self) -> RenderableType:
        """Build Rich Text content (visibility controlled by CSS)."""
        inner_width = self.size.width
        return Text("\n").join(self._build_content(inner_width))

    def _compute_col_widths(self) -> tuple[int, int, int]:
        """Compute auto-sized column widths: (label_w, value_w, source_w).

        Measures longest content in each column, adds padding, and divides
        remaining space proportionally. Source column only used when sources exist.
        """
        shared = self._shared_result()
        sources = self.node.sources
        gap = len(COL_GAP)

        # Measure label column
        label_w = max((len(f) for f in self.fields), default=6) + 2  # 2 left pad

        # Measure value column
        val_w = 6  # minimum
        for f in self.fields:
            v = display_val(shared.get(f))
            val_w = max(val_w, len(v))

        # Measure source column
        src_w = 0
        if sources and self.source_index < len(sources):
            src = sources[self.source_index]
            for f in self.fields:
                v = display_val(src.fields.get(f))
                src_w = max(src_w, len(v))
            src_w = max(src_w, 6)  # minimum

        inner = self.size.width
        used = label_w + gap + val_w
        if src_w:
            used += gap + src_w

        # If we have spare room, expand value column
        if used < inner and src_w == 0:
            val_w += inner - used
        elif used < inner:
            # Give extra to value column
            val_w += inner - used

        return (label_w, val_w, src_w)

    def _col(self, text: str, width: int) -> str:
        """Pad or truncate text to width."""
        if len(text) > width:
            return text[: width - 1] + "\u2026"
        return text.ljust(width)

    def _build_content(self, inner_width: int) -> list[Text]:
        """Render the full detail view with separator and footer hints."""
        content: list[Text] = []

        # Separator line
        content.append(render_separator(inner_width, title="Info", color=ACCENT))

        # Tab bar
        content.append(self._render_tab_bar(inner_width))

        # Blank line
        content.append(Text())

        # File path -> destination
        if self.is_multi:
            content.append(self._render_multi_path_line())
        else:
            content.append(self._render_path_line())

        # Blank line
        content.append(Text())

        # Field rows
        label_w, val_w, src_w = self._compute_col_widths()
        for row_idx, field_name in enumerate(self.fields):
            content.append(
                self._render_field_row(row_idx, field_name, label_w, val_w, src_w)
            )

        # Blank line + footer hints
        content.append(Text())
        content.append(self._render_footer_hints())

        return content

    def _render_tab_bar(self, inner_width: int) -> Text:
        """Render the tab bar with source tabs."""
        sources = self.node.sources

        line = Text()
        # Tabs for sources
        if sources:
            for idx, src in enumerate(sources):
                if idx > 0:
                    line.append("  ")
                tab_text = f" TMDB #{idx + 1} "
                if idx == self.source_index:
                    # Active tab: show confidence inline
                    if src.confidence:
                        tab_text = f" TMDB #{idx + 1} {src.confidence:.0%} "
                    line.append(tab_text, style=f"on {ACCENT} #000000")
                else:
                    line.append(tab_text)

            # Navigation hint
            if len(sources) > 1:
                line.append("   ")
                line.append(
                    "h/l to cycle",
                    style=f"italic {MUTED}",
                )
        else:
            line.append("(no TMDB matches)", style=MUTED)

        return line

    def _render_path_line(self) -> Text:
        """Render single file: path -> destination on one line."""
        line = Text()
        line.append(f"  {self._display_path(self.node)}")
        line.append("  ")
        line.append("\u2192 ", style=MUTED)
        dest = compute_dest(self.node, self._active_template())
        line.append_text(render_dest(dest))
        return line

    def _render_multi_path_line(self) -> Text:
        """Render multi-file summary: count + destinations."""
        count = len(self.file_nodes)
        line = Text()
        line.append(f"  {count} files selected", style="bold")

        dests: set[str] = set()
        for n in self.file_nodes:
            d = compute_dest(n, self._active_template(n))
            dests.add(d or "???")

        line.append("  ")
        line.append("\u2192 ", style=MUTED)
        if len(dests) == 1:
            line.append_text(render_dest(dests.pop()))
        else:
            line.append("(various destinations)", style=MUTED)
        return line

    def _render_footer_hints(self) -> Text:
        """Render contextual footer hints based on editing state."""
        if self.editing:
            return Text(
                " enter to confirm \u00b7 esc to cancel",
                style=f"italic {MUTED}",
            )
        return Text(
            " enter edit \u00b7 shift-enter apply all \u00b7 d clear \u00b7 g guessit \u00b7 tab sources \u00b7 c confirm \u00b7 esc discard",
            style=f"italic {MUTED}",
        )

    def _render_field_row(
        self,
        row_idx: int,
        field_name: str,
        label_w: int,
        val_w: int,
        src_w: int,
    ) -> Text:
        """Render a single field row with auto-sized columns."""
        shared = self._shared_result()
        sources = self.node.sources

        line = Text()

        # Label
        label = f"  {field_name:<{label_w - 2}}"
        line.append(label, style=MUTED)

        # Gap
        line.append(COL_GAP)

        # Value (editable)
        result_raw = shared.get(field_name)
        if self.editing and self.cursor_row == row_idx:
            edit_display = self.edit_value + "\u2588"
            line.append(self._col(edit_display, val_w), style="underline")
        else:
            result_val = display_val(result_raw)
            style = "bold" if self.cursor_row == row_idx else ""
            line.append(self._col(result_val, val_w), style=style)

        # Source value (from active tab, if any)
        if sources and src_w > 0 and self.source_index < len(sources):
            src = sources[self.source_index]
            src_raw = src.fields.get(field_name)
            src_val = display_val(src_raw)

            line.append(COL_GAP)

            if is_multi_value(result_raw):
                base_style = "dim"
            else:
                base_style = diff_style(result_raw, src_raw)
            line.append(self._col(src_val, src_w), style=base_style)

        return line

    # ------------------------------------------------------------------
    # Cursor and editing
    # ------------------------------------------------------------------

    def move_cursor(self, row_delta: int = 0) -> None:
        """Move cursor row, clamping to valid range."""
        if self.editing:
            return
        max_row = len(self.fields) - 1
        new_row = self.cursor_row + row_delta
        self.cursor_row = max(0, min(max_row, new_row))

    def cycle_source(self, delta: int) -> None:
        """Cycle through source tabs with h/l."""
        if self.editing:
            return
        sources = self.node.sources
        if not sources:
            return
        max_idx = len(sources) - 1
        new_idx = self.source_index + delta
        self.source_index = max(0, min(max_idx, new_idx))

    def apply_source_all_clear(self) -> None:
        """Handle shift-enter: apply all fields from current source."""
        sources = self.node.sources
        if not sources:
            return
        src_idx = self.source_index
        if src_idx >= len(sources):
            return
        src = sources[src_idx]
        for field_name in self.fields:
            val = src.fields.get(field_name)
            if val is not None:
                for n in self.file_nodes:
                    n.result[field_name] = val
            else:
                for n in self.file_nodes:
                    n.result.pop(field_name, None)
        self.refresh()

    def start_edit(self) -> None:
        """Enter inline edit mode for the current result field."""
        if self.cursor_row < 0:
            return
        field_name = self.fields[self.cursor_row]
        shared = self._shared_result()
        current = shared.get(field_name)
        if is_multi_value(current):
            self.edit_value = ""
        else:
            self.edit_value = str(current) if current is not None else ""
        self.editing = True
        self.refresh()

    def commit_edit(self) -> None:
        """Save the edited value to the result for all nodes."""
        field_name = self.fields[self.cursor_row]
        val: str | int = self.edit_value
        if field_name in INT_FIELDS:
            try:
                val = int(val)
            except ValueError:
                pass
        for n in self.file_nodes:
            n.result[field_name] = val
            if field_name != "tmdb_id":
                n.result.pop("tmdb_id", None)
        self.editing = False
        self.refresh()

    def cancel_edit(self) -> None:
        """Discard the edit and exit edit mode."""
        self.editing = False
        self.refresh()

    def clear_field(self) -> None:
        """Clear the current field (remove from result)."""
        if self.editing:
            return
        field_name = self.fields[self.cursor_row]
        for n in self.file_nodes:
            n.result.pop(field_name, None)
        self.refresh()

    def reset_field_to_guessit(self) -> None:
        """Reset the current field to its guessit-extracted value."""
        if self.editing:
            return
        from tapes.ui.pipeline import extract_guessit_fields

        field_name = self.fields[self.cursor_row]
        for n in self.file_nodes:
            guessit_fields = extract_guessit_fields(n.path.name)
            val = guessit_fields.get(field_name)
            if val is not None:
                n.result[field_name] = val
            else:
                n.result.pop(field_name, None)
        self.refresh()

    def on_key(self, event: events.Key) -> None:
        """Handle key events for inline editing."""
        if event.key == "tab" and not self.editing:
            self.cycle_source(1)
            self.refresh()
            event.prevent_default()
            event.stop()
            return

        if not self.editing:
            return

        if event.key == "enter":
            self.commit_edit()
            event.prevent_default()
            event.stop()
        elif event.key == "escape":
            self.cancel_edit()
            event.prevent_default()
            event.stop()
        elif event.key == "backspace":
            self.edit_value = self.edit_value[:-1]
            self.refresh()
            event.prevent_default()
            event.stop()
        elif event.character and event.is_printable:
            self.edit_value += event.character
            self.refresh()
            event.prevent_default()
            event.stop()
