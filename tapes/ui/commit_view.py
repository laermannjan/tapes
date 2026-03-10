"""Inline commit confirmation view with file stats and operation selection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget

from tapes.categorize import categorize_staged
from tapes.tree_model import FileNode
from tapes.ui.bottom_bar import OP_COLORS, cycle_operation_index
from tapes.ui.colors import COLOR_ACCENT, COLOR_MUTED, COLOR_STAGED, COLOR_WARNING
from tapes.ui.tree_render import render_separator

if TYPE_CHECKING:
    from rich.console import RenderableType

    from tapes.conflicts import ConflictReport


class CommitView(Widget):
    """Inline commit view showing staged file stats and operation selection."""

    can_focus = True

    operation: reactive[str] = reactive("copy")
    quit_hint: reactive[str] = reactive("")
    progress_text: reactive[str] = reactive("")

    def __init__(
        self,
        files: list[FileNode],
        operation: str,
        *,
        movies_path: str = "",
        tv_path: str = "",
        widget_id: str | None = None,
    ) -> None:
        super().__init__(id=widget_id)
        self._files = files
        self.operation = operation
        self._categories = categorize_staged(files)
        self.movies_path = movies_path
        self.tv_path = tv_path
        self.conflict_report: ConflictReport | None = None

    @property
    def computed_height(self) -> int:
        """Compute the height needed for this view."""
        if self.progress_text:
            return 7  # blank + separator + blank + blank + progress line + blank + hint
        # blank + separator + blank + blank + stats lines + blank + total + blank + lib + blank + op line
        lines = 6  # blank + separator + blank + blank-before-total + total + blank-after-total
        cats = self._categories
        if cats["movies"] or cats["subtitles"] or cats["sidecars"] or cats["other"]:
            lines += 1
        if cats["episodes"]:
            lines += 1
        if self.conflict_report:
            resolved = self.conflict_report.resolved
            problems = self.conflict_report.problems
            if resolved or problems:
                lines += 1  # blank before conflicts
                if resolved:
                    lines += 1 + len(resolved)  # header + items
                if problems:
                    if resolved:
                        lines += 1  # blank between sections
                    lines += 1  # header
                    for p in problems:
                        lines += 1  # problem line
                        if p.skipped_nodes:
                            lines += 1  # skipped count
        lines += 4  # lib paths + blank + blank + op line
        return lines

    def render(self) -> RenderableType:
        w = self.size.width
        return Text("\n").join(self._build_content(w))

    def _build_content(self, width: int) -> list[Text]:
        content: list[Text] = []
        cats = self._categories

        content.append(Text())
        content.append(render_separator(width, title="Commit", color=COLOR_ACCENT))
        content.append(Text())

        if self.progress_text:
            return self._build_progress(content, width)

        content.append(Text())

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

        content.append(Text())
        total = cats["total"]
        content.append(Text(f"  {total} {'file' if total == 1 else 'files'} total"))

        if self.conflict_report:
            resolved = self.conflict_report.resolved
            problems = self.conflict_report.problems
            if resolved or problems:
                content.append(Text())
                if resolved:
                    n_resolved = len(resolved)
                    content.append(
                        Text(f"  {n_resolved} conflict{'s' if n_resolved != 1 else ''} resolved:", style=COLOR_MUTED)
                    )
                    for r in resolved:
                        line = Text()
                        line.append("    \u2713 ", style=COLOR_STAGED)
                        line.append(r.description, style=COLOR_MUTED)
                        content.append(line)
                if problems:
                    if resolved:
                        content.append(Text())
                    n_problems = len(problems)
                    content.append(
                        Text(f"  {n_problems} problem{'s' if n_problems != 1 else ''}:", style=COLOR_WARNING)
                    )
                    for p in problems:
                        line = Text()
                        line.append("    \u2717 ", style=COLOR_WARNING)
                        line.append(p.description, style=COLOR_WARNING)
                        content.append(line)
                        if p.skipped_nodes:
                            skip_line = Text()
                            skip_line.append(f"       {len(p.skipped_nodes)} file(s) skipped", style=COLOR_MUTED)
                            content.append(skip_line)

        content.append(Text())

        lib_line = Text()
        lib_line.append("  ")
        lib_line.append("movies", style=COLOR_MUTED)
        lib_line.append(" \u2192 ", style=COLOR_MUTED)
        lib_line.append(self.movies_path or "(not set)", style=COLOR_MUTED)
        lib_line.append("  \u00b7  ", style=COLOR_MUTED)
        lib_line.append("tv", style=COLOR_MUTED)
        lib_line.append(" \u2192 ", style=COLOR_MUTED)
        lib_line.append(self.tv_path or "(not set)", style=COLOR_MUTED)
        content.append(lib_line)

        content.append(Text())

        bottom = Text()
        bottom.append("  ")
        op_color = OP_COLORS.get(self.operation, "")
        bottom.append(self.operation, style=op_color)
        bottom.append("  ")
        bottom.append("(shift+tab to cycle)", style=COLOR_MUTED)
        bottom.append("       ")
        if self.quit_hint:
            bottom.append(self.quit_hint, style=f"italic {COLOR_MUTED}")
        elif self.conflict_report and self.conflict_report.skipped_count > 0:
            total_valid = len(self._files)
            bottom.append(
                f"enter to confirm {total_valid} file{'s' if total_valid != 1 else ''} \u00b7 esc to cancel",
                style=f"italic {COLOR_MUTED}",
            )
        else:
            bottom.append("enter to confirm \u00b7 esc to cancel", style=f"italic {COLOR_MUTED}")
        content.append(bottom)

        return content

    def _build_progress(self, content: list[Text], width: int) -> list[Text]:  # noqa: ARG002
        """Build progress display during file processing."""
        content.append(Text())
        op_color = OP_COLORS.get(self.operation, "")
        status = Text()
        status.append("  ")
        status.append(self.operation, style=op_color)
        status.append("  ")
        status.append(self.progress_text, style=COLOR_MUTED)
        content.append(status)
        content.append(Text())
        hint = Text()
        hint.append("  ")
        hint.append("esc to interrupt", style=f"italic {COLOR_MUTED}")
        content.append(hint)
        return content

    def cycle_operation(self, delta: int = 1) -> None:
        """Cycle to next/previous operation."""
        self.operation = cycle_operation_index(self.operation, delta)
