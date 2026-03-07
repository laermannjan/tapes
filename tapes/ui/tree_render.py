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


def compute_dest(node: FileNode, template: str) -> str | None:
    """Compute the destination path for a file node using a template.

    Extracts fields from ``node.result`` and adds ``ext`` from the file
    suffix. Returns None if any required template field is missing.
    """
    fields: dict[str, Any] = dict(node.result)
    fields["ext"] = node.path.suffix.lstrip(".")

    needed = template_field_names(template)
    if any(f not in fields for f in needed):
        return None

    return template.format_map(fields)


def render_file_row(
    node: FileNode,
    template: str,
    depth: int = 0,
    flat_mode: bool = False,
    root_path: Path | None = None,
) -> str:
    """Render a single file row as a plain string.

    Format: ``indent + marker + " " + filename + "  ->  " + dest``

    Markers:
    - ``"\\u2713"`` (checkmark) if staged
    - ``"\\u25cb"`` (circle) if not staged and not ignored
    - ``" "`` (space) if ignored
    """
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

    dest = compute_dest(node, template) or "???"

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
) -> str:
    """Render a single row, dispatching to file or folder renderer."""
    if isinstance(node, FileNode):
        return render_file_row(
            node, template, depth=depth, flat_mode=flat_mode, root_path=root_path
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
