"""Pure rendering functions for the file tree."""

from __future__ import annotations

import re as _re
from pathlib import Path

from rich.text import Text

from tapes.templates import can_fill_template, compute_dest, full_extension, select_template
from tapes.tree_model import FileNode, FolderNode, TreeModel
from tapes.ui.colors import (
    COLOR_MISSING,
    COLOR_MUTED,
    COLOR_MUTED_LIGHT,
    COLOR_STAGED,
)

_MISSING_FIELD_RE = _re.compile(r"\{(\w+)\?\}")


def render_dest(dest: str | None) -> Text:
    """Render a destination path with semantic coloring.

    - If *dest* is ``None``: returns ``Text("???")`` in muted style.
    - Arrow ``\u2192`` is dim.
    - Directory portion (everything before the last ``/``) is dim.
    - Filename stem (after last ``/``, before last ``.``) is normal foreground.
    - Extension (last ``.`` onward) is dim.
    - Any ``{field?}`` placeholder patterns are highlighted red.
    """
    if dest is None:
        return Text("???", style=COLOR_MUTED)

    result = Text()

    last_slash = dest.rfind("/")
    if last_slash >= 0:
        dir_part = dest[: last_slash + 1]  # includes trailing /
        basename = dest[last_slash + 1 :]
    else:
        dir_part = ""
        basename = dest

    if dir_part:
        _append_with_placeholders(result, dir_part, COLOR_MUTED)

    ext_str = full_extension(Path(basename))
    if ext_str:
        dot_ext = "." + ext_str
        if basename.endswith(dot_ext):
            stem = basename[: -len(dot_ext)]
            ext = dot_ext
        else:
            stem = basename
            ext = ""
    else:
        stem = basename
        ext = ""

    _append_with_placeholders(result, stem, "")

    if ext:
        _append_with_placeholders(result, ext, COLOR_MUTED)

    return result


def _append_with_placeholders(text: Text, s: str, base_style: str) -> None:
    """Append *s* to *text*, coloring ``{field?}`` placeholders red."""
    pos = 0
    for m in _MISSING_FIELD_RE.finditer(s):
        if m.start() > pos:
            text.append(s[pos : m.start()], style=base_style)
        text.append(m.group(0), style=COLOR_MISSING)
        pos = m.end()
    if pos < len(s):
        text.append(s[pos:], style=base_style)


def render_file_row(
    node: FileNode,
    movie_template: str,
    tv_template: str,
    depth: int = 0,
    flat_mode: bool = False,
    root_path: Path | None = None,
    arrow_col: int | None = None,
) -> Text:
    """Render a single file row as a Rich :class:`Text` object.

    Format: ``indent + filename + padding + " \u2192 " + dest``

    When *arrow_col* is given, the filename area is padded so the arrow
    starts at that column position, creating aligned two-column output.

    Staged files show a green tick before the destination.
    Ignored files are rendered in muted style.
    """
    effective_template = select_template(node, movie_template, tv_template)

    indent = "" if flat_mode else "    " * depth

    row = Text()

    if indent:
        row.append(indent)

    if flat_mode and root_path is not None:
        try:
            filename = str(node.path.relative_to(root_path))
        except ValueError:
            filename = node.path.name
    else:
        filename = node.path.name

    if node.ignored:
        row.append(filename, style="strike")
    else:
        row.append(filename)

        if arrow_col is not None:
            current_len = len(row.plain)
            if current_len < arrow_col:
                row.append(" " * (arrow_col - current_len))
            row.append("\u2192 ", style=COLOR_MUTED)
        else:
            row.append("  \u2192  ", style=COLOR_MUTED)

        if node.staged:
            row.append("\u2713 ", style=COLOR_STAGED)
        elif can_fill_template(node, node.metadata, movie_template, tv_template):
            row.append("\u2610 ", style=COLOR_MUTED)
        else:
            row.append("  ")

        dest = compute_dest(node, effective_template)
        row.append_text(render_dest(dest))

    return row


def render_folder_row(node: FolderNode, depth: int = 0) -> Text:
    """Render a single folder row as a Rich :class:`Text` object.

    Format: ``indent + arrow + " " + name + "/"``

    Arrows:
    - ``"\\u25bc"`` (down triangle) if expanded (not collapsed)
    - ``"\\u25b6"`` (right triangle) if collapsed
    """
    indent = "    " * depth
    row = Text()
    if indent:
        row.append(indent)
    arrow = "\u25bc" if not node.collapsed else "\u25b6"
    row.append(arrow, style=COLOR_MUTED_LIGHT)
    row.append(f" {node.name}/", style=COLOR_MUTED)
    return row


def render_row(
    node: FileNode | FolderNode,
    movie_template: str,
    tv_template: str,
    depth: int = 0,
    flat_mode: bool = False,
    root_path: Path | None = None,
    arrow_col: int | None = None,
) -> Text:
    """Render a single row, dispatching to file or folder renderer.

    Returns :class:`Text` for both file and folder rows.
    """
    if isinstance(node, FileNode):
        return render_file_row(
            node,
            movie_template,
            tv_template,
            depth=depth,
            flat_mode=flat_mode,
            root_path=root_path,
            arrow_col=arrow_col,
        )
    return render_folder_row(node, depth=depth)


def flatten_with_depth(
    model: TreeModel,
) -> list[tuple[FileNode | FolderNode, int]]:
    """Flatten the tree respecting collapsed state, returning (node, depth) pairs.

    The root folder itself is NOT included. Depth starts at 0 for
    the root's immediate children.
    """
    result: list[tuple[FileNode | FolderNode, int]] = []
    _flatten_children_with_depth(model.root, result, depth=0)
    return result


def _flatten_children_with_depth(
    folder: FolderNode,
    result: list[tuple[FileNode | FolderNode, int]],
    depth: int,
) -> None:
    """Recursively flatten children, tracking depth."""
    for child in folder.children:
        result.append((child, depth))
        if isinstance(child, FolderNode) and not child.collapsed:
            _flatten_children_with_depth(child, result, depth + 1)


def flatten_all_with_depth(
    model: TreeModel,
) -> list[tuple[FileNode | FolderNode, int]]:
    """Flatten the tree ignoring collapsed state, returning (node, depth) pairs.

    Used for search/filter which needs to see all files regardless of
    folder collapse state.
    """
    result: list[tuple[FileNode | FolderNode, int]] = []
    _flatten_all_children(model.root, result, depth=0)
    return result


def _flatten_all_children(
    folder: FolderNode,
    result: list[tuple[FileNode | FolderNode, int]],
    depth: int,
) -> None:
    """Recursively flatten ALL children, ignoring collapsed state."""
    for child in folder.children:
        result.append((child, depth))
        if isinstance(child, FolderNode):
            _flatten_all_children(child, result, depth + 1)


def render_separator(
    width: int,
    title: str | None = None,
    right_text: str | None = None,
    color: str = "#555555",
) -> Text:
    """Render a horizontal separator line spanning *width* characters.

    Format: ``--- Title ------------------------------ right text``
    """
    line = Text()
    used = 0

    if title:
        prefix = "\u2500\u2500\u2500 "
        line.append(prefix, style=color)
        line.append(title, style=f"bold {color}")
        line.append(" ", style=color)
        used = len(prefix) + len(title) + 1

    right_len = 0
    if right_text:
        # space + text + space + 3 trailing dashes
        right_len = len(right_text) + 5

    fill = width - used - right_len
    if fill > 0:
        line.append("\u2500" * fill, style=color)

    if right_text:
        line.append(" ", style=color)
        line.append(right_text, style=color)
        line.append(" ", style=color)
        line.append("\u2500\u2500\u2500", style=color)

    return line
