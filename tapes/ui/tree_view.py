"""Textual widget that renders the file tree with cursor navigation."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget

from tapes.ui.tree_model import FileNode, FolderNode, TreeModel
from tapes.ui.tree_render import flatten_with_depth, render_row

if TYPE_CHECKING:
    from rich.console import RenderableType


class TreeView(Widget):
    """Renders the file tree with cursor highlighting and navigation."""

    can_focus = True

    cursor_index: reactive[int] = reactive(0)

    def __init__(
        self,
        model: TreeModel,
        template: str,
        flat_mode: bool = False,
        root_path: Path | None = None,
    ) -> None:
        super().__init__()
        self.model = model
        self.template = template
        self.flat_mode = flat_mode
        self.root_path = root_path
        self._items: list[tuple[FileNode | FolderNode, int]] = []
        self._range_anchor: int | None = None
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

    def toggle_staged_range(self) -> None:
        """Toggle staged on all FileNodes in the selection range."""
        nodes = self.selected_nodes()
        file_nodes = [n for n in nodes if isinstance(n, FileNode)]
        if not file_nodes:
            return
        all_staged = all(f.staged for f in file_nodes)
        for f in file_nodes:
            f.staged = not all_staged
        self.refresh()

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

    def _refresh_items(self) -> None:
        """Rebuild the flattened item list from the model."""
        self._items = flatten_with_depth(self.model)

    def render(self) -> RenderableType:
        """Render the tree with cursor highlighting."""
        if not self._items:
            return Text("(empty)")

        rng = self.selected_range
        lines: list[Text] = []
        for i, (node, depth) in enumerate(self._items):
            effective_depth = 0 if self.flat_mode else depth
            row_str = render_row(
                node,
                self.template,
                depth=effective_depth,
                flat_mode=self.flat_mode,
                root_path=self.root_path,
            )
            line = Text(row_str)
            if i == self.cursor_index:
                line.stylize("reverse")
            elif rng and rng[0] <= i <= rng[1]:
                line.stylize("on dark_blue")
            lines.append(line)

        result = Text("\n").join(lines)
        return result

    def render_tree(self) -> str:
        """Render the full tree to a plain string (no cursor highlighting).

        Kept for backward compatibility with M2.
        """
        lines: list[str] = []
        for node, depth in self._items:
            effective_depth = 0 if self.flat_mode else depth
            line = render_row(
                node,
                self.template,
                depth=effective_depth,
                flat_mode=self.flat_mode,
                root_path=self.root_path,
            )
            lines.append(line)
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

    def refresh_tree(self) -> None:
        """Re-flatten and refresh the display."""
        self._refresh_items()
        if self._items and self.cursor_index >= len(self._items):
            self.cursor_index = len(self._items) - 1
        self.refresh()

    def watch_cursor_index(self) -> None:
        """React to cursor changes by refreshing the display."""
        self.refresh()

    @property
    def staged_count(self) -> int:
        """Number of staged files."""
        return sum(1 for f in self.model.all_files() if f.staged)

    @property
    def total_count(self) -> int:
        """Total number of files."""
        return len(self.model.all_files())

    @property
    def item_count(self) -> int:
        """Number of visible items."""
        return len(self._items)
