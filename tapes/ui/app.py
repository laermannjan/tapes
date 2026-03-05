"""Textual TUI app for reviewing import groups."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Static
from textual.containers import VerticalScroll

from tapes.models import ImportGroup, GroupStatus


# Status badge mapping
_STATUS_BADGES: dict[GroupStatus, tuple[str, str]] = {
    GroupStatus.PENDING: ("[??]", "yellow"),
    GroupStatus.ACCEPTED: ("[ok]", "green"),
    GroupStatus.AUTO_ACCEPTED: ("[**]", "blue"),
    GroupStatus.SKIPPED: ("[--]", "dim"),
}


class GroupWidget(Static):
    """Displays a single import group in collapsed or expanded form."""

    def __init__(self, group: ImportGroup, expanded: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self.group = group
        self.expanded = expanded

    def on_mount(self) -> None:
        self._render_content()

    def _render_content(self) -> None:
        badge, style = _STATUS_BADGES.get(
            self.group.status, ("[??]", "yellow")
        )
        label = self.group.label

        if not self.expanded:
            self.update(f"[{style}]{badge}[/{style}]  {label}")
        else:
            lines: list[str] = []
            lines.append(f"[{style}]{badge}[/{style}]  [bold]{label}[/bold]")

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
            for fe in self.group.files:
                role_tag = f"[{fe.role}]" if fe.role else ""
                lines.append(f"    {role_tag} {fe.path.name}")

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

    BINDINGS = [
        Binding("ctrl+down", "focus_next_group", "Next group", show=True),
        Binding("ctrl+up", "focus_prev_group", "Previous group", show=True),
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
        with VerticalScroll():
            for i, group in enumerate(self._groups):
                widget = GroupWidget(group, expanded=(i == 0))
                self._group_widgets.append(widget)
                yield widget
        yield SummaryWidget(self._groups)

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
