"""Shift+E edit modal -- edit all metadata fields at once."""
from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static
from rich.text import Text

from tapes.ui.models import GridRow
from tapes.ui.render import FIELD_COLS


# Sentinel for "various" placeholder
_VARIOUS = "(various)"


class EditModal(ModalScreen[dict[str, Any] | None]):
    """Modal for editing all metadata fields of one or more rows."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("enter", "confirm", "Confirm", priority=True),
        Binding("tab", "next_field", "Next", show=False, priority=True),
        Binding("shift+tab", "prev_field", "Prev", show=False, priority=True),
        Binding("f", "toggle_freeze", "Freeze", show=False, priority=True),
    ]

    def __init__(self, rows: list[GridRow], **kwargs) -> None:
        super().__init__(**kwargs)
        self._rows = rows
        self._fields = list(FIELD_COLS)
        self._cursor = 0

        # Compute initial values and various flags
        self._values: dict[str, str] = {}
        self._various: dict[str, bool] = {}
        self._dirty: dict[str, bool] = {}
        self._frozen: dict[str, bool] = {}

        first = rows[0]
        for f in self._fields:
            val = str(getattr(first, f) or "")
            self._values[f] = val
            self._dirty[f] = False
            self._frozen[f] = first.is_frozen(f)

            # Check if values differ across rows
            is_various = False
            for r in rows[1:]:
                other_val = str(getattr(r, f) or "")
                if other_val != val:
                    is_various = True
                    break
            self._various[f] = is_various

    def compose(self) -> ComposeResult:
        yield Static(self._build_text(), id="edit-modal-body")

    def _build_text(self) -> Text:
        t = Text()
        t.append("Edit metadata\n\n", style="bold")

        for i, f in enumerate(self._fields):
            is_focused = i == self._cursor
            is_frozen = self._frozen[f]
            is_various = self._various[f] and not self._dirty[f]

            # Label
            label = f"{f}:".ljust(16)
            label_style = "#555555" if is_frozen else "#888888"
            t.append("  ")
            t.append(label, style=label_style)

            # Value
            if is_various:
                display = _VARIOUS
                val_style = "#666666 italic"
            elif is_frozen:
                display = self._values[f]
                val_style = "#555555"
            else:
                display = self._values[f]
                val_style = "#dddddd"

            if is_focused and not is_frozen:
                t.append(display, style="underline " + val_style)
                t.append("_", style="blink")
            else:
                t.append(display, style=val_style)

            if is_frozen:
                t.append("  [frozen]", style="#555555 italic")

            t.append("\n")

        t.append("\n")
        t.append("  tab", style="#888888")
        t.append("/", style="#555555")
        t.append("shift-tab", style="#888888")
        t.append(": navigate  ", style="#555555")
        t.append("f", style="#888888")
        t.append(": freeze  ", style="#555555")
        t.append("enter", style="#888888")
        t.append(": ok  ", style="#555555")
        t.append("esc", style="#888888")
        t.append(": cancel", style="#555555")

        return t

    def _refresh(self) -> None:
        body = self.query_one("#edit-modal-body", Static)
        body.update(self._build_text())

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_confirm(self) -> None:
        result: dict[str, Any] = {}
        for f in self._fields:
            if self._dirty[f]:
                result[f] = self._values[f]
        self.dismiss(result)

    def action_next_field(self) -> None:
        self._cursor = (self._cursor + 1) % len(self._fields)
        self._refresh()

    def action_prev_field(self) -> None:
        self._cursor = (self._cursor - 1) % len(self._fields)
        self._refresh()

    def action_toggle_freeze(self) -> None:
        f = self._fields[self._cursor]
        self._frozen[f] = not self._frozen[f]
        self._refresh()

    def on_key(self, event) -> None:
        f = self._fields[self._cursor]
        if self._frozen[f]:
            return

        if event.key == "backspace":
            event.prevent_default()
            event.stop()
            if self._various[f] and not self._dirty[f]:
                # First edit on various: clear to blank
                self._values[f] = ""
                self._dirty[f] = True
            elif self._values[f]:
                self._values[f] = self._values[f][:-1]
                self._dirty[f] = True
            self._refresh()
        elif event.character and event.is_printable:
            event.prevent_default()
            event.stop()
            if self._various[f] and not self._dirty[f]:
                # First edit on various: start from blank
                self._values[f] = event.character
            else:
                self._values[f] += event.character
            self._dirty[f] = True
            self._refresh()
