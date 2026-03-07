"""Commit confirmation modal listing staged files with destinations."""
from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.widget import Widget

from tapes.ui.tree_render import MUTED, render_dest

if TYPE_CHECKING:
    from rich.console import RenderableType


# Box-drawing characters
_H = "\u2500"  # horizontal
_V = "\u2502"  # vertical
_TL = "\u256d"  # top-left
_TR = "\u256e"  # top-right
_BL = "\u2570"  # bottom-left
_BR = "\u256f"  # bottom-right

_WIDTH = 54  # inner content width


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


def _border_line_text(content: Text) -> Text:
    """Build a bordered line from a Rich Text object, padding to _WIDTH."""
    plain_len = len(content.plain)
    padding = _WIDTH - plain_len
    result = Text()
    result.append(_V)
    result.append_text(content)
    if padding > 0:
        result.append(" " * padding)
    result.append(_V)
    return result


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

    result.append(_border_top("Commit") + "\n")
    result.append(_border_line() + "\n")
    result.append(_border_line(f"  {op_label} {count} {noun} to library?") + "\n")
    result.append(_border_line() + "\n")

    for filename, dest in staged_files:
        # File line: checkmark + filename
        file_line = Text()
        file_line.append("  ")
        file_line.append("\u2713", style="#86E89A")
        file_line.append(" ")
        # Truncate filename if too long
        max_name = _WIDTH - 4  # 2 indent + checkmark + space
        if len(filename) > max_name:
            filename = filename[: max_name - 1] + "\u2026"
        file_line.append(filename)
        result.append_text(_border_line_text(file_line))
        result.append("\n")

        # Destination line: arrow + rendered dest
        dest_line = Text()
        dest_line.append("    \u2192 ", style=MUTED)
        if dest is not None:
            dest_text = render_dest(dest)
            # Truncate if needed
            max_dest = _WIDTH - 6  # 4 spaces + arrow + space
            if len(dest_text.plain) > max_dest:
                plain = dest_text.plain[: max_dest - 1] + "\u2026"
                dest_line.append(plain, style=MUTED)
            else:
                dest_line.append_text(dest_text)
        else:
            dest_line.append("???", style=MUTED)
        result.append_text(_border_line_text(dest_line))
        result.append("\n")

    result.append(_border_line() + "\n")

    # Footer with keybinding hints
    hint = Text()
    hint.append("  ")
    hint.append("y", style="#7AB8FF")
    hint.append(" confirm    ")
    hint.append("n", style="#7AB8FF")
    hint.append(" cancel")
    result.append_text(_border_line_text(hint))
    result.append("\n")

    result.append(_border_line() + "\n")
    result.append(_border_bottom() + "\n")

    return result


class CommitModal(Widget):
    """Centered modal overlay showing commit confirmation."""

    DEFAULT_CSS = """
    CommitModal {
        width: 100%;
        height: 100%;
        content-align: center middle;
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

    def update_content(
        self,
        staged_files: list[tuple[str, str | None]],
        operation: str,
    ) -> None:
        """Update the modal content and refresh."""
        self._staged_files = staged_files
        self._operation = operation
        self.refresh()

    def render(self) -> RenderableType:
        return build_commit_text(self._staged_files, self._operation)
