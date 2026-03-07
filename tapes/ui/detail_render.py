"""Pure rendering functions for the detail view grid."""
from __future__ import annotations

from typing import Any

from tapes.ui.tree_model import FileNode
from tapes.ui.tree_render import compute_dest, template_field_names

LABEL_WIDTH = 14
COL_WIDTH = 28


def get_display_fields(template: str) -> list[str]:
    """Fields to show in the detail grid, derived from template.

    Extracts field names from ``{field}`` placeholders and excludes ``ext``
    (which is always derived from the file extension, not user-editable).
    """
    return [f for f in template_field_names(template) if f != "ext"]


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
    node: FileNode, template: str, source_index: int = 0
) -> list[str]:
    """Render the field/source grid as plain-text lines.

    Shows result column and one source (selected by source_index).
    Used for content validation in tests. The real TUI renders via
    Rich Text with cursor highlighting in ``DetailView.render()``.
    """
    fields = get_display_fields(template)
    sources = node.sources

    lines: list[str] = []

    # Header row
    header_parts: list[str] = [" " * LABEL_WIDTH + col("result")]
    header_parts.append("\u2503")
    if sources:
        idx = min(source_index, len(sources) - 1)
        src = sources[idx]
        conf = f" ({src.confidence:.0%})" if src.confidence else ""
        indicator = f"  [{idx + 1}/{len(sources)}]"
        header_parts.append(col(f"  {src.name}{conf}{indicator}"))
    else:
        header_parts.append(col("  (no sources)"))
    lines.append("".join(header_parts))

    # Field rows
    for field_name in fields:
        label = f" {field_name:<{LABEL_WIDTH - 1}}"
        result_val = display_val(node.result.get(field_name))

        parts: list[str] = [label + col(result_val)]
        parts.append("\u2503")
        if sources:
            idx = min(source_index, len(sources) - 1)
            src_val = display_val(sources[idx].fields.get(field_name))
            parts.append(col(f"  {src_val}"))
        else:
            parts.append(col("  \u00b7"))
        lines.append("".join(parts))

    return lines


def col(text: str) -> str:
    """Pad or truncate text to COL_WIDTH."""
    if len(text) > COL_WIDTH:
        return text[: COL_WIDTH - 1] + "\u2026"
    return text.ljust(COL_WIDTH)
