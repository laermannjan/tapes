"""Pure rendering functions for the detail view grid."""
from __future__ import annotations

from typing import Any

from tapes.ui.tree_model import FileNode
from tapes.ui.tree_render import MUTED, compute_dest, template_field_names

LABEL_WIDTH = 16
COL_WIDTH = 28


def get_display_fields(template: str) -> list[str]:
    """Fields to show in the detail grid, derived from template.

    Always includes ``tmdb_id`` as the first field. Extracts remaining
    field names from ``{field}`` placeholders and excludes ``ext``
    (which is always derived from the file extension, not user-editable).
    """
    fields = [f for f in template_field_names(template) if f != "ext"]
    if "tmdb_id" not in fields:
        fields.insert(0, "tmdb_id")
    return fields


def display_val(val: Any) -> str:
    """Format a value for display. None becomes '?'."""
    if val is None:
        return "?"
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
            parts.append(col("  ?"))
        lines.append("".join(parts))

    return lines


def is_multi_value(val: Any) -> bool:
    """Return True if the value is a multi-value marker like '(N values)'."""
    if not isinstance(val, str):
        return False
    return val.startswith("(") and val.endswith(" values)")


def diff_style(result_val: Any, source_val: Any) -> str:
    """Return a Rich style for a source value relative to the result.

    - Muted gray if source is None (missing) or matches the result.
    - ``"green"`` if source fills an empty result slot.
    - ``"#E07A47"`` (ember) if source differs from a non-empty result.
    """
    if source_val is None:
        return MUTED
    if result_val is None or result_val == "":
        return "#86E89A"
    if str(result_val) == str(source_val):
        return MUTED
    return "#E07A47"


def confidence_style(confidence: float) -> str:
    """Return a Rich style for a confidence percentage.

    - Muted for >= 80% (normal, nothing to worry about).
    - ``"#E07A47"`` (ember) for 50-79%.
    - ``"#FF7A7A"`` (soft red) for < 50%.
    """
    if confidence >= 0.8:
        return "#888888"
    if confidence >= 0.5:
        return "#E07A47"
    return "#FF7A7A"


def col(text: str) -> str:
    """Pad or truncate text to COL_WIDTH."""
    if len(text) > COL_WIDTH:
        return text[: COL_WIDTH - 1] + "\u2026"
    return text.ljust(COL_WIDTH)
