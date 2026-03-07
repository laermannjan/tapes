"""Commit confirmation modal listing staged files with destinations."""
from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Center, Middle
from textual.widgets import Static

from tapes.ui.tree_render import MUTED, render_dest

if TYPE_CHECKING:
    pass


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


class CommitModal(Middle):
    """Centered modal overlay showing commit confirmation."""

    DEFAULT_CSS = """
    CommitModal {
        align: center middle;
    }
    CommitModal > Center {
        align: center middle;
        width: 100%;
        height: auto;
    }
    CommitModal #commit-panel {
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

    can_focus = True

    def __init__(
        self,
        staged_files: list[tuple[str, str | None]] | None = None,
        operation: str = "copy",
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._staged_files: list[tuple[str, str | None]] = staged_files or []
        self._operation = operation

    def compose(self) -> ComposeResult:
        with Center():
            yield Static(
                build_commit_text(self._staged_files, self._operation),
                id="commit-panel",
            )

    def update_content(
        self,
        staged_files: list[tuple[str, str | None]],
        operation: str,
    ) -> None:
        """Update the modal content and refresh."""
        self._staged_files = staged_files
        self._operation = operation
        self.query_one("#commit-panel", Static).update(
            build_commit_text(staged_files, operation)
        )
