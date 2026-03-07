"""Textual App for the tree-based file browser."""
from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.events import Key
from textual.widgets import Footer, Header, Static

from tapes.ui.detail_view import DetailView
from tapes.ui.tree_model import (
    FileNode,
    FolderNode,
    TreeModel,
    UndoManager,
    accept_best_source,
)
from tapes.ui.tree_view import TreeView


class TreeApp(App):
    """Interactive tree browser with cursor navigation."""

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("j,down", "cursor_down", "Down"),
        Binding("k,up", "cursor_up", "Up"),
        Binding("h,left", "cursor_left", "Left"),
        Binding("l,right", "cursor_right", "Right"),
        Binding("enter", "toggle_or_enter", "Toggle"),
        Binding("shift+enter", "apply_all_clear", "Apply All", show=False),
        Binding("space", "toggle_staged", "Stage"),
        Binding("v", "range_select", "Range Select"),
        Binding("escape", "cancel", "Cancel"),
        Binding("u", "undo", "Undo"),
        Binding("x", "toggle_ignored", "Ignore"),
        Binding("c", "commit", "Commit"),
        Binding("a", "accept_best", "Accept"),
        Binding("r", "refresh_query", "Refresh"),
        Binding("grave_accent", "toggle_flat", "Flat/Tree"),
        Binding("slash", "start_search", "Search"),
    ]

    CSS = """
    TreeView {
        height: 1fr;
        overflow-y: auto;
    }
    DetailView {
        height: 1fr;
        overflow-y: auto;
        display: none;
    }
    """

    def __init__(
        self,
        model: TreeModel,
        template: str,
        root_path: Path | None = None,
        auto_pipeline: bool = False,
    ) -> None:
        super().__init__()
        self.model = model
        self.template = template
        self.root_path = root_path
        self._in_detail = False
        self._undo = UndoManager()
        self._confirming_commit = False
        self._auto_pipeline = auto_pipeline
        self._searching = False
        self._search_query = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield TreeView(
            self.model,
            self.template,
            root_path=self.root_path,
        )
        # Hidden until a file is selected; set_node() replaces the placeholder
        yield DetailView(
            FileNode(path=Path("placeholder")),
            self.template,
        )
        yield Static("0 staged / 0 total", id="status")
        yield Footer()

    def on_mount(self) -> None:
        if self._auto_pipeline:
            from tapes.ui.pipeline import run_auto_pipeline

            run_auto_pipeline(self.model)
            self.query_one(TreeView).refresh_tree()
        self._update_footer()

    def _show_detail(self, node: FileNode) -> None:
        """Switch from tree view to detail view for a file node."""
        self._in_detail = True
        detail = self.query_one(DetailView)
        detail.set_node(node)
        detail.on_before_mutate = self._snapshot_before_mutate
        self.query_one(TreeView).display = False
        detail.display = True
        detail.focus()

    def _show_detail_multi(self, nodes: list[FileNode]) -> None:
        """Switch from tree view to detail view for multiple file nodes."""
        self._in_detail = True
        detail = self.query_one(DetailView)
        detail.set_nodes(nodes)
        detail.on_before_mutate = self._snapshot_before_mutate
        self.query_one(TreeView).display = False
        detail.display = True
        detail.focus()

    def _snapshot_before_mutate(self, nodes: list[FileNode]) -> None:
        """Save undo snapshot before a mutation."""
        self._undo.snapshot(nodes)

    def _show_tree(self) -> None:
        """Switch from detail view back to tree view."""
        self._in_detail = False
        detail = self.query_one(DetailView)
        detail.display = False
        tv = self.query_one(TreeView)
        tv.display = True
        tv.focus()
        tv.refresh()
        self._update_footer()

    def action_cursor_down(self) -> None:
        if self._in_detail:
            self.query_one(DetailView).move_cursor(row_delta=1)
        else:
            self.query_one(TreeView).move_cursor(1)

    def action_cursor_up(self) -> None:
        if self._in_detail:
            self.query_one(DetailView).move_cursor(row_delta=-1)
        else:
            self.query_one(TreeView).move_cursor(-1)

    def action_cursor_left(self) -> None:
        if self._in_detail:
            self.query_one(DetailView).move_cursor(col_delta=-1)

    def action_cursor_right(self) -> None:
        if self._in_detail:
            self.query_one(DetailView).move_cursor(col_delta=1)

    def action_toggle_staged(self) -> None:
        if self._in_detail:
            return
        tv = self.query_one(TreeView)
        tv.toggle_staged_at_cursor()
        self._update_footer()

    def action_toggle_or_enter(self) -> None:
        if self._confirming_commit:
            self._confirming_commit = False
            tv = self.query_one(TreeView)
            staged = [f for f in self.model.all_files() if f.staged]
            self.exit(result=staged)
            return
        if self._in_detail:
            dv = self.query_one(DetailView)
            dv.apply_source_field()
            return
        tv = self.query_one(TreeView)
        if tv.in_range_mode:
            nodes = tv.selected_nodes()
            file_nodes = [n for n in nodes if isinstance(n, FileNode)]
            if file_nodes:
                self._show_detail_multi(file_nodes)
            tv.clear_range_select()
            return
        node = tv.cursor_node()
        if isinstance(node, FolderNode):
            tv.toggle_folder_at_cursor()
        elif isinstance(node, FileNode):
            self._show_detail(node)

    def action_apply_all_clear(self) -> None:
        if self._in_detail:
            self.query_one(DetailView).apply_source_all_clear()

    def action_range_select(self) -> None:
        if self._in_detail:
            return
        self.query_one(TreeView).start_range_select()

    def action_cancel(self) -> None:
        if self._searching:
            self._finish_search(keep_filter=False)
            return
        if self._confirming_commit:
            self._confirming_commit = False
            self._update_footer()
            return
        if self._in_detail:
            dv = self.query_one(DetailView)
            if dv.editing:
                dv._cancel_edit()
            else:
                self._show_tree()
            return
        tv = self.query_one(TreeView)
        if tv.in_range_mode:
            tv.clear_range_select()

    def action_toggle_ignored(self) -> None:
        if self._in_detail:
            return
        tv = self.query_one(TreeView)
        tv.toggle_ignored_at_cursor()
        self._update_footer()

    def action_commit(self) -> None:
        if self._in_detail:
            return
        tv = self.query_one(TreeView)
        if tv.staged_count == 0:
            status = self.query_one("#status", Static)
            status.update("No staged files to commit")
            return
        self._confirming_commit = True
        status = self.query_one("#status", Static)
        count = tv.staged_count
        status.update(
            f"{count} file{'s' if count != 1 else ''} staged. "
            "Press enter to confirm, esc to cancel."
        )

    def action_refresh_query(self) -> None:
        from tapes.ui.pipeline import refresh_tmdb_source

        if self._in_detail:
            dv = self.query_one(DetailView)
            self._undo.snapshot(dv._file_nodes)
            for fn in dv._file_nodes:
                refresh_tmdb_source(fn)
            dv.refresh()
        else:
            tv = self.query_one(TreeView)
            if tv.in_range_mode:
                nodes = tv.selected_nodes()
                file_nodes = [n for n in nodes if isinstance(n, FileNode)]
                if file_nodes:
                    self._undo.snapshot(file_nodes)
                    for fn in file_nodes:
                        refresh_tmdb_source(fn)
                tv.clear_range_select()
            else:
                node = tv.cursor_node()
                if isinstance(node, FileNode):
                    self._undo.snapshot([node])
                    refresh_tmdb_source(node)
            tv.refresh()
        self._update_footer()

    def action_accept_best(self) -> None:
        if self._in_detail:
            return
        tv = self.query_one(TreeView)
        if tv.in_range_mode:
            nodes = tv.selected_nodes()
            file_nodes = [n for n in nodes if isinstance(n, FileNode)]
            if file_nodes:
                self._undo.snapshot(file_nodes)
                for fn in file_nodes:
                    accept_best_source(fn)
            tv.clear_range_select()
        else:
            node = tv.cursor_node()
            if isinstance(node, FileNode) and node.sources:
                self._undo.snapshot([node])
                accept_best_source(node)
        tv.refresh()
        self._update_footer()

    def action_start_search(self) -> None:
        if self._in_detail:
            return
        self._searching = True
        self._search_query = ""
        self._update_search_status()

    def _update_search_status(self) -> None:
        """Update the status bar to show the search query."""
        status = self.query_one("#status", Static)
        status.update(f"/{self._search_query}")

    def _finish_search(self, keep_filter: bool) -> None:
        """Exit search mode. If keep_filter is False, clear the filter."""
        self._searching = False
        if not keep_filter:
            self._search_query = ""
            self.query_one(TreeView).clear_filter()
        self._update_footer()

    def on_key(self, event: Key) -> None:
        """Intercept key events during search mode."""
        if not self._searching:
            return

        if event.key == "escape":
            event.prevent_default()
            event.stop()
            self._finish_search(keep_filter=False)
        elif event.key == "enter":
            event.prevent_default()
            event.stop()
            self._finish_search(keep_filter=True)
        elif event.key == "backspace":
            event.prevent_default()
            event.stop()
            self._search_query = self._search_query[:-1]
            self.query_one(TreeView).set_filter(self._search_query)
            self._update_search_status()
        elif event.character and event.is_printable:
            event.prevent_default()
            event.stop()
            self._search_query += event.character
            self.query_one(TreeView).set_filter(self._search_query)
            self._update_search_status()
        else:
            # For non-printable keys (like arrows), prevent normal bindings
            event.prevent_default()
            event.stop()

    def action_toggle_flat(self) -> None:
        if self._in_detail:
            return
        self.query_one(TreeView).toggle_flat_mode()

    def action_undo(self) -> None:
        if self._undo.undo():
            if self._in_detail:
                self.query_one(DetailView).refresh()
            else:
                self.query_one(TreeView).refresh()
            self._update_footer()

    def _update_footer(self) -> None:
        tv = self.query_one(TreeView)
        status = self.query_one("#status", Static)
        ignored = tv.ignored_count
        parts = [f"{tv.staged_count} staged"]
        if ignored:
            parts.append(f"{ignored} ignored")
        parts.append(f"{tv.total_count} total")
        status.update(" / ".join(parts))
