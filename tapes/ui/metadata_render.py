"""Pure rendering functions for the detail view grid."""

from __future__ import annotations

from typing import Any

from tapes.templates import template_field_names
from tapes.ui.colors import COLOR_ADDITION, COLOR_DIFF, COLOR_MUTED


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
    - Soft green if source fills an empty result slot.
    - Ember if source differs from a non-empty result.
    """

    if source_val is None:
        return COLOR_MUTED
    if result_val is None or result_val == "":
        return COLOR_ADDITION
    if str(result_val) == str(source_val):
        return COLOR_MUTED
    return COLOR_DIFF
