"""Commit confirmation screen with operation selection."""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static

from tapes.ui.tree_render import MUTED

OPERATIONS = ["copy", "move", "link", "hardlink"]


def build_commit_text(count: int, operation: str) -> Text:
    """Build the commit modal content as a Rich Text object.

    Parameters
    ----------
    count:
        Number of staged files.
    operation:
        The currently selected file operation.
    """
    noun = "file" if count == 1 else "files"
    result = Text()

    result.append(f"\n  Process {count} {noun}?\n\n")

    result.append("  Operation: ")
    result.append(f"[{operation}]", style="bold")
    result.append("     ")
    result.append("\u2190/\u2192 to change", style=f"italic {MUTED}")
    result.append("\n\n")

    # Footer with keybinding hints
    result.append(
        "  y to confirm \u00b7 n to cancel",
        style=f"italic {MUTED}",
    )
    result.append("\n")

    return result


class CommitScreen(ModalScreen[tuple[bool, str]]):
    """Modal screen for commit confirmation with operation selection.

    Dismisses with (confirmed, operation) tuple.
    """

    DEFAULT_CSS = """
    CommitScreen {
        align: center middle;
    }
    CommitScreen #commit-panel {
        width: auto;
        min-width: 40;
        max-width: 60;
        height: auto;
        max-height: 80%;
        border: round #7AB8FF;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("y", "confirm", "Confirm", show=False),
        Binding("n", "cancel", "Cancel", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("h,left", "prev_op", "Prev Op", show=False),
        Binding("l,right", "next_op", "Next Op", show=False),
    ]

    def __init__(
        self,
        count: int,
        operation: str,
    ) -> None:
        super().__init__()
        self._count = count
        self._operation = operation
        if self._operation not in OPERATIONS:
            self._operation = OPERATIONS[0]

    def compose(self) -> ComposeResult:
        yield Static(
            build_commit_text(self._count, self._operation),
            id="commit-panel",
        )

    def _update_display(self) -> None:
        """Refresh the static content after operation change."""
        panel = self.query_one("#commit-panel", Static)
        panel.update(build_commit_text(self._count, self._operation))

    def action_next_op(self) -> None:
        idx = OPERATIONS.index(self._operation)
        self._operation = OPERATIONS[(idx + 1) % len(OPERATIONS)]
        self._update_display()

    def action_prev_op(self) -> None:
        idx = OPERATIONS.index(self._operation)
        self._operation = OPERATIONS[(idx - 1) % len(OPERATIONS)]
        self._update_display()

    def action_confirm(self) -> None:
        self.dismiss((True, self._operation))

    def action_cancel(self) -> None:
        self.dismiss((False, self._operation))
