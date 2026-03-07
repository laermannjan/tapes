"""Textual widget that renders the file tree with cursor navigation."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget

from tapes.ui.tree_model import FileNode, FolderNode, TreeModel
from tapes.ui.tree_render import flatten_all_with_depth, flatten_with_depth, render_row

if TYPE_CHECKING:
    from rich.console import RenderableType


class TreeView(Widget):
    """Renders the file tree with cursor highlighting and navigation."""

    can_focus = True

    cursor_index: reactive[int] = reactive(0)
    active: reactive[bool] = reactive(True)

    def __init__(
        self,
        model: TreeModel,
        movie_template: str,
        tv_template: str,
        flat_mode: bool = False,
        root_path: Path | None = None,
    ) -> None:
        super().__init__()
        self.model = model
        self.movie_template = movie_template
        self.tv_template = tv_template
        self.flat_mode = flat_mode
        self.root_path = root_path
        self._items: list[tuple[FileNode | FolderNode, int]] = []
        self._all_items: list[tuple[FileNode | FolderNode, int]] = []
        self._range_anchor: int | None = None
        self._filter_text: str = ""
        self._scroll_offset: int = 0
        self._status_text: str = ""
        self._refresh_items()

    @property
    def in_range_mode(self) -> bool:
        """Whether range selection mode is active."""
        return self._range_anchor is not None

    @property
    def selected_range(self) -> tuple[int, int] | None:
        """Return (start, end) inclusive indices of the range, or None."""
        if self._range_anchor is None:
            return None
        lo = min(self._range_anchor, self.cursor_index)
        hi = max(self._range_anchor, self.cursor_index)
        return (lo, hi)

    def start_range_select(self) -> None:
        """Start or cancel range selection at current cursor position."""
        if self._range_anchor is not None:
            self._range_anchor = None
        else:
            self._range_anchor = self.cursor_index
        self.refresh()

    def clear_range_select(self) -> None:
        """Clear range selection."""
        self._range_anchor = None
        self.refresh()

    def selected_nodes(self) -> list[FileNode | FolderNode]:
        """Return nodes in the current selection range."""
        rng = self.selected_range
        if rng is None:
            return []
        lo, hi = rng
        return [self._items[i][0] for i in range(lo, hi + 1)]

    def _toggle_flag_range(self, attr: str) -> None:
        """Toggle a boolean flag on all FileNodes in the selection range."""
        nodes = self.selected_nodes()
        file_nodes = [n for n in nodes if isinstance(n, FileNode)]
        if not file_nodes:
            return
        all_set = all(getattr(f, attr) for f in file_nodes)
        for f in file_nodes:
            setattr(f, attr, not all_set)
        self.refresh()

    def toggle_staged_range(self) -> None:
        """Toggle staged on all FileNodes in the selection range."""
        self._toggle_flag_range("staged")

    def toggle_staged_at_cursor(self) -> None:
        """Toggle staged on cursor or range."""
        if self.in_range_mode:
            self.toggle_staged_range()
            self.clear_range_select()
        else:
            node = self.cursor_node()
            if isinstance(node, FileNode):
                self.model.toggle_staged(node)
                self.refresh()
            elif isinstance(node, FolderNode):
                self.model.toggle_staged_recursive(node)
                self.refresh()

    def toggle_ignored_range(self) -> None:
        """Toggle ignored on all FileNodes in the selection range."""
        self._toggle_flag_range("ignored")

    def toggle_ignored_at_cursor(self) -> None:
        """Toggle ignored on cursor or range."""
        if self.in_range_mode:
            self.toggle_ignored_range()
            self.clear_range_select()
        else:
            node = self.cursor_node()
            if isinstance(node, FileNode):
                self.model.toggle_ignored(node)
                self.refresh()
            elif isinstance(node, FolderNode):
                self.model.toggle_ignored_recursive(node)
                self.refresh()

    def _refresh_items(self) -> None:
        """Rebuild the flattened item list from the model."""
        if self.flat_mode:
            # In flat mode, show only files (no folders), all at depth 0
            self._all_items = [(f, 0) for f in self.model.all_files()]
        elif self._filter_text:
            # When filtering, flatten all items regardless of collapsed state
            # so files inside collapsed folders can be found
            self._all_items = flatten_all_with_depth(self.model)
        else:
            self._all_items = flatten_with_depth(self.model)

        if self._filter_text:
            self._apply_filter()
        else:
            self._items = list(self._all_items)

        self._scroll_offset = 0

    def set_status(self, text: str) -> None:
        """Set the status text displayed in the bottom border."""
        self._status_text = text
        self.refresh()

    def _border_style(self) -> str:
        """Return the Rich style string for the border."""
        return "cyan" if self.active else "dim"

    def render(self) -> RenderableType:
        """Render the visible window of the tree with cursor highlighting."""
        w = self.size.width
        border_style = self._border_style()

        # Top border: ┌─ Files ─...─┐
        title = " Files "
        top_fill = max(0, w - 2 - len(title))
        top_line = Text()
        top_line.append(f"\u250c\u2500{title}" + "\u2500" * top_fill + "\u2510", style=border_style)

        # Bottom border: ├── status ──┤  or  └─...─┘
        if self._status_text:
            status_str = f" {self._status_text} "
            bot_fill = max(0, w - 2 - len(status_str))
            bot_left = bot_fill // 2
            bot_right = bot_fill - bot_left
            bot_line = Text()
            bot_line.append(
                "\u251c" + "\u2500" * bot_left + status_str + "\u2500" * bot_right + "\u2524",
                style=border_style,
            )
        else:
            bot_line = Text()
            bot_line.append("\u2514" + "\u2500" * max(0, w - 2) + "\u2518", style=border_style)

        # Content area height = total height - 2 (top + bottom borders)
        content_height = max(0, self.size.height - 2)

        if not self._items:
            empty_text = "(empty)"
            pad = max(0, w - 2 - len(empty_text))
            content_line = Text()
            content_line.append("\u2502", style=border_style)
            content_line.append(empty_text + " " * pad)
            content_line.append("\u2502", style=border_style)
            content_lines = [content_line]
            # Fill remaining content area
            for _ in range(content_height - 1):
                blank = Text()
                blank.append("\u2502", style=border_style)
                blank.append(" " * max(0, w - 2))
                blank.append("\u2502", style=border_style)
                content_lines.append(blank)
            return Text("\n").join([top_line] + content_lines + [bot_line])

        # Adjust scroll offset for content area
        viewport_height = content_height
        if viewport_height <= 0:
            viewport_height = len(self._items)

        start = self._scroll_offset
        end = min(start + viewport_height, len(self._items))

        rng = self.selected_range
        content_lines: list[Text] = []
        inner_width = max(0, w - 2)
        for i in range(start, end):
            node, depth = self._items[i]
            effective_depth = 0 if self.flat_mode else depth
            row_result = render_row(
                node,
                self.movie_template,
                self.tv_template,
                depth=effective_depth,
                flat_mode=self.flat_mode,
                root_path=self.root_path,
            )
            # Convert to Text if render_row returned a plain string
            if isinstance(row_result, str):
                row_text = Text(row_result)
            else:
                row_text = row_result

            # Pad or truncate to fit inner width
            plain_len = len(row_text.plain)
            if plain_len > inner_width:
                row_text.truncate(inner_width)
            elif plain_len < inner_width:
                row_text.append(" " * (inner_width - plain_len))

            if isinstance(node, FileNode) and node.ignored:
                row_text.stylize("dim")
            if i == self.cursor_index:
                row_text.stylize("reverse")
            elif rng and rng[0] <= i <= rng[1]:
                row_text.stylize("on dark_blue")

            line = Text()
            line.append("\u2502", style=border_style)
            line.append_text(row_text)
            line.append("\u2502", style=border_style)
            content_lines.append(line)

        # Fill remaining content area with blank bordered rows
        for _ in range(viewport_height - len(content_lines)):
            blank = Text()
            blank.append("\u2502", style=border_style)
            blank.append(" " * inner_width)
            blank.append("\u2502", style=border_style)
            content_lines.append(blank)

        return Text("\n").join([top_line] + content_lines + [bot_line])

    def render_tree(self) -> str:
        """Render the full tree to a plain string (no cursor highlighting).

        Kept for backward compatibility with M2.
        """
        lines: list[str] = []
        for node, depth in self._items:
            effective_depth = 0 if self.flat_mode else depth
            row = render_row(
                node,
                self.movie_template,
                self.tv_template,
                depth=effective_depth,
                flat_mode=self.flat_mode,
                root_path=self.root_path,
            )
            lines.append(row.plain if isinstance(row, Text) else row)
        return "\n".join(lines)

    def move_cursor(self, delta: int) -> None:
        """Move the cursor by *delta* positions, clamping to bounds."""
        if not self._items:
            return
        new = max(0, min(len(self._items) - 1, self.cursor_index + delta))
        self.cursor_index = new

    def cursor_node(self) -> FileNode | FolderNode | None:
        """Return the node currently under the cursor."""
        if not self._items or self.cursor_index >= len(self._items):
            return None
        return self._items[self.cursor_index][0]

    def toggle_folder_at_cursor(self) -> None:
        """If the cursor is on a folder, toggle its collapsed state."""
        node = self.cursor_node()
        if isinstance(node, FolderNode):
            self.model.toggle_collapsed(node)
            self._refresh_items()
            # Clamp cursor if items shrank
            if self._items and self.cursor_index >= len(self._items):
                self.cursor_index = len(self._items) - 1
            elif not self._items:
                self.cursor_index = 0
            self.refresh()

    def refresh_tree(self) -> None:
        """Re-flatten and refresh the display."""
        self._refresh_items()
        if self._items and self.cursor_index >= len(self._items):
            self.cursor_index = len(self._items) - 1
        self.refresh()

    SCROLLOFF = 3

    def watch_active(self) -> None:
        """React to active state changes."""
        self.refresh()

    def watch_cursor_index(self) -> None:
        """React to cursor changes by scrolling and refreshing."""
        self._scroll_to_cursor()
        self.refresh()

    def _scroll_to_cursor(self) -> None:
        """Adjust scroll offset so cursor stays visible with scrolloff."""
        if not self._items:
            return
        viewport_height = self.size.height - 2  # account for top/bottom borders
        if viewport_height <= 0:
            return

        scrolloff = min(self.SCROLLOFF, viewport_height // 2)
        top = self._scroll_offset
        bottom = top + viewport_height - 1

        if self.cursor_index - scrolloff < top:
            self._scroll_offset = max(0, self.cursor_index - scrolloff)
        elif self.cursor_index + scrolloff > bottom:
            self._scroll_offset = max(
                0, self.cursor_index + scrolloff - viewport_height + 1
            )

    @property
    def staged_count(self) -> int:
        """Number of staged files."""
        return sum(1 for f in self.model.all_files() if f.staged)

    @property
    def total_count(self) -> int:
        """Total number of files."""
        return len(self.model.all_files())

    def toggle_flat_mode(self) -> None:
        """Toggle between flat and tree display modes.

        Tries to keep the cursor on the same node after toggling.
        """
        current_node = self.cursor_node()
        self.flat_mode = not self.flat_mode
        self._refresh_items()
        # Try to find the same node in the new item list
        if current_node is not None:
            for i, (node, _depth) in enumerate(self._items):
                if node is current_node:
                    self.cursor_index = i
                    break
            else:
                # Node not found (e.g. folder hidden in flat mode)
                if self._items:
                    self.cursor_index = min(
                        self.cursor_index, len(self._items) - 1
                    )
                else:
                    self.cursor_index = 0
        self.refresh()

    @property
    def filter_text(self) -> str:
        """The current filter text."""
        return self._filter_text

    def set_filter(self, text: str) -> None:
        """Filter displayed items to FileNodes whose filename contains text (case-insensitive).

        Folders containing matching files are auto-expanded and shown.
        """
        self._filter_text = text
        self._refresh_items()
        # Clamp cursor
        if self._items:
            if self.cursor_index >= len(self._items):
                self.cursor_index = 0
        else:
            self.cursor_index = 0
        self.refresh()

    def clear_filter(self) -> None:
        """Remove filter and restore the full tree."""
        self._filter_text = ""
        self._refresh_items()
        if self._items and self.cursor_index >= len(self._items):
            self.cursor_index = len(self._items) - 1
        self.refresh()

    def _apply_filter(self) -> None:
        """Apply the current filter text to narrow _items."""
        query = self._filter_text.lower()
        # Find matching file nodes
        matching_files: set[int] = set()
        for i, (node, _depth) in enumerate(self._all_items):
            if isinstance(node, FileNode) and query in node.path.name.lower():
                matching_files.add(i)

        if self.flat_mode:
            # In flat mode, just show matching files
            self._items = [
                (node, depth)
                for i, (node, depth) in enumerate(self._all_items)
                if i in matching_files
            ]
        else:
            # In tree mode, show matching files and their parent folders
            # A folder is shown if any descendant file matches
            keep: set[int] = set(matching_files)
            for file_idx in matching_files:
                # Walk backwards to find parent folders
                file_depth = self._all_items[file_idx][1]
                for j in range(file_idx - 1, -1, -1):
                    node_j, depth_j = self._all_items[j]
                    if isinstance(node_j, FolderNode) and depth_j < file_depth:
                        keep.add(j)
                        file_depth = depth_j
                    if depth_j == 0 and isinstance(node_j, FolderNode):
                        break
            self._items = [
                (node, depth)
                for i, (node, depth) in enumerate(self._all_items)
                if i in keep
            ]

    @property
    def ignored_count(self) -> int:
        """Number of ignored files."""
        return sum(1 for f in self.model.all_files() if f.ignored)

    @property
    def item_count(self) -> int:
        """Number of visible items."""
        return len(self._items)
