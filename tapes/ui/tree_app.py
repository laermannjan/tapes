"""Textual App for the tree-based file browser."""
from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Static

from tapes.ui.tree_model import FolderNode, TreeModel
from tapes.ui.tree_view import TreeView


class TreeApp(App):
    """Interactive tree browser with cursor navigation."""

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("j,down", "cursor_down", "Down"),
        Binding("k,up", "cursor_up", "Up"),
        Binding("enter", "toggle_or_enter", "Toggle"),
        Binding("space", "toggle_staged", "Stage"),
    ]

    CSS = """
    TreeView {
        height: 1fr;
        overflow-y: auto;
    }
    """

    def __init__(
        self,
        model: TreeModel,
        template: str,
        root_path: Path | None = None,
    ) -> None:
        super().__init__()
        self.model = model
        self.template = template
        self.root_path = root_path

    def compose(self) -> ComposeResult:
        yield Header()
        yield TreeView(
            self.model,
            self.template,
            root_path=self.root_path,
        )
        yield Static("0 staged / 0 total", id="status")
        yield Footer()

    def on_mount(self) -> None:
        self._update_footer()

    def action_cursor_down(self) -> None:
        self.query_one(TreeView).move_cursor(1)

    def action_cursor_up(self) -> None:
        self.query_one(TreeView).move_cursor(-1)

    def action_toggle_staged(self) -> None:
        tv = self.query_one(TreeView)
        tv.toggle_staged_at_cursor()
        self._update_footer()

    def action_toggle_or_enter(self) -> None:
        tv = self.query_one(TreeView)
        node = tv.cursor_node()
        if isinstance(node, FolderNode):
            tv.toggle_folder_at_cursor()

    def _update_footer(self) -> None:
        tv = self.query_one(TreeView)
        status = self.query_one("#status", Static)
        status.update(f"{tv.staged_count} staged / {tv.total_count} total")
