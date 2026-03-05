"""Textual TUI app for reviewing import groups."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Static, Footer, Header
from textual.containers import VerticalScroll

from tapes.models import ImportGroup, GroupStatus, FileEntry
from tapes.ui.split_modal import SplitModal
from tapes.ui.merge_modal import MergeModal
from tapes.ui.file_editor import FileEditorModal


# Status badge mapping
_STATUS_BADGES: dict[GroupStatus, tuple[str, str]] = {
    GroupStatus.PENDING: ("??", "yellow"),
    GroupStatus.ACCEPTED: ("ok", "green"),
    GroupStatus.AUTO_ACCEPTED: ("**", "blue"),
    GroupStatus.SKIPPED: ("--", "dim"),
}


class GroupWidget(Static):
    """Displays a single import group in collapsed or expanded form."""

    DEFAULT_CSS = """
    GroupWidget {
        padding: 0 1;
        margin: 0 0 0 0;
    }
    GroupWidget.expanded {
        background: $surface;
        padding: 0 1 1 1;
    }
    """

    def __init__(self, group: ImportGroup, expanded: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self.group = group
        self.expanded = expanded

    def on_mount(self) -> None:
        self._render_content()

    def _render_content(self) -> None:
        badge, style = _STATUS_BADGES.get(
            self.group.status, ("??", "yellow")
        )
        label = self.group.label

        if not self.expanded:
            self.remove_class("expanded")
            self.update(f"[{style}]\\[{badge}][/{style}]  {label}")
        else:
            self.add_class("expanded")
            lines: list[str] = []
            lines.append(f"[{style}]\\[{badge}][/{style}]  [bold]{label}[/bold]")

            # Metadata line
            meta = self.group.metadata
            meta_parts: list[str] = []
            if meta.media_type:
                meta_parts.append(meta.media_type)
            if meta.year is not None:
                meta_parts.append(str(meta.year))
            if meta.season is not None:
                meta_parts.append(f"S{meta.season:02d}")
            if meta.episode is not None:
                if isinstance(meta.episode, list):
                    eps = ", ".join(f"E{e:02d}" for e in meta.episode)
                    meta_parts.append(eps)
                else:
                    meta_parts.append(f"E{meta.episode:02d}")
            if meta_parts:
                lines.append(f"  {' | '.join(meta_parts)}")

            # File list
            lines.append("")
            for fe in self.group.files:
                role_tag = fe.role.ljust(8)
                lines.append(f"  [dim]{role_tag}[/dim]  {fe.path.name}")

            self.update("\n".join(lines))

    def set_expanded(self, expanded: bool) -> None:
        self.expanded = expanded
        self._render_content()


class SummaryWidget(Static):
    """Shows a summary line at the bottom."""

    def __init__(self, groups: list[ImportGroup], **kwargs) -> None:
        super().__init__(id="summary", **kwargs)
        self._groups = groups

    def on_mount(self) -> None:
        self._render_content()

    def _render_content(self) -> None:
        n_groups = len(self._groups)
        n_videos = sum(len(g.video_files) for g in self._groups)
        n_companions = sum(len(g.files) - len(g.video_files) for g in self._groups)
        self.update(
            f"Summary: {n_groups} group(s), {n_videos} video(s), {n_companions} companion(s)"
        )


class ReviewApp(App):
    """Vertical accordion TUI for reviewing import groups."""

    TITLE = "tapes"

    BINDINGS = [
        Binding("j", "focus_next_group", "Next", show=True),
        Binding("k", "focus_prev_group", "Prev", show=True),
        Binding("p", "open_split", "Split", show=True),
        Binding("m", "open_merge", "Merge", show=True),
        Binding("e", "open_file_editor", "Edit files", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(self, groups: list[ImportGroup], **kwargs) -> None:
        super().__init__(**kwargs)
        self._groups = list(groups)
        self._focused_index = 0
        self._group_widgets: list[GroupWidget] = []

    @property
    def focused_index(self) -> int:
        return self._focused_index

    def get_state(self) -> list[ImportGroup]:
        return list(self._groups)

    def get_history(self) -> list:
        return []

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            for i, group in enumerate(self._groups):
                widget = GroupWidget(group, expanded=(i == 0))
                self._group_widgets.append(widget)
                yield widget
        yield SummaryWidget(self._groups)
        yield Footer()

    def action_focus_next_group(self) -> None:
        if not self._group_widgets:
            return
        if self._focused_index < len(self._group_widgets) - 1:
            self._group_widgets[self._focused_index].set_expanded(False)
            self._focused_index += 1
            self._group_widgets[self._focused_index].set_expanded(True)

    def action_focus_prev_group(self) -> None:
        if not self._group_widgets:
            return
        if self._focused_index > 0:
            self._group_widgets[self._focused_index].set_expanded(False)
            self._focused_index -= 1
            self._group_widgets[self._focused_index].set_expanded(True)

    def _rebuild_widgets(self) -> None:
        """Clear and re-compose group widgets after structural changes."""
        # Remove empty groups
        self._groups = [g for g in self._groups if g.files]
        # Clamp focused index
        if self._focused_index >= len(self._groups):
            self._focused_index = max(0, len(self._groups) - 1)

        # Remove old widgets
        scroll = self.query_one(VerticalScroll)
        scroll.remove_children()
        self._group_widgets.clear()

        # Re-compose
        for i, group in enumerate(self._groups):
            widget = GroupWidget(group, expanded=(i == self._focused_index))
            self._group_widgets.append(widget)
            scroll.mount(widget)

        # Update summary
        summary = self.query_one("#summary", SummaryWidget)
        summary._groups = self._groups
        summary._render_content()

    def action_open_split(self) -> None:
        if not self._groups:
            return
        group = self._groups[self._focused_index]
        if len(group.files) < 2:
            return  # Need at least 2 files to split

        def on_split_result(result: ImportGroup | None) -> None:
            if result is None:
                return
            self._groups.append(result)
            self._rebuild_widgets()

        self.push_screen(SplitModal(group), callback=on_split_result)

    def action_open_merge(self) -> None:
        if len(self._groups) < 2:
            return
        focused = self._groups[self._focused_index]

        def on_merge_result(result: list[ImportGroup] | None) -> None:
            if result is None:
                return
            # Move all files from selected groups into focused group
            for source in result:
                for entry in list(source.files):
                    focused.add_file(entry)
            self._rebuild_widgets()

        self.push_screen(
            MergeModal(focused, self._groups), callback=on_merge_result
        )

    def action_open_file_editor(self) -> None:
        if not self._groups:
            return
        focused = self._groups[self._focused_index]

        def on_editor_result(result: list[FileEntry] | None) -> None:
            if result is None:
                return
            for entry in result:
                focused.add_file(entry)
            self._rebuild_widgets()

        self.push_screen(
            FileEditorModal(focused, self._groups), callback=on_editor_result
        )
