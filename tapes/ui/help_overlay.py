"""Help overlay showing keybinding reference."""
from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.widget import Widget

if TYPE_CHECKING:
    from rich.console import RenderableType


# Box-drawing characters
_H = "\u2500"  # horizontal
_V = "\u2502"  # vertical
_TL = "\u256d"  # top-left
_TR = "\u256e"  # top-right
_BL = "\u2570"  # bottom-left
_BR = "\u256f"  # bottom-right

_WIDTH = 62  # inner content width


def _border_top(title: str = "") -> str:
    if title:
        title_part = f" {title} "
        remaining = _WIDTH - len(title_part)
        left = remaining // 2
        right = remaining - left
        return f"{_TL}{_H * left}{title_part}{_H * right}{_TR}"
    return f"{_TL}{_H * _WIDTH}{_TR}"


def _border_bottom() -> str:
    return f"{_BL}{_H * _WIDTH}{_BR}"


def _border_line(content: str = "") -> str:
    padding = _WIDTH - len(content)
    return f"{_V}{content}{' ' * padding}{_V}"


def _build_help_text() -> Text:
    """Build the full help overlay content as a Rich Text object."""

    # Helper to build a keybinding row
    def key_row(key: str, action: str) -> Text:
        t = Text()
        t.append("  ")
        t.append(f"{key:<14}", "#7AB8FF")
        t.append(action)
        pad = _WIDTH - 2 - 14 - len(action)
        if pad > 0:
            t.append(" " * pad)
        return t

    result = Text()

    result.append(_border_top("Help") + "\n")
    result.append(_border_line() + "\n")

    # Files section
    result.append(_border_line("  Files") + "\n", "bold underline")
    result.append(_border_line() + "\n")

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
        row = key_row(key, action)
        bordered = Text()
        bordered.append(f"{_V}")
        bordered.append_text(row)
        bordered.append(f"{_V}\n")
        result.append_text(bordered)

    result.append(_border_line() + "\n")

    # Detail section
    result.append(_border_line("  Detail") + "\n", "bold underline")
    result.append(_border_line() + "\n")

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
        row = key_row(key, action)
        bordered = Text()
        bordered.append(f"{_V}")
        bordered.append_text(row)
        bordered.append(f"{_V}\n")
        result.append_text(bordered)

    result.append(_border_line() + "\n")
    result.append(_border_line() + "\n")

    # Concepts section
    result.append(_border_line("  Concepts") + "\n", "bold underline")
    result.append(_border_line() + "\n")

    concepts = [
        ("\u2713 staged", "file will be processed on commit"),
        ("\u25cb unstaged", "needs review, check destination"),
        ("\u00b7 ignored", "skipped entirely"),
    ]

    for symbol, desc in concepts:
        line = f"  {symbol:<14}{desc}"
        result.append(_border_line(line) + "\n")

    result.append(_border_line() + "\n")

    source_line1 = "  Sources provide metadata from TMDB. Apply values"
    source_line2 = "  to the result to build the destination path."
    result.append(_border_line(source_line1) + "\n", "dim")
    result.append(_border_line(source_line2) + "\n", "dim")

    result.append(_border_line() + "\n")
    result.append(
        _border_line("  Press ? or esc to close") + "\n", "dim italic"
    )
    result.append(_border_bottom() + "\n")

    return result


class HelpOverlay(Widget):
    """Centered modal overlay showing keybinding reference."""

    DEFAULT_CSS = """
    HelpOverlay {
        width: 100%;
        height: 100%;
        content-align: center middle;
    }
    """

    can_focus = True

    def render(self) -> RenderableType:
        return _build_help_text()
