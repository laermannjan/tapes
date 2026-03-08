"""Help screen showing keybinding reference."""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static

from tapes.ui.tree_render import MUTED


def _build_help_text() -> Text:
    """Build the help content as a Rich Text object."""

    def key_row(key: str, action: str) -> Text:
        t = Text()
        t.append(f"  {key:<16}", "#7AB8FF")
        t.append(action)
        return t

    result = Text()

    result.append("  Files\n", "bold")

    file_keys = [
        ("j / k", "move cursor"),
        ("enter", "open detail / toggle folder"),
        ("space", "toggle staged"),
        ("a", "accept best TMDB match"),
        ("x", "toggle ignored"),
        ("v", "range select"),
        ("c", "commit staged files"),
        ("/", "search / filter"),
        ("`", "toggle flat/tree mode"),
        ("- / =", "collapse / expand all"),
        ("r", "refresh TMDB query"),
        ("shift-tab", "cycle operation mode"),
        ("q", "quit"),
    ]
    for key, action in file_keys:
        result.append_text(key_row(key, action))
        result.append("\n")

    result.append("\n")
    result.append("  Detail\n", "bold")

    detail_keys = [
        ("j / k", "move between fields"),
        ("tab / h / l", "cycle TMDB sources"),
        ("enter", "edit field inline"),
        ("shift-enter", "apply all fields from source"),
        ("d", "clear field"),
        ("g", "reset field to guessit value"),
        ("r", "refresh TMDB query"),
        ("c", "confirm changes"),
        ("esc", "discard changes"),
    ]
    for key, action in detail_keys:
        result.append_text(key_row(key, action))
        result.append("\n")

    result.append("\n")
    result.append("  Concepts\n", "bold")
    result.append(f"  {'staged':<16}file will be processed on commit\n")
    result.append(f"  {'unstaged':<16}needs review, check destination\n")
    result.append(f"  {'ignored':<16}skipped entirely\n")

    result.append("\n")
    result.append("  sources provide metadata from TMDB.\n", MUTED)
    result.append("  apply values to the result to build the destination path.\n", MUTED)

    result.append("\n")
    result.append("  press ? or esc to close\n", f"{MUTED} italic")

    return result


class HelpScreen(ModalScreen):
    """Modal screen showing keybinding reference."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    HelpScreen #help-panel {
        width: 64;
        height: auto;
        max-height: 90%;
        border: round #7AB8FF;
        padding: 1 2;
    }
    """

    BINDINGS = [
        Binding("question_mark", "dismiss", "Close", show=False),
        Binding("escape", "dismiss", "Close", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Static(_build_help_text(), id="help-panel")
