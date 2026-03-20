"""Inline help view showing workflow guide and keybinding reference."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.widget import Widget

from tapes.ui.colors import COLOR_ACCENT, COLOR_MUTED
from tapes.ui.tree_render import render_separator

if TYPE_CHECKING:
    from rich.console import RenderableType

KEY_COLOR = COLOR_ACCENT
# Help content line count (update if content changes).
HELP_HEIGHT = 38


def _build_help_content(width: int) -> list[Text]:
    """Build the help view content."""

    def key_row(key: str, desc: str) -> Text:
        t = Text()
        t.append(f"    {key:<16}", KEY_COLOR)
        t.append(desc)
        return t

    def heading(title: str) -> Text:
        return Text(f"    {title}", style="bold")

    def body(text: str) -> Text:
        return Text(f"    {text}", style=COLOR_MUTED)

    lines: list[Text] = []

    # Separator
    lines.append(Text())
    lines.append(render_separator(width, title="Help", color=COLOR_ACCENT))
    lines.append(Text())

    # Workflow overview
    lines.append(heading("How it works"))
    lines.append(body("Tapes scans a folder, extracts metadata from filenames, and"))
    lines.append(body("searches TMDB for matches. You review and curate the results,"))
    lines.append(body("then commit to copy/move/link files into your library."))
    lines.append(Text())

    # File browser keys
    lines.append(heading("File browser"))
    lines.append(key_row("j / k", "move cursor"))
    lines.append(key_row("enter", "open metadata view"))
    lines.append(key_row("space", "stage / unstage for commit"))
    lines.append(key_row("h / l", "collapse / expand folder"))
    lines.append(key_row("x", "reject file (won't be processed)"))
    lines.append(key_row("v", "start visual range select"))
    lines.append(key_row("/", "search and filter"))
    lines.append(key_row("r", "re-query TMDB with current metadata"))
    lines.append(key_row("tab", "open commit preview"))
    lines.append(key_row("shift+tab", "cycle operation (copy/move/link/hardlink)"))
    lines.append(key_row("ctrl+c ctrl+c", "quit"))
    lines.append(Text())

    # Metadata view keys
    lines.append(heading("Metadata view"))
    lines.append(key_row("enter", "accept focused column and return"))
    lines.append(key_row("esc", "discard changes and return"))
    lines.append(key_row("e", "edit field value inline"))
    lines.append(key_row("backspace", "clear field"))
    lines.append(key_row("tab", "cycle TMDB candidates"))
    lines.append(key_row("shift+tab", "toggle focus: metadata / candidate"))
    lines.append(key_row("r", "refresh TMDB candidates"))
    lines.append(key_row("ctrl+r", "reset field from filename"))
    lines.append(Text())

    # Tips
    lines.append(heading("Tips"))
    lines.append(body("High-score TMDB candidates are auto-accepted and staged."))
    lines.append(body("Files need complete metadata before they can be staged."))
    lines.append(body("\u2610 means ready to stage, \u2713 means staged."))
    lines.append(body("Use v to select a range, then enter to bulk-edit metadata."))
    lines.append(Text())

    # Footer
    lines.append(Text("    ? or esc to close", style=f"italic {COLOR_MUTED}"))

    return lines


class HelpView(Widget):
    """Inline help view showing workflow guide and keybindings."""

    can_focus = True

    def render(self) -> RenderableType:
        return Text("\n").join(_build_help_content(self.size.width))
