"""File editor modal -- move files between groups."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from tapes.models import FileEntry, ImportGroup


class FileEditorModal(ModalScreen[list[FileEntry] | None]):
    """Modal showing all files across all groups.

    Selected files are moved to the focused group on confirm.
    """

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
        self._all_groups = all_groups
        # Build a flat list of (group, entry) for files NOT in the focused group
        self._items: list[tuple[ImportGroup, FileEntry]] = []
        for group in all_groups:
            if group is focused_group:
                continue
            for entry in group.files:
                self._items.append((group, entry))
        self._selected: set[int] = set()

    def compose(self) -> ComposeResult:
        yield Static(
            f"[bold]Move files to: {self._focused.label}[/bold]\n"
            "Space: toggle | Enter: confirm | Escape: cancel",
            id="editor-header",
        )
        with VerticalScroll():
            for i, (group, entry) in enumerate(self._items):
                yield Static(self._render_item(i), id=f"editor-item-{i}")

    def _render_item(self, index: int) -> str:
        marker = "[x]" if index in self._selected else "[ ]"
        group, entry = self._items[index]
        return f"  {marker} [{group.label}] {entry.path.name}"

    def _refresh_items(self) -> None:
        for i in range(len(self._items)):
            widget = self.query_one(f"#editor-item-{i}", Static)
            widget.update(self._render_item(i))

    def action_toggle(self) -> None:
        if not hasattr(self, "_cursor"):
            self._cursor = 0
        if not self._items:
            return
        if self._cursor in self._selected:
            self._selected.discard(self._cursor)
        else:
            self._selected.add(self._cursor)
        self._refresh_items()
        self._cursor = (self._cursor + 1) % len(self._items)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_confirm(self) -> None:
        if not self._selected:
            self.dismiss(None)
            return

        entries = [self._items[i][1] for i in sorted(self._selected)]
        self.dismiss(entries)
