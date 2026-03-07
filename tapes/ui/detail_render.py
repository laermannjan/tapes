"""Pure rendering functions for the detail view grid."""
from __future__ import annotations

import re
from typing import Any

from tapes.ui.tree_model import FileNode
from tapes.ui.tree_render import compute_dest

LABEL_WIDTH = 14
COL_WIDTH = 16


def get_display_fields(template: str) -> list[str]:
    """Fields to show in the detail grid, derived from template.

    Extracts field names from ``{field}`` placeholders and excludes ``ext``
    (which is always derived from the file extension, not user-editable).
    """
    return [
        m.group(1).split(":")[0]
        for m in re.finditer(r"\{(\w+[^}]*)\}", template)
        if m.group(1).split(":")[0] != "ext"
    ]


def display_val(val: Any) -> str:
    """Format a value for display. None becomes a centered dot."""
    if val is None:
        return "\u00b7"
    return str(val)


def render_detail_header(node: FileNode, template: str) -> list[str]:
    """Render the filename and destination lines."""
    dest = compute_dest(node, template) or "???"
    return [
        f" {node.path.name}",
        f" \u2192 {dest}",
    ]


def render_detail_grid(
    node: FileNode,
    template: str,
    cursor_row: int | None = None,
    cursor_col: int | None = None,
) -> list[str]:
    """Render the field/source grid with optional cursor highlighting.

    Parameters
    ----------
    cursor_row:
        -1 = header row, 0+ = field rows. None means no cursor.
    cursor_col:
        0 = result column, 1+ = source index. None means no cursor.

    Returns a list of plain-text lines. Cursor position is marked with
    ``>>`` prefix on the cell (for test assertions); real TUI uses
    reverse video via Rich Text styling.
    """
    fields = get_display_fields(template)
    sources = node.sources

    lines: list[str] = []

    # Header row
    header_parts: list[str] = [" " * LABEL_WIDTH + _col("result")]
    header_parts.append("\u2503")
    for i, src in enumerate(sources):
        conf = f" ({src.confidence:.0%})" if src.confidence else ""
        header_parts.append(_col(f"  {src.name}{conf}"))
    lines.append("".join(header_parts))

    # Field rows
    for row_idx, field_name in enumerate(fields):
        label = f" {field_name:<{LABEL_WIDTH - 1}}"
        result_val = display_val(node.result.get(field_name))

        parts: list[str] = [label + _col(result_val)]
        parts.append("\u2503")
        for src in sources:
            src_val = display_val(src.fields.get(field_name))
            parts.append(_col(f"  {src_val}"))
        lines.append("".join(parts))

    return lines


def _col(text: str) -> str:
    """Pad or truncate text to COL_WIDTH."""
    if len(text) > COL_WIDTH:
        return text[: COL_WIDTH - 1] + "\u2026"
    return text.ljust(COL_WIDTH)
