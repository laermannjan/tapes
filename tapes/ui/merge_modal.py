"""Merge modal -- select other groups to merge into the focused group."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from tapes.models import ImportGroup


class MergeModal(ModalScreen[list[ImportGroup] | None]):
    """Modal for merging other groups into the focused group."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Confirm"),
        Binding("space", "toggle", "Toggle"),
    ]

    def __init__(
        self,
        focused_group: ImportGroup,
        all_groups: list[ImportGroup],
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._focused = focused_group
        self._others = [g for g in all_groups if g is not focused_group]
        self._selected: set[int] = set()

    def compose(self) -> ComposeResult:
        yield Static(
            f"[bold]Merge into: {self._focused.label}[/bold]\n"
            "Space: toggle | Enter: confirm | Escape: cancel",
            id="merge-header",
        )
        with VerticalScroll():
            for i, group in enumerate(self._others):
                yield Static(self._render_item(i), id=f"merge-item-{i}")

    def _render_item(self, index: int) -> str:
        marker = "[x]" if index in self._selected else "[ ]"
        group = self._others[index]
        n_files = len(group.files)
        return f"  {marker} {group.label}  ({n_files} file(s))"

    def _refresh_items(self) -> None:
        for i in range(len(self._others)):
            widget = self.query_one(f"#merge-item-{i}", Static)
            widget.update(self._render_item(i))

    def action_toggle(self) -> None:
        if not hasattr(self, "_cursor"):
            self._cursor = 0
        if self._cursor in self._selected:
            self._selected.discard(self._cursor)
        else:
            self._selected.add(self._cursor)
        self._refresh_items()
        self._cursor = (self._cursor + 1) % max(len(self._others), 1)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_confirm(self) -> None:
        if not self._selected:
            self.dismiss(None)
            return

        selected_groups = [self._others[i] for i in sorted(self._selected)]
        self.dismiss(selected_groups)
