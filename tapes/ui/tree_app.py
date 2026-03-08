"""Textual App for the tree-based file browser."""
from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.events import Key

from tapes.config import TapesConfig
from tapes.fields import MEDIA_TYPE, MEDIA_TYPE_EPISODE
from tapes.ui.bottom_bar import BottomBar
from tapes.ui.commit_modal import CommitScreen
from tapes.ui.detail_view import DetailView
from tapes.ui.help_overlay import HelpScreen
from tapes.ui.tree_model import (
    FileNode,
    FolderNode,
    TreeModel,
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
        Binding("x", "toggle_ignored", "Ignore"),
        Binding("c", "commit", "Commit"),
        Binding("a", "accept_best", "Accept"),
        Binding("r", "refresh_query", "Refresh"),
        Binding("grave_accent", "toggle_flat", "Flat/Tree"),
        Binding("slash", "start_search", "Search"),
        Binding("minus", "collapse_all", "Collapse All"),
        Binding("equals_sign", "expand_all", "Expand All"),
        Binding("question_mark", "toggle_help", "Help"),
        Binding("shift+tab", "cycle_op", "Cycle Op", show=False),
    ]

    CSS = """
    TreeView {
        height: 1fr;
        padding: 0 1;
    }
    TreeView.dimmed {
        color: #555555;
    }
    DetailView {
        display: none;
        padding: 0 1;
    }
    BottomBar {
        dock: bottom;
        height: 4;
    }
    """

    def __init__(
        self,
        model: TreeModel,
        movie_template: str,
        tv_template: str,
        root_path: Path | None = None,
        auto_pipeline: bool = False,
        *,
        config: TapesConfig | None = None,
    ) -> None:
        super().__init__()
        self.model = model
        self.movie_template = movie_template
        self.tv_template = tv_template
        self.root_path = root_path
        self.config = config or TapesConfig()
        self._in_detail = False
        self._auto_pipeline = auto_pipeline
        self._tmdb_querying = False
        self._tmdb_progress = (0, 0)
        self._searching = False
        self._search_query = ""

    def compose(self) -> ComposeResult:
        yield TreeView(
            self.model,
            self.movie_template,
            self.tv_template,
            root_path=self.root_path,
        )
        yield DetailView(
            FileNode(path=Path("placeholder")),
            self.movie_template,
            self.tv_template,
            root_path=self.root_path,
        )
        yield BottomBar(id="bottom-bar")

    def on_mount(self) -> None:
        # Use ANSI theme for true terminal background transparency.
        # Only set at mount time -- headless test runners lack a real
        # terminal so the default dark theme is safer there.
        try:
            self.theme = "textual-ansi"
        except Exception:
            pass

        self.query_one(BottomBar).operation = self.config.library.operation

        if self._auto_pipeline:
            from tapes.ui.pipeline import run_guessit_pass

            run_guessit_pass(self.model)
            self.query_one(TreeView).refresh_tree()
            self._update_footer()

            token = self.config.metadata.tmdb_token
            if token:
                self._tmdb_querying = True
                self._update_footer()
                self.run_worker(
                    self._run_tmdb_worker(token),
                    thread=True,
                )
        else:
            self._update_footer()

    def _run_tmdb_worker(self, token: str) -> object:
        """Return a callable that runs TMDB queries in a background thread."""
        from tapes.ui.pipeline import run_tmdb_pass

        threshold = self.config.metadata.auto_accept_threshold

        def worker() -> None:
            def on_progress(done: int, total: int) -> None:
                self.call_from_thread(self._on_tmdb_progress, done, total)

            run_tmdb_pass(
                self.model,
                token=token,
                confidence_threshold=threshold,
                on_progress=on_progress,
            )
            self.call_from_thread(self._on_tmdb_done)

        return worker

    def _show_detail(self, node: FileNode) -> None:
        """Switch from tree view to detail view for a file node."""
        self._in_detail = True
        detail = self.query_one(DetailView)
        detail.set_node(node)
        # separator + tab_bar + blank + path + blank + fields + blank + hints
        detail.styles.height = len(detail.fields) + 7
        detail.styles.display = "block"
        self.query_one(TreeView).add_class("dimmed")
        self.query_one(BottomBar).styles.display = "none"
        detail.focus()

    def _show_detail_multi(self, nodes: list[FileNode]) -> None:
        """Switch from tree view to detail view for multiple file nodes."""
        self._in_detail = True
        detail = self.query_one(DetailView)
        detail.set_nodes(nodes)
        detail.styles.height = len(detail.fields) + 7
        detail.styles.display = "block"
        self.query_one(TreeView).add_class("dimmed")
        self.query_one(BottomBar).styles.display = "none"
        detail.focus()

    def _show_tree(self) -> None:
        """Switch from detail view back to tree view."""
        self._in_detail = False
        detail = self.query_one(DetailView)
        detail.styles.display = "none"
        tv = self.query_one(TreeView)
        tv.remove_class("dimmed")
        self.query_one(BottomBar).styles.display = "block"
        tv.focus()
        tv.refresh()
        self._update_footer()

    def action_toggle_help(self) -> None:
        """Show the help screen."""
        self.push_screen(HelpScreen())

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
            self.query_one(DetailView).cycle_source(-1)

    def action_cursor_right(self) -> None:
        if self._in_detail:
            self.query_one(DetailView).cycle_source(1)

    def action_toggle_staged(self) -> None:
        if self._in_detail:
            return
        tv = self.query_one(TreeView)
        tv.toggle_staged_at_cursor()
        self._update_footer()

    def action_cycle_op(self) -> None:
        if self._in_detail:
            return
        self.query_one(BottomBar).cycle_operation()

    def _compute_file_pairs(
        self, staged: list[FileNode]
    ) -> list[tuple[Path, Path]]:
        """Compute (source, destination) pairs for staged files."""
        from tapes.ui.tree_render import compute_dest, select_template

        cfg = self.config
        pairs: list[tuple[Path, Path]] = []
        for node in staged:
            tmpl = select_template(
                node, self.movie_template, self.tv_template
            )
            # Choose library sub-root based on media_type
            media_type = node.result.get(MEDIA_TYPE)
            if media_type == MEDIA_TYPE_EPISODE and cfg.library.tv:
                library_root = Path(cfg.library.tv)
            elif cfg.library.movies:
                library_root = Path(cfg.library.movies)
            else:
                library_root = Path(".")
            dest_rel = compute_dest(node, tmpl)
            if dest_rel is not None:
                pairs.append((node.path, library_root / dest_rel))
        return pairs

    def action_toggle_or_enter(self) -> None:
        if self._in_detail:
            dv = self.query_one(DetailView)
            dv.start_edit()
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
        if self._in_detail:
            dv = self.query_one(DetailView)
            if dv.editing:
                dv.cancel_edit()
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
            self.notify("No staged files to commit")
            return
        count = tv.staged_count
        bar = self.query_one(BottomBar)
        self.push_screen(
            CommitScreen(count, bar.operation),
            callback=self._on_commit_result,
        )

    def _on_commit_result(self, result: tuple[bool, str]) -> None:
        """Handle commit screen dismissal."""
        confirmed, operation = result
        if confirmed:
            self._do_commit(operation)
        else:
            self._update_footer()

    def _do_commit(self, operation: str) -> None:
        """Execute the commit: process staged files and exit."""
        staged = [f for f in self.model.all_files() if f.staged]
        pairs = self._compute_file_pairs(staged)
        from tapes.file_ops import process_staged

        results = process_staged(
            pairs,
            operation,
            dry_run=self.config.dry_run,
        )
        self.exit(result=results)

    def action_refresh_query(self) -> None:
        from tapes.ui.pipeline import refresh_tmdb_source

        token = self.config.metadata.tmdb_token
        threshold = self.config.metadata.auto_accept_threshold

        if self._in_detail:
            dv = self.query_one(DetailView)
            for fn in dv.file_nodes:
                refresh_tmdb_source(fn, token=token, confidence_threshold=threshold)
            dv.refresh()
        else:
            tv = self.query_one(TreeView)
            if tv.in_range_mode:
                nodes = tv.selected_nodes()
                file_nodes = [n for n in nodes if isinstance(n, FileNode)]
                if file_nodes:
                    for fn in file_nodes:
                        refresh_tmdb_source(fn, token=token, confidence_threshold=threshold)
                tv.clear_range_select()
            else:
                node = tv.cursor_node()
                if isinstance(node, FileNode):
                    refresh_tmdb_source(node, token=token, confidence_threshold=threshold)
            tv.refresh()
        self._update_footer()

    def action_accept_best(self) -> None:
        if self._in_detail:
            self.query_one(DetailView).apply_source_field()
            return
        tv = self.query_one(TreeView)
        if tv.in_range_mode:
            nodes = tv.selected_nodes()
            file_nodes = [n for n in nodes if isinstance(n, FileNode)]
            if file_nodes:
                for fn in file_nodes:
                    accept_best_source(fn)
            tv.clear_range_select()
        else:
            node = tv.cursor_node()
            if isinstance(node, FileNode) and node.sources:
                accept_best_source(node)
        tv.refresh()
        self._update_footer()

    def action_start_search(self) -> None:
        if self._in_detail:
            return
        self._searching = True
        self._search_query = ""
        bar = self.query_one(BottomBar)
        bar.search_active = True
        bar.search_query = ""
        self._update_footer()

    def _update_search_status(self) -> None:
        """Update the bottom bar to show the search query."""
        self.query_one(BottomBar).search_query = self._search_query

    def _finish_search(self, keep_filter: bool) -> None:
        """Exit search mode. If keep_filter is False, clear the filter."""
        self._searching = False
        bar = self.query_one(BottomBar)
        bar.search_active = False
        if not keep_filter:
            self._search_query = ""
            bar.search_query = ""
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

    def action_collapse_all(self) -> None:
        if self._in_detail:
            return
        self.model.collapse_all()
        self.query_one(TreeView).refresh_tree()

    def action_expand_all(self) -> None:
        if self._in_detail:
            return
        self.model.expand_all()
        self.query_one(TreeView).refresh_tree()

    def action_toggle_flat(self) -> None:
        if self._in_detail:
            return
        self.query_one(TreeView).toggle_flat_mode()

    def _on_tmdb_progress(self, done: int, total: int) -> None:
        """Called from worker thread via call_from_thread after each file."""
        self._tmdb_progress = (done, total)
        if self._in_detail:
            self.query_one(DetailView).refresh()
        else:
            self.query_one(TreeView).refresh()
        self._update_footer()

    def _on_tmdb_done(self) -> None:
        """Called when all TMDB queries are complete."""
        self._tmdb_querying = False
        if self._in_detail:
            self.query_one(DetailView).refresh()
        else:
            self.query_one(TreeView).refresh()
        self._update_footer()

    def _update_footer(self) -> None:
        bar = self.query_one(BottomBar)
        tv = self.query_one(TreeView)

        # Stats
        if tv.filter_text:
            bar.stats_text = f"{tv.item_count} matched \u00b7 {tv.total_count} total"
        else:
            ignored = tv.ignored_count
            parts = [f"{tv.staged_count} staged"]
            if ignored:
                parts.append(f"{ignored} ignored")
            parts.append(f"{tv.total_count} total")
            if self._tmdb_querying:
                done, total = self._tmdb_progress
                parts.append(f"TMDB {done}/{total}")
            bar.stats_text = " \u00b7 ".join(parts)

        # Hints
        if self._searching:
            bar.hint_text = "Enter to confirm \u00b7 Esc to cancel"
        else:
            bar.hint_text = (
                "Space to stage \u00b7 Enter for details \u00b7 a to accept \u00b7 "
                "\u21e7Tab op \u00b7 c to commit \u00b7 ? for help"
            )
