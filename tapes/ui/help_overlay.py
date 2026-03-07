"""Help overlay showing keybinding reference."""
from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Center, Middle
from textual.widgets import Static

from tapes.ui.tree_render import MUTED

if TYPE_CHECKING:
    pass


def _build_help_text() -> Text:
    """Build the help content as a Rich Text object (no manual borders)."""

    def key_row(key: str, action: str) -> Text:
        t = Text()
        t.append(f"  {key:<14}", "#7AB8FF")
        t.append(action)
        return t

    result = Text()

    # Files section
    result.append("  Files\n", "bold")

    file_keys = [
        ("j / k", "Move cursor"),
        ("enter", "Open detail / toggle folder"),
        ("space", "Toggle staged"),
        ("a", "Accept best TMDB source"),
        ("x", "Toggle ignored"),
        ("v", "Range select"),
        ("c", "Commit staged files"),
        ("u", "Undo"),
        ("/", "Search / filter"),
        ("`", "Toggle flat/tree mode"),
        ("- / =", "Collapse / expand all"),
        ("r", "Refresh TMDB query"),
        ("q", "Quit"),
    ]
    for key, action in file_keys:
        result.append_text(key_row(key, action))
        result.append("\n")

    result.append("\n")

    # Detail section
    result.append("  Detail\n", "bold")

    detail_keys = [
        ("j / k", "Move between fields"),
        ("h / l", "Previous / next TMDB source"),
        ("enter", "Apply field from current source"),
        ("\u21e7 enter", "Apply all fields from source"),
        ("e", "Edit result field inline"),
        ("d", "Clear result field"),
        ("D", "Reset field to filename value"),
        ("r", "Re-query TMDB"),
        ("u", "Undo"),
        ("esc", "Back to tree"),
    ]
    for key, action in detail_keys:
        result.append_text(key_row(key, action))
        result.append("\n")

    result.append("\n")

    # Concepts
    result.append("  Concepts\n", "bold")
    result.append(f"  {'staged':<14}file will be processed on commit\n")
    result.append(f"  {'unstaged':<14}needs review, check destination\n")
    result.append(f"  {'ignored':<14}skipped entirely\n")

    result.append("\n")
    result.append("  Sources provide metadata from TMDB.\n", MUTED)
    result.append("  Apply values to the result to build the destination path.\n", MUTED)

    result.append("\n")
    result.append("  Press ? or esc to close\n", f"{MUTED} italic")

    return result


class HelpOverlay(Middle):
    """Centered modal overlay showing keybinding reference."""

    DEFAULT_CSS = """
    HelpOverlay {
        align: center middle;
    }
    HelpOverlay > Center {
        align: center middle;
        width: 100%;
        height: auto;
    }
    HelpOverlay #help-panel {
        width: 64;
        height: auto;
        max-height: 90%;
        border: round #7AB8FF;
        padding: 1 2;
        background: #1a1a2e;
    }
    """

    can_focus = True

    def compose(self) -> ComposeResult:
        with Center():
            yield Static(_build_help_text(), id="help-panel")
