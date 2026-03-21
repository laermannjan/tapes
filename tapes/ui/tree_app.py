"""Textual App for the tree-based file browser."""

from __future__ import annotations

import copy
import threading
import time
from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, NamedTuple

if TYPE_CHECKING:
    from textual.timer import Timer

    from tapes.pipeline import PipelineParams

import structlog
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.events import Key

from tapes.categorize import categorize_staged
from tapes.config import TapesConfig
from tapes.fields import MEDIA_TYPE, MEDIA_TYPE_EPISODE, TMDB_ID
from tapes.templates import can_fill_template, compute_dest, select_template
from tapes.tree_model import (
    FileNode,
    FileStatus,
    FolderNode,
    TreeModel,
)
from tapes.ui.bottom_bar import BottomBar
from tapes.ui.commit_view import CommitView
from tapes.ui.help_view import HELP_HEIGHT, HelpView
from tapes.ui.metadata_view import MetadataView
from tapes.ui.tree_view import TreeView

logger = structlog.get_logger()

METADATA_CHROME_LINES = 9


def _format_bytes(n: int) -> str:
    """Format byte count for human display."""
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{n / (1024 * 1024 * 1024):.1f} GB"


class AppState(Enum):
    """Mutually exclusive UI states for the tree app."""

    TREE = "tree"
    METADATA = "metadata"
    COMMIT = "commit"
    HELP = "help"
    TREE_SEARCH = "tree_search"


_MODAL_STATES = frozenset({AppState.COMMIT, AppState.HELP})


class _NodeSnapshot(NamedTuple):
    node: FileNode
    metadata: dict
    candidates: list
    status: FileStatus


class TreeApp(App):
    """Interactive tree browser with cursor navigation."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("j,down", "cursor_down", "Down"),
        Binding("k,up", "cursor_up", "Up"),
        Binding("enter", "primary_action", "Stage/Enter"),
        Binding("space", "toggle_staged", "Stage"),
        Binding("v", "range_select", "Range Select"),
        Binding("escape", "cancel", "Cancel"),
        Binding("x", "toggle_rejected", "Reject"),
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
    MetadataView {
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
        self._mode = AppState.TREE
        self._mode_before_help = AppState.TREE
        self._metadata_snapshot: list[_NodeSnapshot] | None = None
        self._auto_pipeline = auto_pipeline
        self._tmdb_querying = False
        self._tmdb_progress = (0, 0)
        self._search_query = ""
        self._last_ctrl_c: float = 0.0
        self._commit_cancelled: threading.Event | None = None
        # Auto-commit state
        self._auto_commit_timer: Timer | None = None
        self._auto_commit_pending: bool = False
        # Polling state
        self._poll_timer: Timer | None = None
        self._tmdb_queue: list[FileNode] = []

    @property
    def state(self) -> AppState:
        """The current UI state."""
        return self._mode

    def compose(self) -> ComposeResult:
        yield TreeView(
            self.model,
            self.movie_template,
            self.tv_template,
            root_path=self.root_path,
        )
        yield MetadataView(
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
            logger.warning("theme_error")

        self.query_one(BottomBar).operation = self.config.library.operation

        if self._auto_pipeline:
            from tapes.pipeline import run_guessit_pass

            run_guessit_pass(self.model, root_path=self.root_path)
            self.query_one(TreeView).refresh_tree()
            self._update_footer()

            if self.config.metadata.tmdb_token:
                self._tmdb_querying = True
                self._update_footer()
                self.run_worker(
                    self._run_tmdb_worker(),  # ty: ignore[invalid-argument-type]  # Textual WorkType stubs
                    thread=True,
                )
            else:
                # No TMDB token - check if headless should exit (nothing to stage)
                self._check_headless_exit()
        else:
            self._update_footer()

        # Start directory polling if interval > 0
        if self.config.mode.poll_interval > 0:
            self._poll_timer = self.set_interval(
                self.config.mode.poll_interval,
                self._poll_directory,
            )

        # SIGTERM handler for graceful shutdown (Docker, systemd)
        if self.config.mode.headless:
            import signal

            def _handle_sigterm(_signum: int, _frame: object) -> None:
                logger.info("sigterm_received")
                self.exit()

            signal.signal(signal.SIGTERM, _handle_sigterm)

    def _make_pipeline_params(self) -> PipelineParams:
        """Build PipelineParams from current config."""
        from tapes.pipeline import PipelineParams

        return PipelineParams.from_config(self.config)

    def _make_can_stage(self) -> Callable[[FileNode, dict], bool]:
        """Build a can_stage callback from templates."""
        mt, tt = self.movie_template, self.tv_template

        def _can_stage(node: FileNode, merged: dict) -> bool:
            return can_fill_template(node, merged, mt, tt)

        return _can_stage

    def _post_update_with_auto_commit(self, fn: Callable[[], None]) -> None:
        """Wrap pipeline post_update to trigger auto-commit debounce.

        Dispatches *fn* to the main thread (via call_from_thread), then
        also schedules an auto-commit debounce reset.
        """

        def _combined() -> None:
            fn()
            self._schedule_auto_commit()

        self.call_from_thread(_combined)

    def _run_tmdb_worker(self) -> object:
        """Return a callable that runs TMDB queries in a background thread."""
        from tapes.pipeline import run_tmdb_pass

        params = self._make_pipeline_params()

        def worker() -> None:
            def on_progress(done: int, total: int) -> None:
                self.call_from_thread(self._on_tmdb_progress, done, total)

            run_tmdb_pass(
                self.model,
                params,
                on_progress=on_progress,
                post_update=self._post_update_with_auto_commit,
                can_stage=self._make_can_stage(),
            )
            self.call_from_thread(self._on_tmdb_done)

        return worker

    def _show_metadata_view(self, node: FileNode) -> None:
        """Switch from tree view to metadata view for a file node."""
        self._mode = AppState.METADATA
        self._metadata_snapshot = [
            _NodeSnapshot(node, copy.deepcopy(node.metadata), copy.deepcopy(node.candidates), node.status),
        ]
        mv = self.query_one(MetadataView)
        mv.set_node(node)
        mv.styles.height = len(mv.fields) + METADATA_CHROME_LINES
        mv.styles.display = "block"
        self.query_one(TreeView).add_class("dimmed")
        self.query_one(BottomBar).styles.display = "none"  # ty: ignore[invalid-assignment]  # Textual RenderStyles setter
        mv.focus()

    def _show_metadata_view_multi(self, nodes: list[FileNode]) -> None:
        """Switch from tree view to metadata view for multiple file nodes."""
        self._mode = AppState.METADATA
        self._metadata_snapshot = [
            _NodeSnapshot(n, copy.deepcopy(n.metadata), copy.deepcopy(n.candidates), n.status) for n in nodes
        ]
        mv = self.query_one(MetadataView)
        mv.set_nodes(nodes)
        mv.styles.height = len(mv.fields) + METADATA_CHROME_LINES
        mv.styles.display = "block"
        self.query_one(TreeView).add_class("dimmed")
        self.query_one(BottomBar).styles.display = "none"  # ty: ignore[invalid-assignment]  # Textual RenderStyles setter
        mv.focus()

    def _show_tree(self) -> None:
        """Switch from metadata view back to tree view."""
        self._mode = AppState.TREE
        mv = self.query_one(MetadataView)
        mv.styles.display = "none"  # ty: ignore[invalid-assignment]  # Textual RenderStyles setter
        tv = self.query_one(TreeView)
        tv.remove_class("dimmed")
        self.query_one(BottomBar).styles.display = "block"
        tv.focus()
        tv.refresh()
        self._update_footer()
        if self._auto_commit_pending:
            self._run_auto_commit()

    def _show_commit(self) -> None:
        """Show the commit confirmation view with conflict report."""
        from tapes.conflicts import detect_conflicts

        staged = [f for f in self.model.all_files() if f.staged]
        node_pairs = self._compute_file_pairs(staged)

        report = detect_conflicts(
            node_pairs,
            conflict_resolution=self.config.library.conflict_resolution,
        )

        self._mode = AppState.COMMIT
        bar = self.query_one(BottomBar)
        cv = self.query_one(CommitView)

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
        self._mode = AppState.TREE
        cv = self.query_one(CommitView)
        cv.styles.display = "none"  # ty: ignore[invalid-assignment]  # Textual RenderStyles setter
        tv = self.query_one(TreeView)
        tv.remove_class("dimmed")
        self.query_one(BottomBar).styles.display = "block"
        tv.focus()
        tv.refresh()
        self._update_footer()
        if self._auto_commit_pending:
            self._run_auto_commit()

    def _discard_metadata(self) -> None:
        """Discard metadata view changes and return to tree."""
        if self._metadata_snapshot:
            for node, metadata, candidates, status in self._metadata_snapshot:
                node.metadata = metadata
                node.candidates = candidates
                node.status = status
            self._metadata_snapshot = None
        self._show_tree()

    def action_toggle_help(self) -> None:
        """Toggle the inline help view."""
        if self._mode == AppState.HELP:
            self._hide_help()
        else:
            self._show_help()

    def _show_help(self) -> None:
        """Show the inline help view, remembering the previous mode."""
        self._mode_before_help = self._mode
        self._mode = AppState.HELP
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
        if prev == AppState.METADATA:
            self.query_one(MetadataView).focus()
        elif prev == AppState.COMMIT:
            self.query_one(CommitView).focus()
        else:
            tv = self.query_one(TreeView)
            tv.remove_class("dimmed")
            self.query_one(BottomBar).styles.display = "block"
            tv.focus()
            tv.refresh()
            self._update_footer()
            if self._auto_commit_pending:
                self._run_auto_commit()

    def action_cursor_down(self) -> None:
        if self._mode in _MODAL_STATES:
            return
        if self._mode == AppState.METADATA:
            self.query_one(MetadataView).move_cursor(row_delta=1)
        else:
            self.query_one(TreeView).move_cursor(1)

    def action_cursor_up(self) -> None:
        if self._mode in _MODAL_STATES:
            return
        if self._mode == AppState.METADATA:
            self.query_one(MetadataView).move_cursor(row_delta=-1)
        else:
            self.query_one(TreeView).move_cursor(-1)

    def action_toggle_staged(self) -> None:
        if self._mode != AppState.TREE:
            return
        tv = self.query_one(TreeView)
        if tv.in_range_mode:
            mt, tt = self.movie_template, self.tv_template
            nodes = tv.selected_nodes()
            file_nodes = [n for n in nodes if isinstance(n, FileNode)]
            if file_nodes:
                all_staged = all(f.staged for f in file_nodes)
                for f in file_nodes:
                    if all_staged:
                        f.status = FileStatus.PENDING
                    elif can_fill_template(f, f.metadata, mt, tt):
                        f.status = FileStatus.STAGED
            tv.clear_range_select()
            tv.refresh()
            self._update_footer()
            self._schedule_auto_commit()
            return
        node = tv.cursor_node()
        if isinstance(node, FileNode):
            self._toggle_staged_with_gate(node)
        elif isinstance(node, FolderNode):
            mt, tt = self.movie_template, self.tv_template
            self.model.toggle_staged_recursive(
                node,
                can_stage=lambda n: can_fill_template(n, n.metadata, mt, tt),
            )
            tv.refresh()
            self._update_footer()
            self._schedule_auto_commit()

    def _compute_file_pairs(self, staged: list[FileNode]) -> list[tuple[FileNode, Path]]:
        """Compute (node, destination) pairs for staged files."""
        cfg = self.config
        pairs: list[tuple[FileNode, Path]] = []
        for node in staged:
            tmpl = select_template(node, self.movie_template, self.tv_template)
            media_type = node.metadata.get(MEDIA_TYPE)
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
        if self._mode == AppState.COMMIT:
            cv = self.query_one(CommitView)
            self._do_commit(cv.operation)
            return
        if self._mode == AppState.METADATA:
            dv = self.query_one(MetadataView)
            if dv.editing:
                dv.apply_edit()
            else:
                self._accept_metadata_and_return()
            return
        if self._mode != AppState.TREE:
            return
        tv = self.query_one(TreeView)
        if tv.in_range_mode:
            nodes = tv.selected_nodes()
            file_nodes = [n for n in nodes if isinstance(n, FileNode)]
            if file_nodes:
                self._show_metadata_view_multi(file_nodes)
            tv.clear_range_select()
            return
        node = tv.cursor_node()
        if isinstance(node, FolderNode):
            from tapes.tree_model import collect_files

            files = collect_files(node)
            if files:
                self._show_metadata_view_multi(files)
        elif isinstance(node, FileNode):
            self._show_metadata_view(node)

    def _toggle_staged_with_gate(self, node: FileNode) -> None:
        """Toggle staging with the can_fill_template gate."""
        mt, tt = self.movie_template, self.tv_template

        def _can_stage(n: FileNode) -> bool:
            return can_fill_template(n, n.metadata, mt, tt)

        old = node.staged
        self.model.toggle_staged(node, can_stage=_can_stage)
        if not old and not node.staged:
            self.notify("Incomplete metadata -- cannot stage")
        self.query_one(TreeView).refresh()
        self._update_footer()
        if node.staged:
            self._schedule_auto_commit()

    def _accept_metadata_and_return(self) -> None:
        """Accept metadata view changes, auto-stage if possible, return to tree."""
        dv = self.query_one(MetadataView)
        # Capture nodes and whether fields will change BEFORE switching modes.
        # After _show_tree(), the MetadataChanged message would trigger
        # action_refresh_query in TREE mode, which only collects the cursor
        # node instead of all files from the metadata view.
        metadata_nodes = list(dv.file_nodes)
        needs_refresh = dv.focus_column == "candidate"

        dv.accept_focused_column()

        mt, tt = self.movie_template, self.tv_template
        any_staged = False
        if self._metadata_snapshot:
            for snap in self._metadata_snapshot:
                node = snap.node
                if node.pending and can_fill_template(node, node.metadata, mt, tt):
                    node.status = FileStatus.STAGED
                    any_staged = True
        self._metadata_snapshot = None
        if any_staged:
            self._schedule_auto_commit()
        self._show_tree()

        # Trigger TMDB refresh for all metadata nodes when fields changed.
        # This replaces the stale MetadataChanged -> action_refresh_query path
        # which would only refresh the cursor node after the mode switch.
        if needs_refresh and self.config.metadata.tmdb_token and metadata_nodes and not self._tmdb_querying:
            self._tmdb_querying = True
            self._update_footer()
            self.run_worker(
                self._run_refresh_worker(metadata_nodes),  # ty: ignore[invalid-argument-type]  # Textual WorkType stubs
                thread=True,
            )

    def action_range_select(self) -> None:
        if self._mode != AppState.TREE:
            return
        self.query_one(TreeView).start_range_select()

    def action_cancel(self) -> None:
        if self._mode == AppState.TREE_SEARCH:
            self._finish_search(keep_filter=False)
            return
        if self._mode == AppState.HELP:
            self._hide_help()
            return
        if self._mode == AppState.COMMIT:
            if self._commit_cancelled is not None:
                self._commit_cancelled.set()
                self.query_one(CommitView).progress_text = "cancelling ..."
            else:
                self._hide_commit()
            return
        if self._mode == AppState.METADATA:
            dv = self.query_one(MetadataView)
            if dv.editing:
                dv.cancel_edit()
            else:
                self._discard_metadata()
            return
        tv = self.query_one(TreeView)
        if tv.in_range_mode:
            tv.clear_range_select()

    def action_toggle_rejected(self) -> None:
        if self._mode != AppState.TREE:
            return
        tv = self.query_one(TreeView)
        tv.toggle_rejected_at_cursor()
        self._update_footer()

    def action_tab_forward(self) -> None:
        """Tab key: open commit preview from tree, cycle candidates in metadata view."""
        if self._mode == AppState.METADATA:
            dv = self.query_one(MetadataView)
            dv.cycle_candidate(1)
            dv.refresh()
            return
        if self._mode != AppState.TREE:
            return
        tv = self.query_one(TreeView)
        if tv.staged_count == 0:
            self.notify("No staged files to commit")
            return
        self._show_commit()

    def action_start_edit(self) -> None:
        """e key: start inline edit in metadata view."""
        if self._mode != AppState.METADATA:
            return
        self.query_one(MetadataView).start_edit()

    def _do_commit(self, operation: str) -> None:
        """Execute the commit: process staged files in a worker thread."""
        cv = self.query_one(CommitView)
        report = cv.conflict_report
        if report is None:
            return

        pairs = [(n.path, d) for n, d in report.valid_pairs]
        staged = [n for n, _ in report.valid_pairs]
        overwrite_dests = report.overwrite_dests

        if not pairs:
            self.notify("No files to process")
            return

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
            self._run_commit_worker(pairs, staged, operation, overwrite_dests),  # ty: ignore[invalid-argument-type]  # Textual WorkType stubs
            thread=True,
        )

    def _run_commit_worker(
        self,
        pairs: list[tuple[Path, Path]],
        staged: list[FileNode],
        operation: str,
        overwrite_dests: set[Path] | None = None,
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
                overwrite_dests=overwrite_dests,
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

        ok_srcs = {src for (src, _dest), msg in zip(pairs, results, strict=False) if not msg.startswith("Error")}
        processed = [n for n in staged if n.path in ok_srcs]
        errors = len(results) - len(ok_srcs)

        if processed:
            self.model.remove_nodes(processed)

        if self.config.library.delete_rejected:
            from tapes.file_ops import delete_files

            rejected = [f for f in self.model.all_files() if f.rejected]
            if rejected:
                delete_files([f.path for f in rejected], dry_run=self.config.dry_run)
                self.model.remove_nodes(rejected)

        self._hide_commit()
        self.query_one(CommitView).progress_text = ""
        self.query_one(TreeView).refresh_tree()
        self._update_footer()

        msg = f"{len(processed)} file(s) processed"
        if errors:
            msg += f", {errors} error(s)"
        logger.info("commit_done", processed=len(processed), errors=errors)
        if not self.config.mode.headless:
            self.notify(msg)

    def _on_commit_cancelled(self, done: int, total: int) -> None:
        """Handle commit cancellation -- return to tree view."""
        self._commit_cancelled = None
        self._hide_commit()
        self.query_one(CommitView).progress_text = ""
        self.notify(f"Cancelled ({done}/{total} files processed)")

    # ------------------------------------------------------------------
    # Auto-commit: debounce timer, pending flag, background processing
    # ------------------------------------------------------------------

    def _schedule_auto_commit(self) -> None:
        """Reset the auto-commit debounce timer after a staging event."""
        if not self.config.mode.auto_commit:
            return
        if self._auto_commit_timer is not None:
            self._auto_commit_timer.stop()
        self._auto_commit_timer = self.set_timer(
            self.config.mode.auto_commit_delay,
            self._auto_commit_fire,
        )

    def _auto_commit_fire(self) -> None:
        """Called when the debounce timer expires."""
        self._auto_commit_timer = None
        if self._mode != AppState.TREE:
            self._auto_commit_pending = True
            return
        self._run_auto_commit()

    def _run_auto_commit(self) -> None:
        """Collect staged files, run conflict detection, process in background."""
        from tapes.conflicts import detect_conflicts

        self._auto_commit_pending = False

        staged = [f for f in self.model.all_files() if f.staged]
        if not staged:
            self._check_headless_exit()
            return

        pairs = self._compute_file_pairs(staged)
        if not pairs:
            # Staged files have no computable destination - unstage them
            for f in staged:
                f.status = FileStatus.PENDING
            self._check_headless_exit()
            return

        report = detect_conflicts(
            pairs,
            conflict_resolution=self.config.library.conflict_resolution,
        )

        if not report.valid_pairs:
            if report.rejected_count > 0:
                self.notify(f"{report.rejected_count} file(s) rejected (conflicts)")
                self.query_one(TreeView).refresh()
                self._update_footer()
            self._check_headless_exit()
            return

        src_dest_pairs = [(n.path, dest) for n, dest in report.valid_pairs]
        valid_nodes = [n for n, _ in report.valid_pairs]
        batch_rejected = [n for p in report.problems for n in p.rejected_nodes]
        overwrite_dests = report.overwrite_dests

        self.run_worker(
            self._run_auto_commit_worker(src_dest_pairs, valid_nodes, batch_rejected, overwrite_dests),  # ty: ignore[invalid-argument-type]  # Textual WorkType stubs
            thread=True,
        )

    def _run_auto_commit_worker(
        self,
        pairs: list[tuple[Path, Path]],
        staged: list[FileNode],
        batch_rejected: list[FileNode],
        overwrite_dests: set[Path],
    ) -> object:
        """Background worker for auto-commit batch processing."""
        from tapes.file_ops import process_staged

        operation = self.config.library.operation
        dry_run = self.config.dry_run

        def worker() -> None:
            results = process_staged(
                pairs,
                operation,
                dry_run=dry_run,
                overwrite_dests=overwrite_dests,
            )
            self.call_from_thread(self._on_auto_commit_done, pairs, results, staged, batch_rejected)

        return worker

    def _on_auto_commit_done(
        self,
        pairs: list[tuple[Path, Path]],
        results: list[str],
        staged: list[FileNode],
        batch_rejected: list[FileNode],
    ) -> None:
        """Handle auto-commit batch completion."""
        ok_srcs = {src for (src, _), msg in zip(pairs, results, strict=False) if not msg.startswith("Error")}
        processed = [n for n in staged if n.path in ok_srcs]
        errored = [n for n in staged if n.path not in ok_srcs]
        errors = len(errored)

        # Unstage errored files so they don't block headless exit
        for n in errored:
            n.status = FileStatus.PENDING

        if processed:
            self.model.remove_nodes(processed)

        if self.config.library.delete_rejected and batch_rejected:
            from tapes.file_ops import delete_files

            delete_files([n.path for n in batch_rejected], dry_run=self.config.dry_run)
            self.model.remove_nodes(batch_rejected)

        self.query_one(TreeView).refresh_tree()
        self._update_footer()

        parts: list[str] = []
        parts.append(f"{len(processed)} file(s) processed")
        n_rejected = len(batch_rejected)
        if n_rejected:
            parts.append(f"{n_rejected} rejected")
        if errors:
            parts.append(f"{errors} error(s)")
        msg = "Auto-committed: " + ", ".join(parts)
        logger.info("auto_commit_done", processed=len(processed), rejected=n_rejected, errors=errors)
        if not self.config.mode.headless:
            self.notify(msg)

        self._check_headless_exit()

    def _check_headless_exit(self) -> None:
        """Exit the app if headless, one-shot, and all work is done."""
        if not self.config.mode.headless:
            return
        if self.config.mode.poll_interval > 0:
            return  # Persistent mode, never auto-exit

        # All-work-done condition
        if (
            not self._tmdb_querying
            and not self._tmdb_queue
            and self._auto_commit_timer is None
            and not self._auto_commit_pending
            and not any(f.staged for f in self.model.all_files())
        ):
            logger.info("headless_exit")
            self.exit()

    def action_refresh_query(self) -> None:
        if self._mode in _MODAL_STATES or self._mode == AppState.METADATA:
            return
        if self._tmdb_querying:
            return  # Already querying

        if not self.config.metadata.tmdb_token:
            return

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
            self._run_refresh_worker(nodes),  # ty: ignore[invalid-argument-type]  # Textual WorkType stubs
            thread=True,
        )

    def _run_refresh_worker(self, nodes: list[FileNode]) -> object:
        """Return a callable that refreshes TMDB data in a background thread."""
        from tapes.pipeline import refresh_tmdb_batch

        params = self._make_pipeline_params()

        def worker() -> None:
            def on_progress(done: int, total: int) -> None:
                self.call_from_thread(self._on_tmdb_progress, done, total)

            refresh_tmdb_batch(
                nodes,
                params,
                on_progress=on_progress,
                post_update=self.call_from_thread,
                can_stage=self._make_can_stage(),
            )
            self.call_from_thread(self._on_tmdb_done)

        return worker

    def action_clear_field(self) -> None:
        if self._mode != AppState.METADATA:
            return
        self.query_one(MetadataView).clear_field()

    def action_reset_guessit(self) -> None:
        if self._mode != AppState.METADATA:
            return
        self.query_one(MetadataView).reset_field_to_guessit()

    def action_start_search(self) -> None:
        if self._mode != AppState.TREE:
            return
        self._mode = AppState.TREE_SEARCH
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
        self._mode = AppState.TREE
        bar = self.query_one(BottomBar)
        bar.search_active = False
        if not keep_filter:
            self._search_query = ""
            bar.search_query = ""
            self.query_one(TreeView).clear_filter()
        self._update_footer()
        if self._auto_commit_pending:
            self._run_auto_commit()

    def on_key(self, event: Key) -> None:
        """Intercept key events for h/l navigation, ctrl+c quit, shift+tab, and search mode."""
        if self._mode == AppState.TREE and event.key in ("h", "left", "l", "right", "shift+left", "shift+right"):
            tv = self.query_one(TreeView)
            if event.key in ("h", "left"):
                node = tv.cursor_node()
                if isinstance(node, FolderNode) and not node.collapsed:
                    tv.toggle_folder_at_cursor()
                else:
                    tv.move_to_parent()
            elif event.key in ("l", "right"):
                node = tv.cursor_node()
                if isinstance(node, FolderNode) and node.collapsed:
                    tv.toggle_folder_at_cursor()
            elif event.key == "shift+left":
                tv.scroll_horizontal(-TreeView.H_SCROLL_STEP)
            elif event.key == "shift+right":
                tv.scroll_horizontal(TreeView.H_SCROLL_STEP)
            event.prevent_default()
            event.stop()
            return

        # Tab key: commit preview from tree, cycle candidates in metadata view
        # Must be intercepted here because Textual uses tab for focus cycling.
        if event.key == "tab" and self._mode != AppState.TREE_SEARCH:
            self.action_tab_forward()
            event.prevent_default()
            event.stop()
            return

        if event.key == "ctrl+c":
            now = time.monotonic()
            if now - self._last_ctrl_c < 1.0:
                self.exit()
            else:
                self._last_ctrl_c = now
                msg = "press ctrl+c again to exit"
                if self._mode == AppState.METADATA:
                    dv = self.query_one(MetadataView)
                    dv.quit_hint = msg
                    self.set_timer(1.0, self._clear_quit_hint)
                elif self._mode == AppState.COMMIT:
                    cv = self.query_one(CommitView)
                    cv.quit_hint = msg
                    self.set_timer(1.0, self._clear_quit_hint)
                else:
                    self.query_one(BottomBar).hint_text = msg
                    self.set_timer(1.0, self._update_footer)
            event.prevent_default()
            event.stop()
            return

        if event.key == "shift+tab" and self._mode != AppState.TREE_SEARCH:
            if self._mode == AppState.METADATA:
                self.query_one(MetadataView).toggle_column_focus()
            elif self._mode == AppState.COMMIT:
                self.query_one(CommitView).cycle_operation()
            else:
                self.query_one(BottomBar).cycle_operation()
            event.prevent_default()
            event.stop()
            return

        if self._mode != AppState.TREE_SEARCH:
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
            event.prevent_default()
            event.stop()

    def action_collapse_all(self) -> None:
        if self._mode != AppState.TREE:
            return
        self.model.collapse_all()
        self.query_one(TreeView).refresh_tree()

    def action_expand_all(self) -> None:
        if self._mode != AppState.TREE:
            return
        self.model.expand_all()
        self.query_one(TreeView).refresh_tree()

    def action_toggle_flat(self) -> None:
        if self._mode != AppState.TREE:
            return
        self.query_one(TreeView).toggle_flat_mode()

    def _on_tmdb_progress(self, done: int, total: int) -> None:
        """Called from worker thread via call_from_thread after each file."""
        self._tmdb_progress = (done, total)
        if self._mode == AppState.METADATA:
            self.query_one(MetadataView).refresh()
        else:
            self.query_one(TreeView).refresh()
        self._update_footer()

    def _on_tmdb_done(self) -> None:
        """Called when all TMDB queries are complete."""
        self._tmdb_querying = False
        if self._mode == AppState.METADATA:
            # B1: if a show/movie was auto-accepted (tmdb_id newly set)
            # while in metadata view, return to tree so the user sees
            # the result in the destination preview.
            mv = self.query_one(MetadataView)
            if self._metadata_snapshot and self._should_return_to_tree(mv):
                self._metadata_snapshot = None
                self._maybe_start_tmdb_worker()
                self._show_tree()
                return
            mv.refresh()
        else:
            self.query_one(TreeView).refresh()
        self._update_footer()
        self._maybe_start_tmdb_worker()
        # Trigger auto-commit for any staged files that were deferred
        self._schedule_auto_commit()
        self._check_headless_exit()

    def _should_return_to_tree(self, mv: MetadataView) -> bool:  # noqa: ARG002
        """Check if TMDB auto-accept set tmdb_id that wasn't in the snapshot."""
        if not self._metadata_snapshot:
            return False
        for snap in self._metadata_snapshot:
            old_tmdb_id = snap.metadata.get(TMDB_ID)
            new_tmdb_id = snap.node.metadata.get(TMDB_ID)
            if new_tmdb_id is not None and old_tmdb_id != new_tmdb_id:
                return True
        return False

    def on_metadata_view_metadata_changed(self, _event: MetadataView.MetadataChanged) -> None:
        """Auto-refresh TMDB when metadata view fields are edited."""
        if self._tmdb_querying:
            return
        token = self.config.metadata.tmdb_token
        if not token:
            return
        self.action_refresh_query()

    def _clear_quit_hint(self) -> None:
        """Clear the quit hint from metadata/commit view."""
        self.query_one(MetadataView).quit_hint = ""
        self.query_one(CommitView).quit_hint = ""

    def _update_footer(self) -> None:
        bar = self.query_one(BottomBar)
        tv = self.query_one(TreeView)

        if tv.filter_text:
            bar.stats_text = f"{tv.item_count} matched \u00b7 {tv.total_count} total"
        else:
            rejected = tv.rejected_count
            parts = [f"{tv.staged_count} staged"]
            if rejected:
                parts.append(f"{rejected} rejected")
            parts.append(f"{tv.total_count} total")
            if self._tmdb_querying:
                done, total = self._tmdb_progress
                parts.append(f"TMDB {done}/{total}")
            bar.stats_text = " \u00b7 ".join(parts)

        if self._mode == AppState.TREE_SEARCH:
            bar.hint_text = "enter to confirm \u00b7 esc to cancel"
        else:
            bar.hint_text = "enter to view \u00b7 space to stage \u00b7 tab to commit \u00b7 ? for help"

    # ------------------------------------------------------------------
    # Directory polling: re-scan, diff, rebuild tree, migrate state
    # ------------------------------------------------------------------

    def _poll_directory(self) -> None:
        """Re-scan the directory and update the tree with new/removed files."""
        from tapes.pipeline import run_guessit_pass
        from tapes.scanner import scan

        if self.root_path is None:
            return

        cfg = self.config
        scanned = scan(
            self.root_path,
            ignore_patterns=cfg.scan.ignore_patterns,
            video_extensions=cfg.scan.video_extensions,
        )
        scanned_set = set(scanned)
        known_paths = {f.path for f in self.model.all_files()}

        new_paths = scanned_set - known_paths
        removed_paths = known_paths - scanned_set

        if not new_paths and not removed_paths:
            return

        # Guard: protect files in active metadata snapshot from removal
        if self._metadata_snapshot:
            snapshot_paths = {snap.node.path for snap in self._metadata_snapshot}
            protected = removed_paths & snapshot_paths
            if protected:
                removed_paths -= protected
                scanned_set |= protected
                if not new_paths and not removed_paths:
                    return

        # Save state from current tree
        state_map: dict[Path, tuple[FileStatus, dict, list]] = {}
        for node in self.model.all_files():
            state_map[node.path] = (
                node.status,
                node.metadata.copy(),
                list(node.candidates),
            )

        # Save cursor position
        tv = self.query_one(TreeView)
        cursor_path: Path | None = None
        cursor_node = tv.cursor_node()
        if isinstance(cursor_node, FileNode):
            cursor_path = cursor_node.path

        # Rebuild tree
        from tapes.tree_model import build_tree

        new_model = build_tree(sorted(scanned_set), self.root_path)

        # Migrate state to new tree
        new_files: list[FileNode] = []
        for node in new_model.all_files():
            if node.path in state_map:
                status, metadata, candidates = state_map[node.path]
                node.status = status
                node.metadata = metadata
                node.candidates = candidates
            else:
                new_files.append(node)

        # Replace model root
        self.model.root = new_model.root
        self.model._cached_files = None  # noqa: SLF001

        # Run guessit on new files only
        if new_files:
            run_guessit_pass(self.model, root_path=self.root_path, nodes=new_files)

        # Queue new files for TMDB
        if new_files and cfg.metadata.tmdb_token:
            self._tmdb_queue.extend(new_files)
            self._maybe_start_tmdb_worker()

        # Refresh UI
        tv.refresh_tree()
        self._restore_cursor(tv, cursor_path)
        self._update_footer()

    def _restore_cursor(self, tv: TreeView, target_path: Path | None) -> None:
        """Restore cursor to the node at target_path, or clamp to valid range."""
        if target_path is None:
            return
        for i, (node, _depth) in enumerate(tv._items):  # noqa: SLF001
            if isinstance(node, FileNode) and node.path == target_path:
                tv.cursor_index = i
                return
        if tv._items:  # noqa: SLF001
            tv.cursor_index = min(tv.cursor_index, len(tv._items) - 1)  # noqa: SLF001
        else:
            tv.cursor_index = 0

    def _maybe_start_tmdb_worker(self) -> None:
        """Start a TMDB worker for queued new files if none is running."""
        if self._tmdb_querying or not self._tmdb_queue:
            return

        from tapes.pipeline import run_tmdb_pass

        # Drain the queue into a temporary model for the worker
        nodes = list(self._tmdb_queue)
        self._tmdb_queue.clear()

        self._tmdb_querying = True
        self._update_footer()

        params = self._make_pipeline_params()

        def worker() -> None:
            # Create a minimal model containing just the queued nodes
            temp_root = FolderNode(name="temp", children=nodes)
            temp_model = TreeModel(root=temp_root)

            def on_progress(done: int, total: int) -> None:
                self.call_from_thread(self._on_tmdb_progress, done, total)

            run_tmdb_pass(
                temp_model,
                params,
                on_progress=on_progress,
                post_update=self._post_update_with_auto_commit,
                can_stage=self._make_can_stage(),
            )
            self.call_from_thread(self._on_tmdb_done)

        self.run_worker(worker, thread=True)
