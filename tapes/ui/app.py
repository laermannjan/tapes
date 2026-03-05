"""Textual TUI app for reviewing import groups."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Static, Footer, Header
from textual.containers import VerticalScroll
from rich.text import Text

from tapes.models import ImportGroup, GroupStatus, FileEntry
from tapes.ui.split_modal import SplitModal
from tapes.ui.merge_modal import MergeModal
from tapes.ui.file_editor import FileEditorModal


_STATUS_BADGES: dict[GroupStatus, tuple[str, str]] = {
    GroupStatus.PENDING: ("??", "yellow"),
    GroupStatus.ACCEPTED: ("ok", "green"),
    GroupStatus.AUTO_ACCEPTED: ("**", "blue"),
    GroupStatus.SKIPPED: ("--", "dim"),
}


def _render_collapsed(group: ImportGroup) -> Text:
    badge, style = _STATUS_BADGES.get(group.status, ("??", "yellow"))
    line = Text()
    line.append(f"[{badge}]", style=style)
    line.append("  ")
    line.append(group.label, style="bold")
    n_files = len(group.files)
    n_videos = len(group.video_files)
    n_comp = n_files - n_videos
    info = f"  {n_videos} video"
    if n_videos != 1:
        info += "s"
    if n_comp:
        info += f", {n_comp} companion"
        if n_comp != 1:
            info += "s"
    line.append(info, style="dim")
    return line


def _render_expanded(group: ImportGroup) -> Text:
    badge, style = _STATUS_BADGES.get(group.status, ("??", "yellow"))
    out = Text()
    out.append(f"[{badge}]", style=style)
    out.append("  ")
    out.append(group.label, style="bold")

    # Metadata summary
    meta = group.metadata
    parts: list[str] = []
    if meta.media_type:
        parts.append(meta.media_type)
    if meta.year is not None:
        parts.append(str(meta.year))
    if meta.season is not None:
        parts.append(f"S{meta.season:02d}")
    if parts:
        out.append("  ")
        out.append(" | ".join(parts), style="dim")

    out.append("\n")

    # File listing
    for fe in group.files:
        out.append("\n")
        role = (fe.role or "").ljust(8)
        if fe.role == "video":
            out.append(f"  {role}  ", style="dim")
            out.append(fe.path.name)
        else:
            out.append(f"  {role}  ", style="dim")
            out.append(fe.path.name, style="dim")

    return out


class GroupWidget(Static):
    """Displays a single import group in collapsed or expanded form."""

    DEFAULT_CSS = """
    GroupWidget {
        padding: 0 1;
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
        if self.expanded:
            self.add_class("expanded")
            self.update(_render_expanded(self.group))
        else:
            self.remove_class("expanded")
            self.update(_render_collapsed(self.group))

    def set_expanded(self, expanded: bool) -> None:
        self.expanded = expanded
        self._render_content()


class SummaryWidget(Static):
    """Shows a summary line at the bottom."""

    DEFAULT_CSS = """
    SummaryWidget {
        dock: bottom;
        height: 1;
        padding: 0 1;
        background: $surface;
    }
    """

    def __init__(self, groups: list[ImportGroup], **kwargs) -> None:
        super().__init__(id="summary", **kwargs)
        self._groups = groups

    def on_mount(self) -> None:
        self._render_content()

    def _render_content(self) -> None:
        n_groups = len(self._groups)
        n_videos = sum(len(g.video_files) for g in self._groups)
        n_companions = sum(len(g.files) - len(g.video_files) for g in self._groups)
        text = Text()
        text.append(f" {n_groups}", style="bold")
        text.append(" groups  ", style="dim")
        text.append(f"{n_videos}", style="bold")
        text.append(" videos", style="dim")
        if n_companions:
            text.append(f"  {n_companions}", style="bold")
            text.append(" companions", style="dim")
        self.update(text)


class ReviewApp(App):
    """Vertical accordion TUI for reviewing import groups."""

    TITLE = "tapes"

    BINDINGS = [
        Binding("down", "focus_next_group", "Next", show=True),
        Binding("up", "focus_prev_group", "Prev", show=True),
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
            self._group_widgets[self._focused_index].scroll_visible()

    def action_focus_prev_group(self) -> None:
        if not self._group_widgets:
            return
        if self._focused_index > 0:
            self._group_widgets[self._focused_index].set_expanded(False)
            self._focused_index -= 1
            self._group_widgets[self._focused_index].set_expanded(True)
            self._group_widgets[self._focused_index].scroll_visible()

    def _rebuild_widgets(self) -> None:
        """Clear and re-compose group widgets after structural changes."""
        self._groups = [g for g in self._groups if g.files]
        if self._focused_index >= len(self._groups):
            self._focused_index = max(0, len(self._groups) - 1)

        scroll = self.query_one(VerticalScroll)
        scroll.remove_children()
        self._group_widgets.clear()

        for i, group in enumerate(self._groups):
            widget = GroupWidget(group, expanded=(i == self._focused_index))
            self._group_widgets.append(widget)
            scroll.mount(widget)

        summary = self.query_one("#summary", SummaryWidget)
        summary._groups = self._groups
        summary._render_content()

    def action_open_split(self) -> None:
        if not self._groups:
            return
        group = self._groups[self._focused_index]
        if len(group.files) < 2:
            return

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
