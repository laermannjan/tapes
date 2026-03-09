"""Textual App for the tree-based file browser."""

from __future__ import annotations

import copy
import logging
import threading
import time
from enum import Enum
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


def _format_bytes(n: int) -> str:
    """Format byte count for human display."""
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{n / (1024 * 1024 * 1024):.1f} GB"


class AppMode(Enum):
    """Mutually exclusive UI modes for the tree app."""

    TREE = "tree"
    DETAIL = "detail"
    COMMIT = "commit"
    HELP = "help"
    SEARCHING = "searching"


_MODAL_MODES = frozenset({AppMode.COMMIT, AppMode.HELP})


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
        Binding("enter", "primary_action", "Stage/Enter"),
        Binding("space", "toggle_staged", "Stage"),
        Binding("v", "range_select", "Range Select"),
        Binding("escape", "cancel", "Cancel"),
        Binding("x", "toggle_ignored", "Ignore"),
        Binding("e", "start_edit", "Edit", show=False),
        Binding("r", "refresh_query", "Refresh"),
        Binding("grave_accent", "toggle_flat", "Flat/Tree"),
        Binding("slash", "start_search", "Search"),
        Binding("minus", "collapse_all", "Collapse All"),
        Binding("equals_sign", "expand_all", "Expand All"),
        Binding("question_mark", "toggle_help", "Help"),
        Binding("backspace", "clear_field", "Clear Field", show=False),
        Binding("ctrl+r", "reset_guessit", "Reset to filename", show=False),
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
        self._mode = AppMode.TREE
        self._mode_before_help = AppMode.TREE
        self._detail_snapshot: list[_NodeSnapshot] | None = None
        self._auto_pipeline = auto_pipeline
        self._tmdb_querying = False
        self._tmdb_progress = (0, 0)
        self._search_query = ""
        self._last_ctrl_c: float = 0.0
        self._commit_cancelled: threading.Event | None = None

    @property
    def mode(self) -> AppMode:
        """The current UI mode."""
        return self._mode

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
        from tapes.ui.tree_render import can_fill_template

        threshold = self.config.metadata.auto_accept_threshold
        max_workers = self.config.advanced.max_workers
        max_results = self.config.metadata.max_results
        tmdb_timeout = self.config.advanced.tmdb_timeout
        tmdb_retries = self.config.advanced.tmdb_retries
        margin_threshold = self.config.metadata.margin_accept_threshold
        min_margin = self.config.metadata.min_accept_margin
        language = self.config.metadata.language
        mt, tt = self.movie_template, self.tv_template

        def _can_stage(node: FileNode, merged: dict) -> bool:
            return can_fill_template(node, merged, mt, tt)

        def worker() -> None:
            def on_progress(done: int, total: int) -> None:
                self.call_from_thread(self._on_tmdb_progress, done, total)

            run_tmdb_pass(
                self.model,
                token=token,
                confidence_threshold=threshold,
                on_progress=on_progress,
                max_workers=max_workers,
                post_update=self.call_from_thread,
                max_results=max_results,
                tmdb_timeout=tmdb_timeout,
                tmdb_retries=tmdb_retries,
                margin_threshold=margin_threshold,
                min_margin=min_margin,
                language=language,
                can_stage=_can_stage,
            )
            self.call_from_thread(self._on_tmdb_done)

        return worker

    def _show_detail(self, node: FileNode) -> None:
        """Switch from tree view to detail view for a file node."""
        self._mode = AppMode.DETAIL
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
        self._mode = AppMode.DETAIL
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
        self._mode = AppMode.TREE
        detail = self.query_one(DetailView)
        detail.styles.display = "none"  # ty: ignore[invalid-assignment]  # Textual RenderStyles setter
        tv = self.query_one(TreeView)
        tv.remove_class("dimmed")
        self.query_one(BottomBar).styles.display = "block"
        tv.focus()
        tv.refresh()
        self._update_footer()

    def _show_commit(self) -> None:
        """Show the commit confirmation view with conflict report."""
        from tapes.conflicts import detect_conflicts

        staged = [f for f in self.model.all_files() if f.staged]
        node_pairs = self._compute_file_pairs(staged)

        report = detect_conflicts(
            node_pairs,
            duplicate_resolution=self.config.metadata.duplicate_resolution,
            disambiguation=self.config.metadata.disambiguation,
        )

        self._mode = AppMode.COMMIT
        bar = self.query_one(BottomBar)
        cv = self.query_one(CommitView)

        # Recollect staged (conflict detection may have unstaged some)
        remaining_staged = [n for n, _ in report.valid_pairs]
        cv._files = remaining_staged  # noqa: SLF001
        cv._categories = categorize_staged(remaining_staged)  # noqa: SLF001
        cv.operation = bar.operation
        cv.movies_path = self.config.library.movies
        cv.tv_path = self.config.library.tv
        cv.conflict_report = report
        cv.styles.height = cv.computed_height
        cv.styles.display = "block"
        self.query_one(TreeView).add_class("dimmed")
        bar.styles.display = "none"  # ty: ignore[invalid-assignment]  # Textual RenderStyles setter
        cv.focus()

    def _hide_commit(self) -> None:
        """Hide the commit view and return to tree."""
        self._mode = AppMode.TREE
        cv = self.query_one(CommitView)
        cv.styles.display = "none"  # ty: ignore[invalid-assignment]  # Textual RenderStyles setter
        tv = self.query_one(TreeView)
        tv.remove_class("dimmed")
        self.query_one(BottomBar).styles.display = "block"
        tv.focus()
        tv.refresh()
        self._update_footer()

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
        if self._mode == AppMode.HELP:
            self._hide_help()
        else:
            self._show_help()

    def _show_help(self) -> None:
        """Show the inline help view, remembering the previous mode."""
        self._mode_before_help = self._mode
        self._mode = AppMode.HELP
        hv = self.query_one(HelpView)
        hv.styles.height = HELP_HEIGHT
        hv.styles.display = "block"
        self.query_one(TreeView).add_class("dimmed")
        self.query_one(BottomBar).styles.display = "none"  # ty: ignore[invalid-assignment]  # Textual RenderStyles setter
        hv.focus()

    def _hide_help(self) -> None:
        """Hide the help view and return to the previous mode."""
        prev = self._mode_before_help
        self._mode = prev
        hv = self.query_one(HelpView)
        hv.styles.display = "none"  # ty: ignore[invalid-assignment]  # Textual RenderStyles setter
        if prev == AppMode.DETAIL:
            self.query_one(DetailView).focus()
        elif prev == AppMode.COMMIT:
            self.query_one(CommitView).focus()
        else:
            tv = self.query_one(TreeView)
            tv.remove_class("dimmed")
            self.query_one(BottomBar).styles.display = "block"
            tv.focus()
            tv.refresh()
            self._update_footer()

    def action_cursor_down(self) -> None:
        if self._mode in _MODAL_MODES:
            return
        if self._mode == AppMode.DETAIL:
            self.query_one(DetailView).move_cursor(row_delta=1)
        else:
            self.query_one(TreeView).move_cursor(1)

    def action_cursor_up(self) -> None:
        if self._mode in _MODAL_MODES:
            return
        if self._mode == AppMode.DETAIL:
            self.query_one(DetailView).move_cursor(row_delta=-1)
        else:
            self.query_one(TreeView).move_cursor(-1)

    def action_toggle_staged(self) -> None:
        if self._mode != AppMode.TREE:
            return
        tv = self.query_one(TreeView)
        if tv.in_range_mode:
            from tapes.ui.tree_render import can_fill_template

            mt, tt = self.movie_template, self.tv_template
            nodes = tv.selected_nodes()
            file_nodes = [n for n in nodes if isinstance(n, FileNode)]
            if file_nodes:
                all_staged = all(f.staged for f in file_nodes)
                for f in file_nodes:
                    if all_staged:
                        f.staged = False
                    elif can_fill_template(f, f.result, mt, tt):
                        f.staged = True
            tv.clear_range_select()
            tv.refresh()
            self._update_footer()
            return
        node = tv.cursor_node()
        if isinstance(node, FileNode):
            self._toggle_staged_with_gate(node)
        elif isinstance(node, FolderNode):
            from tapes.ui.tree_render import can_fill_template

            mt, tt = self.movie_template, self.tv_template
            self.model.toggle_staged_recursive(
                node,
                can_stage=lambda n: can_fill_template(n, n.result, mt, tt),
            )
            tv.refresh()
            self._update_footer()

    def action_cycle_op(self) -> None:
        if self._mode != AppMode.TREE:
            return
        self.query_one(BottomBar).cycle_operation()

    def _compute_file_pairs(self, staged: list[FileNode]) -> list[tuple[FileNode, Path]]:
        """Compute (node, destination) pairs for staged files."""
        from tapes.ui.tree_render import compute_dest, select_template

        cfg = self.config
        pairs: list[tuple[FileNode, Path]] = []
        for node in staged:
            tmpl = select_template(node, self.movie_template, self.tv_template)
            media_type = node.result.get(MEDIA_TYPE)
            if media_type == MEDIA_TYPE_EPISODE and cfg.library.tv:
                library_root = Path(cfg.library.tv)
            elif cfg.library.movies:
                library_root = Path(cfg.library.movies)
            else:
                library_root = Path()
            dest_rel = compute_dest(node, tmpl)
            if dest_rel is not None:
                pairs.append((node, library_root / dest_rel))
        return pairs

    def action_primary_action(self) -> None:
        """Enter key: context-dependent primary action."""
        if self._mode == AppMode.COMMIT:
            cv = self.query_one(CommitView)
            self._do_commit(cv.operation)
            return
        if self._mode == AppMode.DETAIL:
            dv = self.query_one(DetailView)
            if dv.editing:
                dv.commit_edit()
            else:
                self._accept_detail_and_return()
            return
        if self._mode != AppMode.TREE:
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
            from tapes.tree_model import collect_files

            files = collect_files(node)
            if files:
                self._show_detail_multi(files)
        elif isinstance(node, FileNode):
            self._toggle_staged_with_gate(node)

    def _toggle_staged_with_gate(self, node: FileNode) -> None:
        """Toggle staging with the can_fill_template gate."""
        from tapes.ui.tree_render import can_fill_template

        mt, tt = self.movie_template, self.tv_template

        def _can_stage(n: FileNode) -> bool:
            return can_fill_template(n, n.result, mt, tt)

        old = node.staged
        self.model.toggle_staged(node, can_stage=_can_stage)
        if not old and not node.staged:
            self.notify("Incomplete metadata -- cannot stage")
        self.query_one(TreeView).refresh()
        self._update_footer()

    def _accept_detail_and_return(self) -> None:
        """Accept detail view changes, auto-stage if possible, return to tree."""
        from tapes.ui.tree_render import can_fill_template

        dv = self.query_one(DetailView)
        dv.accept_focused_column()

        mt, tt = self.movie_template, self.tv_template
        if self._detail_snapshot:
            for snap in self._detail_snapshot:
                node = snap.node
                if can_fill_template(node, node.result, mt, tt):
                    node.staged = True
        self._detail_snapshot = None
        self._show_tree()

    def action_range_select(self) -> None:
        if self._mode != AppMode.TREE:
            return
        self.query_one(TreeView).start_range_select()

    def action_cancel(self) -> None:
        if self._mode == AppMode.SEARCHING:
            self._finish_search(keep_filter=False)
            return
        if self._mode == AppMode.HELP:
            self._hide_help()
            return
        if self._mode == AppMode.COMMIT:
            if self._commit_cancelled is not None:
                # Processing in progress -- signal cancellation.
                self._commit_cancelled.set()
                self.query_one(CommitView).progress_text = "cancelling ..."
            else:
                self._hide_commit()
            return
        if self._mode == AppMode.DETAIL:
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
        if self._mode != AppMode.TREE:
            return
        tv = self.query_one(TreeView)
        tv.toggle_ignored_at_cursor()
        self._update_footer()

    def action_tab_forward(self) -> None:
        """Tab key: open commit preview from tree, cycle sources in detail."""
        if self._mode == AppMode.DETAIL:
            self.query_one(DetailView).cycle_source(1)
            return
        if self._mode != AppMode.TREE:
            return
        tv = self.query_one(TreeView)
        if tv.staged_count == 0:
            self.notify("No staged files to commit")
            return
        self._show_commit()

    def action_start_edit(self) -> None:
        """e key: start inline edit in detail view."""
        if self._mode != AppMode.DETAIL:
            return
        self.query_one(DetailView).start_edit()

    def _do_commit(self, operation: str) -> None:
        """Execute the commit: process staged files in a worker thread."""
        cv = self.query_one(CommitView)
        report = cv.conflict_report
        if report is None:
            return

        # Convert valid_pairs to (Path, Path) for file_ops
        pairs = [(n.path, d) for n, d in report.valid_pairs]
        staged = [n for n, _ in report.valid_pairs]

        if not pairs:
            self.notify("No files to process")
            return

        # Validate: reject files with no library path (relative destinations).
        bad = [src for src, dest in pairs if not dest.is_absolute()]
        if bad:
            self.notify(
                f"{len(bad)} file(s) have no library path configured",
                severity="error",
            )
            return

        self._commit_cancelled = threading.Event()
        cv.progress_text = f"0/{len(pairs)} files ..."
        cv.styles.height = cv.computed_height
        self.run_worker(
            self._run_commit_worker(pairs, staged, operation),  # ty: ignore[invalid-argument-type]  # Textual WorkType stubs
            thread=True,
        )

    def _run_commit_worker(
        self,
        pairs: list[tuple[Path, Path]],
        staged: list[FileNode],
        operation: str,
    ) -> object:
        """Return a callable that processes files in a background thread."""
        from tapes.file_ops import process_staged

        dry_run = self.config.dry_run
        cancel = self._commit_cancelled
        if cancel is None:  # pragma: no cover -- caller always sets this
            return lambda: None

        def worker() -> None:
            last_update = 0.0
            current_file = ""
            file_counter = ""

            def on_file_start(i: int, total: int, src: Path, dest: Path) -> None:
                nonlocal current_file, file_counter
                file_counter = f"{i + 1}/{total} files"
                current_file = f"{src.name} \u2192 {dest}"
                self.call_from_thread(
                    self._on_commit_progress,
                    f"{file_counter} ... {current_file}",
                )

            def on_file_progress(copied: int, total: int) -> None:
                nonlocal last_update
                now = time.monotonic()
                if now - last_update < 0.2:
                    return
                last_update = now
                self.call_from_thread(
                    self._on_commit_progress,
                    f"{file_counter} ... {current_file}  ({_format_bytes(copied)} / {_format_bytes(total)})",
                )

            results = process_staged(
                pairs,
                operation,
                dry_run=dry_run,
                on_file_start=on_file_start,
                on_file_progress=on_file_progress,
                cancelled=cancel.is_set,
            )

            if cancel.is_set():
                self.call_from_thread(self._on_commit_cancelled, len(results), len(pairs))
            else:
                self.call_from_thread(self._on_commit_done, pairs, results, staged)

        return worker

    def _on_commit_progress(self, text: str) -> None:
        """Update commit view progress from worker thread."""
        cv = self.query_one(CommitView)
        cv.progress_text = text
        cv.styles.height = cv.computed_height

    def _on_commit_done(
        self,
        pairs: list[tuple[Path, Path]],
        results: list[str],
        staged: list[FileNode],
    ) -> None:
        """Handle successful commit -- remove processed files and return to tree."""
        self._commit_cancelled = None

        # Identify successfully processed source paths.
        ok_srcs = {src for (src, _dest), msg in zip(pairs, results, strict=False) if not msg.startswith("Error")}
        processed = [n for n in staged if n.path in ok_srcs]
        errors = len(results) - len(ok_srcs)

        if processed:
            self.model.remove_nodes(processed)

        self._hide_commit()
        self.query_one(CommitView).progress_text = ""
        self.query_one(TreeView).refresh_tree()
        self._update_footer()

        msg = f"{len(processed)} file(s) processed"
        if errors:
            msg += f", {errors} error(s)"
        self.notify(msg)

    def _on_commit_cancelled(self, done: int, total: int) -> None:
        """Handle commit cancellation -- return to tree view."""
        self._commit_cancelled = None
        self._hide_commit()
        self.query_one(CommitView).progress_text = ""
        self.notify(f"Cancelled ({done}/{total} files processed)")

    def action_refresh_query(self) -> None:
        if self._mode in _MODAL_MODES:
            return
        if self._tmdb_querying:
            return  # Already querying

        token = self.config.metadata.tmdb_token
        if not token:
            return

        # Collect target nodes
        if self._mode == AppMode.DETAIL:
            nodes = list(self.query_one(DetailView).file_nodes)
        else:
            tv = self.query_one(TreeView)
            if tv.in_range_mode:
                selected = tv.selected_nodes()
                nodes = [n for n in selected if isinstance(n, FileNode)]
                tv.clear_range_select()
            else:
                node = tv.cursor_node()
                nodes = [node] if isinstance(node, FileNode) else []

        if not nodes:
            return

        self._tmdb_querying = True
        self._update_footer()
        self.run_worker(
            self._run_refresh_worker(nodes, token),  # ty: ignore[invalid-argument-type]  # Textual WorkType stubs
            thread=True,
        )

    def _run_refresh_worker(self, nodes: list[FileNode], token: str) -> object:
        """Return a callable that refreshes TMDB data in a background thread."""
        from tapes.pipeline import refresh_tmdb_batch
        from tapes.ui.tree_render import can_fill_template

        threshold = self.config.metadata.auto_accept_threshold
        max_workers = self.config.advanced.max_workers
        max_results = self.config.metadata.max_results
        tmdb_timeout = self.config.advanced.tmdb_timeout
        tmdb_retries = self.config.advanced.tmdb_retries
        margin_threshold = self.config.metadata.margin_accept_threshold
        min_margin = self.config.metadata.min_accept_margin
        language = self.config.metadata.language
        mt, tt = self.movie_template, self.tv_template

        def _can_stage(node: FileNode, merged: dict) -> bool:
            return can_fill_template(node, merged, mt, tt)

        def worker() -> None:
            def on_progress(done: int, total: int) -> None:
                self.call_from_thread(self._on_tmdb_progress, done, total)

            refresh_tmdb_batch(
                nodes,
                token=token,
                confidence_threshold=threshold,
                on_progress=on_progress,
                max_workers=max_workers,
                post_update=self.call_from_thread,
                max_results=max_results,
                tmdb_timeout=tmdb_timeout,
                max_retries=tmdb_retries,
                margin_threshold=margin_threshold,
                min_margin=min_margin,
                language=language,
                can_stage=_can_stage,
            )
            self.call_from_thread(self._on_tmdb_done)

        return worker

    def action_clear_field(self) -> None:
        if self._mode != AppMode.DETAIL:
            return
        self.query_one(DetailView).clear_field()

    def action_reset_guessit(self) -> None:
        if self._mode != AppMode.DETAIL:
            return
        self.query_one(DetailView).reset_field_to_guessit()

    def action_start_search(self) -> None:
        if self._mode != AppMode.TREE:
            return
        self._mode = AppMode.SEARCHING
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
        self._mode = AppMode.TREE
        bar = self.query_one(BottomBar)
        bar.search_active = False
        if not keep_filter:
            self._search_query = ""
            bar.search_query = ""
            self.query_one(TreeView).clear_filter()
        self._update_footer()

    def on_key(self, event: Key) -> None:
        """Intercept key events for h/l navigation, ctrl+c quit, shift+tab, and search mode."""
        # h/left = collapse, l/right = expand in tree mode
        if self._mode == AppMode.TREE and event.key in ("h", "left"):
            tv = self.query_one(TreeView)
            node = tv.cursor_node()
            if isinstance(node, FolderNode) and not node.collapsed:
                tv.toggle_folder_at_cursor()
            else:
                tv.move_to_parent()
            event.prevent_default()
            event.stop()
            return
        if self._mode == AppMode.TREE and event.key in ("l", "right"):
            tv = self.query_one(TreeView)
            node = tv.cursor_node()
            if isinstance(node, FolderNode) and node.collapsed:
                tv.toggle_folder_at_cursor()
            event.prevent_default()
            event.stop()
            return

        # Tab key: commit preview from tree, cycle sources in detail
        # Must be intercepted here because Textual uses tab for focus cycling.
        if event.key == "tab" and self._mode != AppMode.SEARCHING:
            self.action_tab_forward()
            event.prevent_default()
            event.stop()
            return

        # Double ctrl+c to quit
        if event.key == "ctrl+c":
            now = time.monotonic()
            if now - self._last_ctrl_c < 1.0:
                self.exit()
            else:
                self._last_ctrl_c = now
                msg = "press ctrl+c again to exit"
                if self._mode == AppMode.DETAIL:
                    dv = self.query_one(DetailView)
                    dv.quit_hint = msg
                    self.set_timer(1.0, self._clear_quit_hint)
                elif self._mode == AppMode.COMMIT:
                    cv = self.query_one(CommitView)
                    cv.quit_hint = msg
                    self.set_timer(1.0, self._clear_quit_hint)
                else:
                    self.query_one(BottomBar).hint_text = msg
                    self.set_timer(1.0, self._update_footer)
            event.prevent_default()
            event.stop()
            return

        # Intercept shift+tab for op cycling / detail column toggle
        if event.key == "shift+tab" and self._mode != AppMode.SEARCHING:
            if self._mode == AppMode.DETAIL:
                self.query_one(DetailView).toggle_column_focus()
            elif self._mode == AppMode.COMMIT:
                self.query_one(CommitView).cycle_operation()
            else:
                self.query_one(BottomBar).cycle_operation()
            event.prevent_default()
            event.stop()
            return

        if self._mode != AppMode.SEARCHING:
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
        if self._mode != AppMode.TREE:
            return
        self.model.collapse_all()
        self.query_one(TreeView).refresh_tree()

    def action_expand_all(self) -> None:
        if self._mode != AppMode.TREE:
            return
        self.model.expand_all()
        self.query_one(TreeView).refresh_tree()

    def action_toggle_flat(self) -> None:
        if self._mode != AppMode.TREE:
            return
        self.query_one(TreeView).toggle_flat_mode()

    def _on_tmdb_progress(self, done: int, total: int) -> None:
        """Called from worker thread via call_from_thread after each file."""
        self._tmdb_progress = (done, total)
        if self._mode == AppMode.DETAIL:
            self.query_one(DetailView).refresh()
        else:
            self.query_one(TreeView).refresh()
        self._update_footer()

    def _on_tmdb_done(self) -> None:
        """Called when all TMDB queries are complete."""
        self._tmdb_querying = False
        if self._mode == AppMode.DETAIL:
            self.query_one(DetailView).refresh()
        else:
            self.query_one(TreeView).refresh()
        self._update_footer()

    def on_detail_view_fields_changed(self, _event: DetailView.FieldsChanged) -> None:
        """Auto-refresh TMDB when detail view fields are edited."""
        if self._tmdb_querying:
            return
        token = self.config.metadata.tmdb_token
        if not token:
            return
        self.action_refresh_query()

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
        if self._mode == AppMode.SEARCHING:
            bar.hint_text = "enter to confirm \u00b7 esc to cancel"
        else:
            bar.hint_text = "enter/space to stage \u00b7 tab to commit \u00b7 ? for help"
