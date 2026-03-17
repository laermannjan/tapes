"""Pure rendering functions for the file tree."""

from __future__ import annotations

import re as _re
import string as _string
from pathlib import Path
from typing import Any

from rich.text import Text

from tapes.templates import (
    can_fill_template,
    full_extension,
    prepare_template_fields,
    select_template,
    template_field_names,
)
from tapes.tree_model import FileNode, FolderNode, TreeModel
from tapes.ui.colors import (
    AQUA,
    AZURE,
    COLOR_MISSING,
    COLOR_MUTED,
    COLOR_MUTED_LIGHT,
    COLOR_STAGED,
    FLINT,
    LAVENDER,
    SAND,
    SPRING,
    TEAL,
)

# Field-to-color mapping for destination rendering.
# Fields not listed here use normal foreground (empty style).
DEST_FIELD_COLORS: dict[str, str] = {
    "title": SAND,
    "year": AZURE,
    "season": TEAL,
    "episode": AQUA,
    "episode_title": SPRING,
    "ext": FLINT,
}

# Splits a literal string into word runs (odd indices) vs punctuation (even).
_LITERAL_SPLIT_RE = _re.compile(r"([a-zA-Z]+\s*)")

_MISSING_FIELD_RE = _re.compile(r"\{(\w+)\?\}")

_DIM_FACTOR = 0.78


def _dim_hex(color: str) -> str:
    """Darken a hex color by reducing RGB channels."""
    c = color.lstrip("#")
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    f = _DIM_FACTOR
    return f"#{int(r * f):02x}{int(g * f):02x}{int(b * f):02x}"


# Precomputed dim versions for the directory portion.
_DEST_FIELD_COLORS_DIM: dict[str, str] = {k: _dim_hex(v) if v else "" for k, v in DEST_FIELD_COLORS.items()}
_FLINT_DIM = _dim_hex(FLINT)
_MISSING_DIM = _dim_hex(COLOR_MISSING)


def _render_literal(text: Text, literal: str, *, dim: bool = False) -> None:
    """Append template literal text with sep/dim distinction.

    Punctuation characters (parens, slashes, dots, dashes, spaces)
    get normal foreground (separator). Word runs get dim (structural).
    When *dim* is True, colors are darkened for the directory portion.
    """
    parts = _LITERAL_SPLIT_RE.split(literal)
    for i, part in enumerate(parts):
        if not part:
            continue
        if i % 2 == 0:
            # Punctuation / separator
            text.append(part, style=FLINT if dim else "")
        else:
            # Word text -> structural
            text.append(part, style=_FLINT_DIM if dim else FLINT)


def render_dest_from_template(node: FileNode, template: str) -> Text:
    """Render a destination path with per-field semantic coloring.

    Each template field is colored by its role (title, year, episode, etc.).
    Literal text is split into separators (normal) and structural words (dim).
    The directory portion (before the last ``/``) uses darkened colors.
    Missing fields show ``{field?}`` with red braces and the field's own color.
    Returns ``Text("???")`` when all fields are missing.
    """
    fields: dict[str, Any] = prepare_template_fields(node)

    needed = template_field_names(template)
    missing = {f for f in needed if fields.get(f) is None}

    if len(missing) == len(needed):
        return Text("???", style=COLOR_MUTED)

    parts = list(_string.Formatter().parse(template))

    # Find the template part containing the last / to split dir from filename.
    split_part = -1
    split_pos = -1
    for i, (literal, _, _, _) in enumerate(parts):
        if literal and "/" in literal:
            split_part = i
            split_pos = literal.rfind("/")

    result = Text()
    in_dir = split_part >= 0  # start in dir if there's any /

    for part_idx, (literal, field_name, format_spec, _) in enumerate(parts):
        if part_idx > split_part >= 0:
            in_dir = False

        if literal:
            if part_idx == split_part:
                # Split this literal: up to and including / is dir, rest is filename.
                dir_literal = literal[: split_pos + 1]
                file_literal = literal[split_pos + 1 :]
                if dir_literal:
                    _render_literal(result, dir_literal, dim=True)
                if file_literal:
                    _render_literal(result, file_literal, dim=False)
                in_dir = False
            else:
                _render_literal(result, literal, dim=in_dir)

        if field_name is not None:
            colors = _DEST_FIELD_COLORS_DIM if in_dir else DEST_FIELD_COLORS
            color = colors.get(field_name, "")
            # Normal foreground fields get FLINT when in dir.
            if in_dir and not color:
                color = FLINT

            if field_name in missing:
                miss_color = _MISSING_DIM if in_dir else COLOR_MISSING
                result.append("{", style=miss_color)
                result.append(field_name, style=color or miss_color)
                result.append("?}", style=miss_color)
            else:
                val = fields[field_name]
                if format_spec:
                    try:
                        formatted = format(val, format_spec)
                    except (ValueError, TypeError):
                        formatted = str(val)
                else:
                    formatted = str(val)
                result.append(formatted, style=color)

    return result


def render_dest(dest: str | None) -> Text:
    """Render a pre-computed destination string with positional coloring.

    Used as a fallback when no template/node is available.

    - If *dest* is ``None``: returns ``Text("???")`` in muted style.
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

    Staged files show a filled circle before the destination.
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
        row.append(filename, style=LAVENDER)

        if arrow_col is not None:
            current_len = len(row.plain)
            if current_len < arrow_col:
                row.append(" " * (arrow_col - current_len))
            row.append("  \u2192  ", style=COLOR_MUTED)
        else:
            row.append("  \u2192  ", style=COLOR_MUTED)

        if node.staged:
            row.append("\u25c9 ", style=COLOR_STAGED)
        elif can_fill_template(node, node.metadata, movie_template, tv_template):
            row.append("\u25cb ", style=COLOR_MUTED)
        else:
            row.append("\u25cb ", style=COLOR_MISSING)

        row.append_text(render_dest_from_template(node, effective_template))

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
