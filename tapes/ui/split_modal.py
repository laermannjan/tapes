"""Split modal -- select files to split into a new group."""

from __future__ import annotations

import copy
from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Static

from tapes.models import FileEntry, ImportGroup


class SplitModal(ModalScreen[ImportGroup | None]):
    """Modal for splitting files out of a group into a new one."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Confirm"),
        Binding("space", "toggle", "Toggle"),
    ]

    def __init__(self, group: ImportGroup, **kwargs) -> None:
        super().__init__(**kwargs)
        self._group = group
        self._entries = list(group.files)
        self._selected: set[int] = set()

    def compose(self) -> ComposeResult:
        yield Static("[bold]Split group -- select files for new group[/bold]\n"
                      "Space: toggle | Enter: confirm | Escape: cancel",
                      id="split-header")
        with VerticalScroll():
            for i, entry in enumerate(self._entries):
                yield Static(self._render_item(i), id=f"split-item-{i}")

    def _render_item(self, index: int) -> str:
        marker = "[x]" if index in self._selected else "[ ]"
        return f"  {marker} {self._entries[index].path.name}"

    def _refresh_items(self) -> None:
        for i in range(len(self._entries)):
            widget = self.query_one(f"#split-item-{i}", Static)
            widget.update(self._render_item(i))

    def action_toggle(self) -> None:
        # Toggle the item under cursor. For simplicity, cycle through items
        # using a simple index tracker.
        if not hasattr(self, "_cursor"):
            self._cursor = 0
        if self._cursor in self._selected:
            self._selected.discard(self._cursor)
        else:
            self._selected.add(self._cursor)
        self._refresh_items()
        # Advance cursor
        self._cursor = (self._cursor + 1) % len(self._entries)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_confirm(self) -> None:
        if not self._selected or len(self._selected) == len(self._entries):
            # Can't split nothing or everything
            self.dismiss(None)
            return

        # Create new group with copied metadata
        new_meta = copy.deepcopy(self._group.metadata)
        new_group = ImportGroup(
            metadata=new_meta,
            group_type=self._group.group_type,
        )

        # Move selected files to new group (add_file auto-removes from old)
        for i in sorted(self._selected):
            new_group.add_file(self._entries[i])

        self.dismiss(new_group)
