"""Pure rendering functions for the file tree."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from rich.text import Text

from tapes.fields import MEDIA_TYPE, MEDIA_TYPE_EPISODE
from tapes.tree_model import FileNode, FolderNode, TreeModel

# Explicit muted gray instead of Rich "dim" (which thins the font weight).
MUTED = "#888888"
# Lighter muted for fold arrows (more visible than MUTED).
MUTED_LIGHT = "#aaaaaa"
# Green tick for staged files.
STAGED_COLOR = "#4EBA65"
# Cursor highlight (lazygit-style dark slate).
CURSOR_BG = "on #373737"
# Range selection background (matches cursor).
RANGE_BG = "on #373737"


def template_field_names(template: str) -> list[str]:
    """Extract unique field names referenced in a template string."""
    return list(dict.fromkeys(m.group(1).split(":")[0] for m in re.finditer(r"\{(\w+[^}]*)\}", template)))


def select_template(node: FileNode, movie_template: str, tv_template: str) -> str:
    """Select the appropriate template based on the node's media_type.

    Returns ``tv_template`` if ``media_type`` is ``"episode"``,
    otherwise ``movie_template``.
    """
    media_type = node.result.get(MEDIA_TYPE)
    if media_type == MEDIA_TYPE_EPISODE:
        return tv_template
    return movie_template


_KNOWN_TAGS = frozenset({"forced", "sdh", "signs", "commentary"})


def _is_tag(s: str) -> bool:
    """Check if a suffix component is a language/subtitle tag."""
    return s.lower() in _KNOWN_TAGS or (len(s) in (2, 3) and s.isalpha())


def full_extension(path: Path) -> str:
    """Return the full extension, preserving tags like '.forced.en.srt'.

    Walks backwards through suffixes, collecting consecutive tags
    (language codes, 'forced', 'sdh', etc.) that precede the final
    extension.  Also picks up hyphen-prefixed tags (e.g. ``-forced``)
    that appear just before the dot-suffix chain in the stem.
    """
    suffixes = path.suffixes
    if not suffixes:
        return ""
    # Always include the last suffix; walk backwards collecting tags
    count = 1
    for i in range(len(suffixes) - 2, -1, -1):
        tag = suffixes[i].lstrip(".")
        if _is_tag(tag):
            count += 1
        else:
            break

    ext = "".join(suffixes[-count:]).lstrip(".")

    # Check for hyphen-prefixed tags in the stem (e.g. "movie-forced")
    stem = path.name[: -len("." + ext)] if ext else path.stem
    while "-" in stem:
        last_hyphen = stem.rfind("-")
        candidate = stem[last_hyphen + 1 :]
        if _is_tag(candidate):
            ext = candidate + "." + ext
            stem = stem[:last_hyphen]
        else:
            break

    return ext


def compute_dest(node: FileNode, template: str) -> str | None:
    """Compute the destination path for a file node using a template.

    Extracts fields from ``node.result`` and adds ``ext`` from the file
    suffix. Returns None if any required template field is missing or None.

    Format specs (e.g. ``{season:02d}``) are applied when all fields are
    present. If a field with a format spec is missing, the spec is dropped
    and ``?`` is shown instead so the user can see partial progress.
    """
    fields: dict[str, Any] = dict(node.result)
    fields["ext"] = full_extension(node.path)

    needed = template_field_names(template)
    missing = [f for f in needed if fields.get(f) is None]

    if not missing:
        return template.format_map(fields)

    # All fields missing -> no useful destination
    if len(missing) == len(needed):
        return None

    # Partial: fill missing fields with "?" and strip format specs
    patched = dict(fields)
    for f in missing:
        patched[f] = "?"
    # Remove format specs so "?" doesn't fail on e.g. :02d
    safe_template = re.sub(r"\{(\w+):[^}]+\}", r"{\1}", template)
    return safe_template.format_map(patched)


def render_dest(dest: str | None) -> Text:
    """Render a destination path with semantic coloring.

    - If *dest* is ``None``: returns ``Text("???")`` in muted style.
    - Arrow ``\u2192`` is dim.
    - Directory portion (everything before the last ``/``) is dim.
    - Filename stem (after last ``/``, before last ``.``) is normal foreground.
    - Extension (last ``.`` onward) is dim.
    - Any ``?`` placeholder characters are highlighted ember.
    """
    if dest is None:
        return Text("???", style=MUTED)

    result = Text()

    # Split into directory and basename
    last_slash = dest.rfind("/")
    if last_slash >= 0:
        dir_part = dest[: last_slash + 1]  # includes trailing /
        basename = dest[last_slash + 1 :]
    else:
        dir_part = ""
        basename = dest

    # Render directory part: dim, but ? chars yellow
    if dir_part:
        _append_with_yellow_placeholders(result, dir_part, MUTED)

    # Split basename into stem and full extension (e.g. ".en.srt")
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

    # Render stem: normal, but ? chars yellow
    _append_with_yellow_placeholders(result, stem, "")

    # Render extension: dim, but ? chars yellow
    if ext:
        _append_with_yellow_placeholders(result, ext, MUTED)

    return result


def _append_with_yellow_placeholders(text: Text, s: str, base_style: str) -> None:
    """Append *s* to *text*, coloring ``?`` characters yellow."""
    i = 0
    while i < len(s):
        j = i
        if s[i] == "?":
            # Collect consecutive ?
            while j < len(s) and s[j] == "?":
                j += 1
            text.append(s[i:j], style="#E07A47")
        else:
            # Collect non-? characters
            while j < len(s) and s[j] != "?":
                j += 1
            text.append(s[i:j], style=base_style)
        i = j


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

        # Pad to arrow column if specified
        if arrow_col is not None:
            current_len = len(row.plain)
            if current_len < arrow_col:
                row.append(" " * (arrow_col - current_len))
            row.append("\u2192 ", style=MUTED)
        else:
            row.append("  \u2192  ", style=MUTED)

        # Staged tick (green ✓) or blank placeholder for alignment
        if node.staged:
            row.append("\u2713 ", style=STAGED_COLOR)
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
    row.append(arrow, style=MUTED_LIGHT)
    row.append(f" {node.name}/", style=MUTED)
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

    Format: ``─── Title ──────────────────── right text``
    """
    line = Text()
    used = 0

    if title:
        prefix = "─── "
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
        line.append("─" * fill, style=color)

    if right_text:
        line.append(" ", style=color)
        line.append(right_text, style=color)
        line.append(" ", style=color)
        line.append("───", style=color)

    return line
