"""Interactive Textual widget for the metadata view with cursor and editing."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.text import Text
from textual import events
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget

from tapes.fields import INT_FIELDS, MEDIA_TYPE, MEDIA_TYPE_EPISODE, SEASON, TMDB_ID
from tapes.templates import compute_dest, select_template
from tapes.tree_model import FileNode, compute_shared_fields
from tapes.ui.colors import COLOR_ACCENT, COLOR_COLUMN_FOCUS_BG, COLOR_CURSOR_BG, COLOR_MUTED
from tapes.ui.metadata_render import (
    diff_style,
    display_val,
    get_display_fields,
    is_multi_value,
)
from tapes.ui.tree_render import render_dest, render_separator

if TYPE_CHECKING:
    from rich.console import RenderableType

# Column gap between field names, values, and candidate values.
COL_GAP = "   "


class MetadataView(Widget):
    """Metadata view showing a file's metadata grid with cursor navigation.

    Supports single-node and multi-node modes. In multi-node mode,
    shared values are shown and edits apply to all nodes.
    """

    class MetadataChanged(Message):
        """Posted when metadata fields are mutated (edit, ctrl+a, clear, etc.)."""

    can_focus = True

    cursor_row: reactive[int] = reactive(0)  # 0+ = fields
    candidate_index: reactive[int] = reactive(0)  # which TMDB candidate tab
    editing: reactive[bool] = reactive(False)
    quit_hint: reactive[str] = reactive("")

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
        self.focus_column: str = "candidate"  # "metadata" or "candidate"

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
        self.candidate_index = 0
        self.focus_column = "candidate"
        self.fields = get_display_fields(self._active_template(node))
        self.editing = False
        self.refresh()

    def set_nodes(self, nodes: list[FileNode]) -> None:
        """Switch to multiple file nodes for multi-file metadata view."""
        if not nodes:
            return
        self.file_nodes = list(nodes)
        self.node = nodes[0]
        self.cursor_row = 0
        self.candidate_index = 0
        self.focus_column = "candidate"
        self.fields = get_display_fields(self._active_template(self.node))
        self.editing = False
        self.refresh()

    def _shared_result(self) -> dict[str, Any]:
        """Compute the shared metadata for multi-node display."""
        if not self.is_multi:
            return self.node.metadata
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
        """Compute auto-sized column widths: (label_w, value_w, candidate_w).

        Label and value columns are measured by content. The candidate column
        starts after a gap. The label+gap+value portion is capped at 50%
        of the widget width so the candidate column stays visible.
        """
        shared = self._shared_result()
        candidates = self.node.candidates
        gap = len(COL_GAP)
        inner = self.size.width

        label_w = max((len(f) for f in self.fields), default=6) + 4
        val_w = 6
        for f in self.fields:
            v = display_val(shared.get(f))
            val_w = max(val_w, len(v))

        cand_w = 0
        if candidates and self.candidate_index < len(candidates):
            cand = candidates[self.candidate_index]
            for f in self.fields:
                v = display_val(cand.metadata.get(f))
                cand_w = max(cand_w, len(v))
            cand_w = max(cand_w, 6)

        # Cap label+gap+value at 50% so the candidate column stays visible.
        if cand_w > 0:
            max_left = inner // 2
            left_used = label_w + gap + val_w
            if left_used > max_left:
                val_w = max(6, max_left - label_w - gap)

        return (label_w, val_w, cand_w)

    def _col(self, text: str, width: int) -> str:
        """Pad or truncate text to width."""
        if len(text) > width:
            return text[: width - 1] + "\u2026"
        return text.ljust(width)

    def _build_content(self, inner_width: int) -> list[Text]:
        """Render the full metadata view with separator and footer hints."""
        content: list[Text] = []

        content.append(Text())
        content.append(render_separator(inner_width, title="Metadata", color=COLOR_ACCENT))
        content.append(Text())

        if self.is_multi:
            content.append(self._render_multi_path_line())
        else:
            content.append(self._render_path_line())

        content.append(Text())
        content.append(self._render_tab_bar(inner_width))
        content.append(Text())

        label_w, val_w, cand_w = self._compute_col_widths()
        for row_idx, field_name in enumerate(self.fields):
            content.append(self._render_field_row(row_idx, field_name, label_w, val_w, cand_w, inner_width))

        content.append(Text())
        content.append(self._render_footer_hints())

        return content

    def _render_tab_bar(self, inner_width: int) -> Text:  # noqa: ARG002
        """Render the tab bar with candidate tabs or multi-node hint."""
        line = Text()
        line.append("    ")

        # B2: In multi-node mode with an accepted show (tmdb_id set),
        # show a hint instead of episode candidate tabs.
        if self.is_multi:
            shared = self._shared_result()
            if shared.get(TMDB_ID) is not None and shared.get(MEDIA_TYPE) == MEDIA_TYPE_EPISODE:
                line.append("Select individual files to match episodes", style=COLOR_MUTED)
                if any(n.metadata.get(SEASON) is None for n in self.file_nodes):
                    line.append("  \u00b7  ", style=COLOR_MUTED)
                    line.append("Set season to improve matching", style=COLOR_MUTED)
                return line

        candidates = self.node.candidates

        if candidates:
            for idx, cand in enumerate(candidates):
                if idx > 0:
                    line.append("  ")
                conf = f" [{cand.score:.0%}]" if cand.score else ""
                tab_text = f" TMDB #{idx + 1}{conf} "
                if idx == self.candidate_index:
                    line.append(tab_text, style=f"on {COLOR_ACCENT} #000000")
                else:
                    line.append(tab_text)

            line.append("   ")
            line.append(
                "(tab to cycle)",
                style=COLOR_MUTED,
            )
        else:
            line.append("(no TMDB candidates)", style=COLOR_MUTED)

        return line

    def _render_path_line(self) -> Text:
        """Render single file: path -> destination on one line."""
        line = Text()
        line.append(f"    {self._display_path(self.node)}")
        line.append("  ")
        line.append("\u2192 ", style=COLOR_MUTED)
        dest = compute_dest(self.node, self._active_template())
        line.append_text(render_dest(dest))
        return line

    def _render_multi_path_line(self) -> Text:
        """Render multi-file summary: count + destinations."""
        count = len(self.file_nodes)
        line = Text()
        line.append(f"    {count} files selected", style="bold")

        dests: set[str] = set()
        for n in self.file_nodes:
            d = compute_dest(n, self._active_template(n))
            dests.add(d or "???")

        line.append("  ")
        line.append("\u2192 ", style=COLOR_MUTED)
        if len(dests) == 1:
            line.append_text(render_dest(dests.pop()))
        else:
            line.append("(various destinations)", style=COLOR_MUTED)
        return line

    def _render_footer_hints(self) -> Text:
        """Render contextual footer hints based on editing state."""
        if self.quit_hint:
            return Text(f"    {self.quit_hint}", style=f"italic {COLOR_MUTED}")
        if self.editing:
            return Text(
                "    enter to confirm \u00b7 esc to cancel",
                style=f"italic {COLOR_MUTED}",
            )
        hints = (
            "    enter to accept \u00b7 esc to discard"
            " \u00b7 e to edit \u00b7 tab/shift+tab to cycle candidates"
            " \u00b7 r to refresh \u00b7 ctrl+r to reset from filename"
        )
        return Text(hints, style=f"italic {COLOR_MUTED}")

    def _render_field_row(
        self,
        row_idx: int,
        field_name: str,
        label_w: int,
        val_w: int,
        cand_w: int,
        inner_width: int = 0,
    ) -> Text:
        """Render a single field row with auto-sized columns."""
        shared = self._shared_result()
        candidates = self.node.candidates
        is_cursor = self.cursor_row == row_idx

        line = Text()

        label = f"    {field_name:<{label_w - 4}}"
        line.append(label, style=COLOR_MUTED)
        line.append(COL_GAP)

        meta_raw = shared.get(field_name)
        if self.editing and is_cursor:
            edit_display = self.edit_value + "\u2588"
            line.append(self._col(edit_display, val_w), style="underline")
        else:
            meta_val = display_val(meta_raw)
            val_style = "bold" if is_cursor else ""
            if self.focus_column == "metadata":
                val_style += f" {COLOR_COLUMN_FOCUS_BG}"
            line.append(self._col(meta_val, val_w), style=val_style)

        if candidates and cand_w > 0 and self.candidate_index < len(candidates):
            cand = candidates[self.candidate_index]
            cand_raw = cand.metadata.get(field_name)
            cand_val = display_val(cand_raw)

            line.append(COL_GAP)

            base_style = "dim" if is_multi_value(meta_raw) else diff_style(meta_raw, cand_raw)
            if self.focus_column == "candidate":
                base_style += f" {COLOR_COLUMN_FOCUS_BG}"
            line.append(self._col(cand_val, cand_w), style=base_style)

        if is_cursor and inner_width > 0:
            plain_len = len(line.plain)
            if plain_len < inner_width:
                line.append(" " * (inner_width - plain_len))
            line.stylize(COLOR_CURSOR_BG)

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

    def cycle_candidate(self, delta: int) -> None:
        """Cycle through candidate tabs."""
        if self.editing:
            return
        candidates = self.node.candidates
        if not candidates:
            return
        self.candidate_index = (self.candidate_index + delta) % len(candidates)
        self.focus_column = "candidate"

    def accept_current_candidate(self) -> None:
        """Accept all fields from the current candidate.

        Only sets fields that are present in the candidate. Fields the candidate
        doesn't have are left untouched, preserving per-file metadata like
        season/episode when accepting a show-level TMDB match.
        """
        candidates = self.node.candidates
        if not candidates:
            return
        cand_idx = self.candidate_index
        if cand_idx >= len(candidates):
            return
        cand = candidates[cand_idx]
        for field_name in self.fields:
            val = cand.metadata.get(field_name)
            if val is not None:
                for n in self.file_nodes:
                    n.metadata[field_name] = val
        # A3: clear candidates after acceptance sets tmdb_id.
        if any(n.metadata.get(TMDB_ID) is not None for n in self.file_nodes):
            for n in self.file_nodes:
                n.candidates.clear()
        self.refresh()
        self.post_message(self.MetadataChanged())

    def start_edit(self) -> None:
        """Enter inline edit mode for the current metadata field."""
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

    def apply_edit(self) -> None:
        """Save the edited value to the metadata for all nodes."""
        field_name = self.fields[self.cursor_row]
        val: str | int = self.edit_value
        if field_name in INT_FIELDS:
            with contextlib.suppress(ValueError):
                val = int(val)
        for n in self.file_nodes:
            n.metadata[field_name] = val
            if field_name != "tmdb_id":
                n.metadata.pop("tmdb_id", None)
        self.editing = False
        self.refresh()
        self.post_message(self.MetadataChanged())

    def cancel_edit(self) -> None:
        """Discard the edit and exit edit mode."""
        self.editing = False
        self.refresh()

    def clear_field(self) -> None:
        """Clear the current field (remove from metadata)."""
        if self.editing:
            return
        field_name = self.fields[self.cursor_row]
        for n in self.file_nodes:
            n.metadata.pop(field_name, None)
        self.refresh()
        self.post_message(self.MetadataChanged())

    def reset_field_to_guessit(self) -> None:
        """Reset the current field to its guessit-extracted value."""
        if self.editing:
            return
        from tapes.pipeline import extract_guessit_fields

        field_name = self.fields[self.cursor_row]
        for n in self.file_nodes:
            guessit_fields = extract_guessit_fields(n.path.name)
            val = guessit_fields.get(field_name)
            if val is not None:
                n.metadata[field_name] = val
            else:
                n.metadata.pop(field_name, None)
        self.refresh()

    def toggle_column_focus(self) -> None:
        """Toggle focus between metadata and candidate columns."""
        if self.focus_column == "metadata":
            self.focus_column = "candidate"
        else:
            self.focus_column = "metadata"
        self.refresh()

    def accept_focused_column(self) -> None:
        """Accept the focused column's values.

        If candidate is focused, copies non-None fields from the current
        candidate to the metadata (preserving fields the candidate doesn't have).
        If metadata is focused, no changes needed -- metadata is kept as-is.
        """
        if self.focus_column == "candidate":
            self.accept_current_candidate()

    def on_key(self, event: events.Key) -> None:
        """Handle key events for inline editing."""
        if event.key == "tab" and not self.editing:
            self.cycle_candidate(1)
            self.refresh()
            event.prevent_default()
            event.stop()
            return

        if not self.editing:
            return

        if event.key == "enter":
            self.apply_edit()
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
