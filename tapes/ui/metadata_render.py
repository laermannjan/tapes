"""Pure rendering functions for the metadata view grid."""

from __future__ import annotations

from typing import Any

from tapes.templates import template_field_names
from tapes.ui.colors import COLOR_MUTED, SAND, SPRING


def get_display_fields(template: str, extra_keys: set[str] | None = None) -> list[str]:
    """Fields to show in the metadata grid, derived from template + metadata.

    Always starts with ``media_type`` (read-only context) and ``tmdb_id``,
    followed by remaining field names from ``{field}`` placeholders.
    ``ext`` is excluded (always derived from the file extension).

    When *extra_keys* is provided, any metadata keys not already in the
    template are appended (sorted) so all extracted data is visible.
    """
    fields = [f for f in template_field_names(template) if f not in ("ext", "media_type", "tmdb_id")]
    result = ["media_type", "tmdb_id", *fields]

    if extra_keys:
        extra = sorted(k for k in extra_keys if k not in result and k != "ext")
        result.extend(extra)

    return result


def display_val(val: Any, missing: str = "?") -> str:
    """Format a value for display. None becomes *missing* marker."""
    if val is None:
        return missing
    return str(val)


def is_multi_value(val: Any) -> bool:
    """Return True if the value is a multi-value marker like '(N values)'."""
    if not isinstance(val, str):
        return False
    return val.startswith("(") and val.endswith(" values)")


def diff_style(metadata_val: Any, candidate_val: Any) -> str:
    """Return a Rich style for a candidate value relative to the metadata.

    - Muted gray if candidate is None (missing) or matches the metadata.
    - Green if candidate fills an empty metadata slot.
    - Warm yellow if candidate differs from a non-empty metadata value.
    """

    if candidate_val is None:
        return COLOR_MUTED
    if metadata_val is None or metadata_val == "":
        return SPRING
    if str(metadata_val) == str(candidate_val):
        return COLOR_MUTED
    return SAND
