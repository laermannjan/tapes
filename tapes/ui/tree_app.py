"""Textual App for the tree-based file browser."""

from __future__ import annotations

import copy
import logging
import time
from pathlib import Path
from typing import ClassVar, NamedTuple

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.events import Key

from tapes.categorize import categorize_staged
from tapes.config import TapesConfig
from tapes.fields import MEDIA_TYPE, MEDIA_TYPE_EPISODE
from tapes.tree_model import (
    FileNode,
    FolderNode,
    TreeModel,
)
from tapes.ui.bottom_bar import BottomBar
from tapes.ui.commit_view import CommitView
from tapes.ui.detail_view import DetailView
from tapes.ui.help_overlay import HELP_HEIGHT, HelpView
from tapes.ui.tree_view import TreeView

logger = logging.getLogger(__name__)

DETAIL_CHROME_LINES = 9


class _NodeSnapshot(NamedTuple):
    node: FileNode
    result: dict
    sources: list
    staged: bool


class TreeApp(App):
    """Interactive tree browser with cursor navigation."""

    BINDINGS: ClassVar[list[Binding]] = [
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
        Binding("r", "refresh_query", "Refresh"),
        Binding("grave_accent", "toggle_flat", "Flat/Tree"),
        Binding("slash", "start_search", "Search"),
        Binding("minus", "collapse_all", "Collapse All"),
        Binding("equals_sign", "expand_all", "Expand All"),
        Binding("question_mark", "toggle_help", "Help"),
        Binding("backspace", "clear_field", "Clear Field", show=False),
        Binding("f", "reset_guessit", "Extract from filename", show=False),
    ]

    CSS = """
    TreeView {
        height: 1fr;
        padding: 0 1;
    }
    TreeView.dimmed {
        opacity: 1.0;
    }
    DetailView {
        display: none;
    }
    CommitView {
        display: none;
    }
    HelpView {
        display: none;
    }
    BottomBar {
        dock: bottom;
        height: 5;
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
        self._detail_snapshot: list[_NodeSnapshot] | None = None
        self._auto_pipeline = auto_pipeline
        self._tmdb_querying = False
        self._tmdb_progress = (0, 0)
        self._searching = False
        self._in_commit = False
        self._in_help = False
        self._search_query = ""
        self._last_ctrl_c: float = 0.0

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
        yield CommitView([], "copy", widget_id="commit-view")
        yield HelpView(id="help-view")
        yield BottomBar(id="bottom-bar")

    def on_mount(self) -> None:
        # Use ANSI theme for true terminal background transparency.
        # Only set at mount time -- headless test runners lack a real
        # terminal so the default dark theme is safer there.
        try:
            self.theme = "textual-ansi"
        except Exception:  # noqa: BLE001
            logger.warning("Could not set textual-ansi theme, using default")

        self.query_one(BottomBar).operation = self.config.library.operation

        if self._auto_pipeline:
            from tapes.pipeline import run_guessit_pass

            run_guessit_pass(self.model)
            self.query_one(TreeView).refresh_tree()
            self._update_footer()

            token = self.config.metadata.tmdb_token
            if token:
                self._tmdb_querying = True
                self._update_footer()
                self.run_worker(
                    self._run_tmdb_worker(token),  # ty: ignore[invalid-argument-type]  # Textual WorkType stubs
                    thread=True,
                )
        else:
            self._update_footer()

    def _run_tmdb_worker(self, token: str) -> object:
        """Return a callable that runs TMDB queries in a background thread."""
        from tapes.pipeline import run_tmdb_pass

        threshold = self.config.metadata.auto_accept_threshold

        def worker() -> None:
            def on_progress(done: int, total: int) -> None:
                self.call_from_thread(self._on_tmdb_progress, done, total)

            run_tmdb_pass(
                self.model,
                token=token,
                confidence_threshold=threshold,
                on_progress=on_progress,
                post_update=self.call_from_thread,
            )
            self.call_from_thread(self._on_tmdb_done)

        return worker

    def _show_detail(self, node: FileNode) -> None:
        """Switch from tree view to detail view for a file node."""
        self._in_detail = True
        self._detail_snapshot = [
            _NodeSnapshot(node, copy.deepcopy(node.result), copy.deepcopy(node.sources), node.staged),
        ]
        detail = self.query_one(DetailView)
        detail.set_node(node)
        # separator + tab_bar + blank + path + blank + fields + blank + hints
        detail.styles.height = len(detail.fields) + DETAIL_CHROME_LINES
        detail.styles.display = "block"
        self.query_one(TreeView).add_class("dimmed")
        self.query_one(BottomBar).styles.display = "none"  # ty: ignore[invalid-assignment]  # Textual RenderStyles setter
        detail.focus()

    def _show_detail_multi(self, nodes: list[FileNode]) -> None:
        """Switch from tree view to detail view for multiple file nodes."""
        self._in_detail = True
        self._detail_snapshot = [
            _NodeSnapshot(n, copy.deepcopy(n.result), copy.deepcopy(n.sources), n.staged) for n in nodes
        ]
        detail = self.query_one(DetailView)
        detail.set_nodes(nodes)
        detail.styles.height = len(detail.fields) + DETAIL_CHROME_LINES
        detail.styles.display = "block"
        self.query_one(TreeView).add_class("dimmed")
        self.query_one(BottomBar).styles.display = "none"  # ty: ignore[invalid-assignment]  # Textual RenderStyles setter
        detail.focus()

    def _show_tree(self) -> None:
        """Switch from detail view back to tree view."""
        self._in_detail = False
        detail = self.query_one(DetailView)
        detail.styles.display = "none"  # ty: ignore[invalid-assignment]  # Textual RenderStyles setter
        tv = self.query_one(TreeView)
        tv.remove_class("dimmed")
        self.query_one(BottomBar).styles.display = "block"
        tv.focus()
        tv.refresh()
        self._update_footer()

    def _show_commit(self) -> None:
        """Show the commit confirmation view."""
        self._in_commit = True
        staged = [f for f in self.model.all_files() if f.staged]
        bar = self.query_one(BottomBar)
        cv = self.query_one(CommitView)
        cv._files = staged  # noqa: SLF001
        cv._categories = categorize_staged(staged)  # noqa: SLF001
        cv.operation = bar.operation
        cv.styles.height = cv.computed_height
        cv.styles.display = "block"
        self.query_one(TreeView).add_class("dimmed")
        bar.styles.display = "none"  # ty: ignore[invalid-assignment]  # Textual RenderStyles setter
        cv.focus()

    def _hide_commit(self) -> None:
        """Hide the commit view and return to tree."""
        self._in_commit = False
        cv = self.query_one(CommitView)
        cv.styles.display = "none"  # ty: ignore[invalid-assignment]  # Textual RenderStyles setter
        tv = self.query_one(TreeView)
        tv.remove_class("dimmed")
        self.query_one(BottomBar).styles.display = "block"
        tv.focus()
        tv.refresh()
        self._update_footer()

    def _confirm_detail(self) -> None:
        """Confirm detail view changes and return to tree."""
        self._detail_snapshot = None
        self._show_tree()

    def _discard_detail(self) -> None:
        """Discard detail view changes and return to tree."""
        if self._detail_snapshot:
            for node, result, sources, staged in self._detail_snapshot:
                node.result = result
                node.sources = sources
                node.staged = staged
            self._detail_snapshot = None
        self._show_tree()

    def action_toggle_help(self) -> None:
        """Toggle the inline help view."""
        if self._in_help:
            self._hide_help()
        else:
            self._show_help()

    def _show_help(self) -> None:
        """Show the inline help view."""
        self._in_help = True
        hv = self.query_one(HelpView)
        hv.styles.height = HELP_HEIGHT
        hv.styles.display = "block"
        self.query_one(TreeView).add_class("dimmed")
        self.query_one(BottomBar).styles.display = "none"  # ty: ignore[invalid-assignment]  # Textual RenderStyles setter
        hv.focus()

    def _hide_help(self) -> None:
        """Hide the help view and return to tree."""
        self._in_help = False
        hv = self.query_one(HelpView)
        hv.styles.display = "none"  # ty: ignore[invalid-assignment]  # Textual RenderStyles setter
        tv = self.query_one(TreeView)
        tv.remove_class("dimmed")
        self.query_one(BottomBar).styles.display = "block"
        tv.focus()
        tv.refresh()
        self._update_footer()

    def action_cursor_down(self) -> None:
        if self._in_commit or self._in_help:
            return
        if self._in_detail:
            self.query_one(DetailView).move_cursor(row_delta=1)
        else:
            self.query_one(TreeView).move_cursor(1)

    def action_cursor_up(self) -> None:
        if self._in_commit or self._in_help:
            return
        if self._in_detail:
            self.query_one(DetailView).move_cursor(row_delta=-1)
        else:
            self.query_one(TreeView).move_cursor(-1)

    def action_cursor_left(self) -> None:
        if self._in_commit or self._in_help:
            return
        if self._in_detail:
            self.query_one(DetailView).cycle_source(-1)

    def action_cursor_right(self) -> None:
        if self._in_commit or self._in_help:
            return
        if self._in_detail:
            self.query_one(DetailView).cycle_source(1)

    def action_toggle_staged(self) -> None:
        if self._in_commit or self._in_help:
            return
        if self._in_detail:
            return
        tv = self.query_one(TreeView)
        tv.toggle_staged_at_cursor()
        self._update_footer()

    def action_cycle_op(self) -> None:
        if self._in_commit or self._in_help:
            return
        if self._in_detail:
            return
        self.query_one(BottomBar).cycle_operation()

    def _compute_file_pairs(self, staged: list[FileNode]) -> list[tuple[Path, Path]]:
        """Compute (source, destination) pairs for staged files."""
        from tapes.ui.tree_render import compute_dest, select_template

        cfg = self.config
        pairs: list[tuple[Path, Path]] = []
        for node in staged:
            tmpl = select_template(node, self.movie_template, self.tv_template)
            # Choose library sub-root based on media_type
            media_type = node.result.get(MEDIA_TYPE)
            if media_type == MEDIA_TYPE_EPISODE and cfg.library.tv:
                library_root = Path(cfg.library.tv)
            elif cfg.library.movies:
                library_root = Path(cfg.library.movies)
            else:
                library_root = Path()
            dest_rel = compute_dest(node, tmpl)
            if dest_rel is not None:
                pairs.append((node.path, library_root / dest_rel))
        return pairs

    def action_toggle_or_enter(self) -> None:
        if self._in_commit:
            cv = self.query_one(CommitView)
            self._hide_commit()
            self._do_commit(cv.operation)
            return
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
        if self._in_commit or self._in_help:
            return
        if self._in_detail:
            self.query_one(DetailView).apply_source_all_clear()

    def action_range_select(self) -> None:
        if self._in_commit or self._in_help:
            return
        if self._in_detail:
            return
        self.query_one(TreeView).start_range_select()

    def action_cancel(self) -> None:
        if self._searching:
            self._finish_search(keep_filter=False)
            return
        if self._in_help:
            self._hide_help()
            return
        if self._in_commit:
            self._hide_commit()
            return
        if self._in_detail:
            dv = self.query_one(DetailView)
            if dv.editing:
                dv.cancel_edit()
            else:
                self._discard_detail()
            return
        tv = self.query_one(TreeView)
        if tv.in_range_mode:
            tv.clear_range_select()

    def action_toggle_ignored(self) -> None:
        if self._in_commit or self._in_help:
            return
        if self._in_detail:
            return
        tv = self.query_one(TreeView)
        tv.toggle_ignored_at_cursor()
        self._update_footer()

    def action_commit(self) -> None:
        if self._in_detail:
            self._confirm_detail()
            return
        if self._in_commit:
            cv = self.query_one(CommitView)
            self._hide_commit()
            self._do_commit(cv.operation)
            return
        tv = self.query_one(TreeView)
        if tv.staged_count == 0:
            self.notify("No staged files to commit")
            return
        self._show_commit()

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
        if self._in_commit or self._in_help:
            return
        from tapes.pipeline import refresh_tmdb_source

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

    def action_clear_field(self) -> None:
        if self._in_commit or self._in_help:
            return
        if not self._in_detail:
            return
        self.query_one(DetailView).clear_field()

    def action_reset_guessit(self) -> None:
        if self._in_commit or self._in_help:
            return
        if not self._in_detail:
            return
        self.query_one(DetailView).reset_field_to_guessit()

    def action_start_search(self) -> None:
        if self._in_commit or self._in_help:
            return
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
        """Intercept key events for ctrl+c quit, shift+tab, and search mode."""
        # Double ctrl+c to quit
        if event.key == "ctrl+c":
            now = time.monotonic()
            if now - self._last_ctrl_c < 1.0:
                self.exit()
            else:
                self._last_ctrl_c = now
                msg = "press ctrl+c again to exit"
                if self._in_detail:
                    dv = self.query_one(DetailView)
                    dv.quit_hint = msg
                    self.set_timer(1.0, self._clear_quit_hint)
                elif self._in_commit:
                    cv = self.query_one(CommitView)
                    cv.quit_hint = msg
                    self.set_timer(1.0, self._clear_quit_hint)
                else:
                    self.query_one(BottomBar).hint_text = msg
                    self.set_timer(1.0, self._update_footer)
            event.prevent_default()
            event.stop()
            return

        # Intercept shift+tab for op cycling (Textual captures it for focus)
        if event.key == "shift+tab" and not self._in_detail and not self._searching:
            if self._in_commit:
                self.query_one(CommitView).cycle_operation()
            else:
                self.query_one(BottomBar).cycle_operation()
            event.prevent_default()
            event.stop()
            return

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
        if self._in_commit or self._in_help:
            return
        if self._in_detail:
            return
        self.model.collapse_all()
        self.query_one(TreeView).refresh_tree()

    def action_expand_all(self) -> None:
        if self._in_commit or self._in_help:
            return
        if self._in_detail:
            return
        self.model.expand_all()
        self.query_one(TreeView).refresh_tree()

    def action_toggle_flat(self) -> None:
        if self._in_commit or self._in_help:
            return
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

    def _clear_quit_hint(self) -> None:
        """Clear the quit hint from detail/commit view."""
        self.query_one(DetailView).quit_hint = ""
        self.query_one(CommitView).quit_hint = ""

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
            bar.hint_text = "enter to confirm \u00b7 esc to cancel"
        else:
            bar.hint_text = "space to stage \u00b7 enter to expand \u00b7 c to commit \u00b7 ? for help"
