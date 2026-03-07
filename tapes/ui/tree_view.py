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
        self._refresh_items()

    def _refresh_items(self) -> None:
        """Rebuild the flattened item list from the model."""
        self._items = flatten_with_depth(self.model)

    def render(self) -> RenderableType:
        """Render the tree with cursor highlighting."""
        if not self._items:
            return Text("(empty)")

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
    def item_count(self) -> int:
        """Number of visible items."""
        return len(self._items)
