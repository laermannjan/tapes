"""Pure rendering functions for the detail view grid."""

from __future__ import annotations

from typing import Any

from tapes.ui.tree_render import MUTED, template_field_names


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
