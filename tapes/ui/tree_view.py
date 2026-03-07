"""Textual widget that renders the file tree as styled text."""
from __future__ import annotations

from pathlib import Path

from textual.widgets import Static

from tapes.ui.tree_model import TreeModel
from tapes.ui.tree_render import flatten_with_depth, render_row


class TreeView(Static):
    """Renders the file tree as styled text."""

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

    def render_tree(self) -> str:
        """Render the full tree to a string."""
        lines: list[str] = []
        items = flatten_with_depth(self.model)
        for node, depth in items:
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

    def on_mount(self) -> None:
        """Populate the widget content on mount."""
        self.update(self.render_tree())
