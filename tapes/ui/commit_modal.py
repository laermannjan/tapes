"""Commit confirmation screen listing staged files with destinations."""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static

from tapes.ui.tree_render import MUTED, render_dest


def build_commit_text(
    staged_files: list[tuple[str, str | None]],
    operation: str,
) -> Text:
    """Build the commit modal content as a Rich Text object.

    Parameters
    ----------
    staged_files:
        List of (filename, destination) pairs. Destination may be None
        if the template could not be fully resolved.
    operation:
        The file operation type: "copy", "move", or "link".
    """
    op_label = operation.capitalize()
    count = len(staged_files)
    noun = "file" if count == 1 else "files"

    result = Text()

    result.append(f"  {op_label} {count} {noun} to library?\n\n")

    for filename, dest in staged_files:
        # File line: checkmark + filename
        result.append("  ")
        result.append("\u2713", style="#86E89A")
        result.append(f" {filename}\n")

        # Destination line
        result.append("    ")
        result.append("\u2192 ", style=MUTED)
        if dest is not None:
            result.append_text(render_dest(dest))
        else:
            result.append("???", style=MUTED)
        result.append("\n")

    result.append("\n")

    # Footer with keybinding hints
    result.append("  ")
    result.append("y", style="#7AB8FF")
    result.append(" confirm    ")
    result.append("n", style="#7AB8FF")
    result.append(" cancel\n")

    return result


class CommitScreen(ModalScreen[bool]):
    """Modal screen showing commit confirmation. Dismisses with True/False."""

    DEFAULT_CSS = """
    CommitScreen {
        align: center middle;
    }
    CommitScreen #commit-panel {
        width: 80%;
        max-width: 100;
        min-width: 50;
        height: auto;
        max-height: 80%;
        border: round #7AB8FF;
        padding: 1 2;
        background: #1a1a2e;
    }
    """

    BINDINGS = [
        Binding("y", "confirm", "Confirm", show=False),
        Binding("n", "cancel", "Cancel", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(
        self,
        staged_files: list[tuple[str, str | None]],
        operation: str,
    ) -> None:
        super().__init__()
        self._staged_files = staged_files
        self._operation = operation

    def compose(self) -> ComposeResult:
        yield Static(
            build_commit_text(self._staged_files, self._operation),
            id="commit-panel",
        )

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)
