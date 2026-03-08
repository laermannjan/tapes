"""Persistent bottom bar with search input, operation mode, and hints."""
from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget

from tapes.ui.tree_render import MUTED, render_separator

if TYPE_CHECKING:
    from rich.console import RenderableType

# Accent color for active search separator.
ACCENT = "#B1B9F9"
# Inactive separator color.
INACTIVE = "#555555"

OPERATIONS = ["copy", "move", "link", "hardlink"]

OP_COLORS: dict[str, str] = {
    "copy": "#86E89A",
    "move": "#E07A47",
    "link": "#7AB8FF",
    "hardlink": "#7AB8FF",
}


class BottomBar(Widget):
    """Bottom bar showing stats, search input, operation mode, and hints."""

    stats_text: reactive[str] = reactive("")
    search_query: reactive[str] = reactive("")
    search_active: reactive[bool] = reactive(False)
    operation: reactive[str] = reactive("copy")
    hint_text: reactive[str] = reactive("")

    def render(self) -> RenderableType:
        w = self.size.width
        sep_color = ACCENT if self.search_active else INACTIVE

        lines: list[Text] = []

        # Blank line above separator
        lines.append(Text())

        # Line 1: separator with stats
        lines.append(
            render_separator(w, right_text=self.stats_text or None, color=sep_color)
        )

        # Line 2: search input
        search_line = Text()
        search_style = "" if self.search_active else MUTED
        search_line.append("  /", style=search_style)
        if self.search_query:
            search_line.append(self.search_query, style=search_style)
        if self.search_active:
            search_line.append("\u2588")
        lines.append(search_line)

        # Line 3: separator
        lines.append(render_separator(w, color=sep_color))

        # Line 4: operation + hints
        bottom = Text()
        bottom.append("  ")
        op_color = OP_COLORS.get(self.operation, "")
        bottom.append(self.operation, style=op_color)
        bottom.append("  ")
        bottom.append("(shift+tab to cycle)", style=MUTED)
        if self.hint_text:
            bottom.append("       ")
            bottom.append(self.hint_text, style=f"italic {MUTED}")
        lines.append(bottom)

        return Text("\n").join(lines)

    def cycle_operation(self, delta: int = 1) -> None:
        """Cycle to next/previous operation."""
        idx = OPERATIONS.index(self.operation)
        self.operation = OPERATIONS[(idx + delta) % len(OPERATIONS)]
