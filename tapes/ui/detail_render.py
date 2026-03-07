"""Pure rendering functions for the detail view grid."""
from __future__ import annotations

from typing import Any

from rich.text import Text

from tapes.ui.tree_model import FileNode, FolderNode, collect_files
from tapes.ui.tree_render import MUTED, compute_dest, render_dest, template_field_names

LABEL_WIDTH = 16
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

    - ``"#86E89A"`` (soft green) for >= 80%.
    - ``"#E07A47"`` (ember) for 50-79%.
    - ``"#FF7A7A"`` (soft red) for < 50%.
    """
    if confidence >= 0.8:
        return "#86E89A"
    if confidence >= 0.5:
        return "#E07A47"
    return "#FF7A7A"


def col(text: str) -> str:
    """Pad or truncate text to COL_WIDTH."""
    if len(text) > COL_WIDTH:
        return text[: COL_WIDTH - 1] + "\u2026"
    return text.ljust(COL_WIDTH)


def render_compact_preview(node: FileNode, template: str) -> Text:
    """Render a 2-line compact preview for a file node.

    Line 1: filename (bold white) + "  " + destination (styled)
    Line 2: key fields (title, year, type, S, E) with dim labels
             and TMDB confidence on the right.
    """
    # Line 1: filename -> destination
    line1 = Text()
    line1.append(f" {node.path.name}", style="bold")
    line1.append("  ")
    line1.append("\u2192 ", style=MUTED)
    dest = compute_dest(node, template)
    line1.append_text(render_dest(dest))

    # Line 2: key fields + TMDB confidence
    line2 = Text()
    line2.append(" ")

    result = node.result
    field_specs = [
        ("title", "title"),
        ("year", "year"),
        ("type", "media_type"),
        ("S", "season"),
        ("E", "episode"),
    ]
    for i, (label, key) in enumerate(field_specs):
        if i > 0:
            line2.append("  ")
        line2.append(f"{label}: ", style=MUTED)
        val = result.get(key)
        if val is None:
            line2.append("\u00b7", style=MUTED)
        else:
            line2.append(str(val))

    # TMDB confidence from best source
    best_conf = 0.0
    for src in node.sources:
        if src.confidence > best_conf:
            best_conf = src.confidence
    if best_conf > 0:
        conf_str = f"{best_conf:.0%}"
        # Right-align: add spacing
        line2.append("  ")
        line2.append("TMDB ", style="#7AB8FF")
        line2.append(conf_str, style=confidence_style(best_conf))

    result_text = Text()
    result_text.append_text(line1)
    result_text.append("\n")
    result_text.append_text(line2)
    return result_text


def render_folder_preview(folder: FolderNode) -> Text:
    """Render a 2-line compact preview for a folder node.

    Line 1: folder name + "/" (bold white)
    Line 2: "N files . N unstaged . N ignored" (dim), omitting zero counts.
    """
    line1 = Text()
    line1.append(f" {folder.name}/", style="bold")

    files = collect_files(folder)
    total = len(files)
    unstaged = sum(1 for f in files if not f.staged and not f.ignored)
    ignored = sum(1 for f in files if f.ignored)

    parts: list[str] = []
    if total > 0:
        parts.append(f"{total} file{'s' if total != 1 else ''}")
    if unstaged > 0:
        parts.append(f"{unstaged} unstaged")
    if ignored > 0:
        parts.append(f"{ignored} ignored")

    line2 = Text()
    line2.append(" ")
    if parts:
        line2.append(" \u00b7 ".join(parts), style=MUTED)
    else:
        line2.append("empty", style=MUTED)

    result_text = Text()
    result_text.append_text(line1)
    result_text.append("\n")
    result_text.append_text(line2)
    return result_text
