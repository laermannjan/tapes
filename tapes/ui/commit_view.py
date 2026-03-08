"""Inline commit confirmation view with file stats and operation selection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget

from tapes.categorize import categorize_staged
from tapes.tree_model import FileNode
from tapes.ui.bottom_bar import OP_COLORS, cycle_operation_index
from tapes.ui.tree_render import ACCENT, MUTED, render_separator

if TYPE_CHECKING:
    from rich.console import RenderableType


class CommitView(Widget):
    """Inline commit view showing staged file stats and operation selection."""

    can_focus = True

    operation: reactive[str] = reactive("copy")
    quit_hint: reactive[str] = reactive("")

    def __init__(self, files: list[FileNode], operation: str, *, widget_id: str | None = None) -> None:
        super().__init__(id=widget_id)
        self._files = files
        self.operation = operation
        self._categories = categorize_staged(files)

    @property
    def computed_height(self) -> int:
        """Compute the height needed for this view."""
        # blank + separator + blank + blank + stats lines + blank + total + blank + op line
        lines = 6  # blank + separator + blank + blank-before-total + total + blank-after-total
        cats = self._categories
        if cats["movies"] or cats["subtitles"] or cats["sidecars"] or cats["other"]:
            lines += 1
        if cats["episodes"]:
            lines += 1
        lines += 2  # blank + op line
        return lines

    def render(self) -> RenderableType:
        w = self.size.width
        return Text("\n").join(self._build_content(w))

    def _build_content(self, width: int) -> list[Text]:
        content: list[Text] = []
        cats = self._categories

        # Blank + separator + blank
        content.append(Text())
        content.append(render_separator(width, title="Commit", color=ACCENT))
        content.append(Text())

        # Blank
        content.append(Text())

        # Stats line 1: movies, subtitles, sidecars, other
        line1_parts: list[str] = []
        if cats["movies"]:
            n = cats["movies"]
            line1_parts.append(f"{n} {'movie' if n == 1 else 'movies'}")
        if cats["subtitles"]:
            n = cats["subtitles"]
            line1_parts.append(f"{n} {'subtitle' if n == 1 else 'subtitles'}")
        if cats["sidecars"]:
            n = cats["sidecars"]
            line1_parts.append(f"{n} {'sidecar' if n == 1 else 'sidecars'}")
        if cats["other"]:
            n = cats["other"]
            line1_parts.append(f"{n} other")
        if line1_parts:
            joined = " \u00b7 ".join(line1_parts)
            content.append(Text(f"  {joined}"))

        # Stats line 2: shows, seasons, episodes
        line2_parts: list[str] = []
        if cats["shows"]:
            n = cats["shows"]
            line2_parts.append(f"{n} {'show' if n == 1 else 'shows'}")
        if cats["seasons"]:
            n = cats["seasons"]
            line2_parts.append(f"{n} {'season' if n == 1 else 'seasons'}")
        if cats["episodes"]:
            n = cats["episodes"]
            line2_parts.append(f"{n} {'episode' if n == 1 else 'episodes'}")
        if line2_parts:
            joined = " \u00b7 ".join(line2_parts)
            content.append(Text(f"  {joined}"))

        # Blank + total
        content.append(Text())
        total = cats["total"]
        content.append(Text(f"  {total} {'file' if total == 1 else 'files'} total"))

        # Blank
        content.append(Text())

        # Operation + hints line (mirrors BottomBar layout)
        bottom = Text()
        bottom.append("  ")
        op_color = OP_COLORS.get(self.operation, "")
        bottom.append(self.operation, style=op_color)
        bottom.append("  ")
        bottom.append("(shift+tab to cycle)", style=MUTED)
        bottom.append("       ")
        if self.quit_hint:
            bottom.append(self.quit_hint, style=f"italic {MUTED}")
        else:
            bottom.append("enter to confirm \u00b7 esc to cancel", style=f"italic {MUTED}")
        content.append(bottom)

        return content

    def cycle_operation(self, delta: int = 1) -> None:
        """Cycle to next/previous operation."""
        self.operation = cycle_operation_index(self.operation, delta)
