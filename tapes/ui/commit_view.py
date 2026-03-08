"""Inline commit confirmation view with file stats and operation selection."""
from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget

from tapes.fields import MEDIA_TYPE, MEDIA_TYPE_EPISODE, MEDIA_TYPE_MOVIE
from tapes.ui.bottom_bar import OPERATIONS, OP_COLORS
from tapes.ui.tree_model import FileNode
from tapes.ui.tree_render import MUTED, render_separator

if TYPE_CHECKING:
    from typing import Any

    from rich.console import RenderableType

ACCENT = "#B1B9F9"

SUBTITLE_EXTS = frozenset({".srt", ".sub", ".ass", ".ssa", ".idx"})
SIDECAR_EXTS = frozenset({".nfo", ".xml", ".jpg", ".png"})


def categorize_staged(files: list[FileNode]) -> dict[str, int]:
    """Categorize staged files and return counts."""
    movies = 0
    episodes = 0
    subtitles = 0
    sidecars = 0
    other = 0
    shows: set[str] = set()
    seasons: set[tuple[str, Any]] = set()

    for f in files:
        ext = f.path.suffix.lower()
        media_type = f.result.get(MEDIA_TYPE)

        if media_type == MEDIA_TYPE_MOVIE:
            movies += 1
        elif media_type == MEDIA_TYPE_EPISODE:
            episodes += 1
            title = f.result.get("title", "")
            season = f.result.get("season")
            if title:
                shows.add(title)
            if title and season is not None:
                seasons.add((title, season))
        elif ext in SUBTITLE_EXTS:
            subtitles += 1
        elif ext in SIDECAR_EXTS:
            sidecars += 1
        else:
            other += 1

    return {
        "movies": movies,
        "episodes": episodes,
        "shows": len(shows),
        "seasons": len(seasons),
        "subtitles": subtitles,
        "sidecars": sidecars,
        "other": other,
        "total": len(files),
    }


class CommitView(Widget):
    """Inline commit view showing staged file stats and operation selection."""

    can_focus = True

    operation: reactive[str] = reactive("copy")
    quit_hint: reactive[str] = reactive("")

    def __init__(self, files: list[FileNode], operation: str, *, id: str | None = None) -> None:
        super().__init__(id=id)
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
            content.append(Text(f"  {' \u00b7 '.join(line1_parts)}"))

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
            content.append(Text(f"  {' \u00b7 '.join(line2_parts)}"))

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
        idx = OPERATIONS.index(self.operation)
        self.operation = OPERATIONS[(idx + delta) % len(OPERATIONS)]
