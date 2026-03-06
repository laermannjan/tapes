"""Destination path computation for the grid TUI."""
from __future__ import annotations

import re
from pathlib import PurePosixPath

from tapes.ui.models import GridRow


def _row_fields(row: GridRow) -> dict[str, str | int]:
    """Extract template fields from a GridRow."""
    ext = PurePosixPath(row.filepath).suffix.lstrip(".")
    fields: dict[str, str | int] = {"ext": ext}
    if row.title is not None:
        fields["title"] = row.title
    if row.year is not None:
        fields["year"] = row.year
    if row.season is not None:
        fields["season"] = row.season
    if row.episode is not None and isinstance(row.episode, int):
        fields["episode"] = row.episode
    if row.episode_title is not None:
        fields["episode_title"] = row.episode_title
    return fields


def _template_field_names(template: str) -> list[str]:
    """Extract unique field names referenced in a template string."""
    return list(dict.fromkeys(
        m.group(1).split(":")[0]
        for m in re.finditer(r"\{(\w+[^}]*)\}", template)
    ))


def missing_template_fields(row: GridRow, template: str) -> list[str]:
    """Return list of field names required by template but missing from row."""
    available = _row_fields(row)
    needed = _template_field_names(template)
    return [f for f in needed if f not in available]


def compute_dest_path(row: GridRow, template: str) -> str | None:
    """Compute destination path from template and row fields.

    Returns None if any required field is missing.
    """
    fields = _row_fields(row)
    needed = _template_field_names(template)
    if any(f not in fields for f in needed):
        return None
    return template.format_map(fields)


def compute_dest_path_with_unknown(row: GridRow, template: str) -> str:
    """Compute destination path, substituting 'unknown' for missing fields."""
    fields = _row_fields(row)
    needed = _template_field_names(template)
    fill = {f: fields.get(f, "unknown") for f in needed}
    return template.format_map(fill)
