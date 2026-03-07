"""Pure rendering functions for the file tree."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tapes.ui.tree_model import FileNode, FolderNode, TreeModel


def template_field_names(template: str) -> list[str]:
    """Extract unique field names referenced in a template string."""
    return list(
        dict.fromkeys(
            m.group(1).split(":")[0]
            for m in re.finditer(r"\{(\w+[^}]*)\}", template)
        )
    )


def select_template(
    node: FileNode, movie_template: str, tv_template: str
) -> str:
    """Select the appropriate template based on the node's media_type.

    Returns ``tv_template`` if ``media_type`` is ``"episode"``,
    otherwise ``movie_template``.
    """
    media_type = node.result.get("media_type")
    if media_type == "episode":
        return tv_template
    return movie_template


def compute_dest(node: FileNode, template: str) -> str | None:
    """Compute the destination path for a file node using a template.

    Extracts fields from ``node.result`` and adds ``ext`` from the file
    suffix. Returns None if any required template field is missing or None.

    Format specs (e.g. ``{season:02d}``) are applied when all fields are
    present. If a field with a format spec is missing, the spec is dropped
    and ``?`` is shown instead so the user can see partial progress.
    """
    fields: dict[str, Any] = dict(node.result)
    fields["ext"] = node.path.suffix.lstrip(".")

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


def render_file_row(
    node: FileNode,
    template: str,
    depth: int = 0,
    flat_mode: bool = False,
    root_path: Path | None = None,
    *,
    movie_template: str | None = None,
    tv_template: str | None = None,
) -> str:
    """Render a single file row as a plain string.

    Format: ``indent + marker + " " + filename + "  ->  " + dest``

    When *movie_template* and *tv_template* are provided, the template is
    selected automatically based on ``node.result["media_type"]`` and the
    *template* parameter is ignored.

    Markers:
    - ``"\\u2713"`` (checkmark) if staged
    - ``"\\u25cb"`` (circle) if not staged and not ignored
    - ``" "`` (space) if ignored
    """
    if movie_template is not None and tv_template is not None:
        effective_template = select_template(node, movie_template, tv_template)
    else:
        effective_template = template

    indent = "" if flat_mode else "  " * depth

    if node.staged:
        marker = "\u2713"
    elif node.ignored:
        marker = " "
    else:
        marker = "\u25cb"

    if flat_mode and root_path is not None:
        try:
            filename = str(node.path.relative_to(root_path))
        except ValueError:
            filename = node.path.name
    else:
        filename = node.path.name

    dest = compute_dest(node, effective_template) or "???"

    return f"{indent}{marker} {filename}  \u2192  {dest}"


def render_folder_row(node: FolderNode, depth: int = 0) -> str:
    """Render a single folder row as a plain string.

    Format: ``indent + arrow + " " + name + "/"``

    Arrows:
    - ``"\\u25bc"`` (down triangle) if expanded (not collapsed)
    - ``"\\u25b6"`` (right triangle) if collapsed
    """
    indent = "  " * depth
    arrow = "\u25b6" if node.collapsed else "\u25bc"
    return f"{indent}{arrow} {node.name}/"


def render_row(
    node: FileNode | FolderNode,
    template: str,
    depth: int = 0,
    flat_mode: bool = False,
    root_path: Path | None = None,
    *,
    movie_template: str | None = None,
    tv_template: str | None = None,
) -> str:
    """Render a single row, dispatching to file or folder renderer."""
    if isinstance(node, FileNode):
        return render_file_row(
            node,
            template,
            depth=depth,
            flat_mode=flat_mode,
            root_path=root_path,
            movie_template=movie_template,
            tv_template=tv_template,
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
