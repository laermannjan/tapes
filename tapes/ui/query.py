"""Mock TMDB lookup for grid TUI."""
from __future__ import annotations

from typing import Any

# Mock database: title -> (fields, confidence).
# Confident matches (>= 0.9) auto-accept. Uncertain (< 0.9) become match sub-rows.
_MOCK_TMDB: dict[str, tuple[dict[str, Any], float]] = {
    "dune": ({"title": "Dune", "year": 2021}, 0.95),
    "arrival": ({"title": "Arrival", "year": 2016}, 0.95),
    "breaking bad": (
        {"title": "Breaking Bad", "year": 2008},
        0.75,
    ),
    "interstellar": ({"title": "Interstellar", "year": 2014}, 0.95),
}

# Per-episode overrides for Breaking Bad (keyed by episode number).
_BB_EPISODES: dict[int, dict[str, Any]] = {
    1: {"episode_title": "Pilot"},
    2: {"episode_title": "Cat's in the Bag..."},
    3: {"episode_title": "...And the Bag's in the River"},
}

CONFIDENCE_THRESHOLD = 0.9


def mock_tmdb_lookup(
    title: str,
    *,
    episode: int | None = None,
) -> tuple[dict[str, Any], float] | None:
    """Look up a title in the mock TMDB database.

    Returns (fields_dict, confidence) if found, or None if no match.
    For episode lookups, merges episode-specific fields.
    """
    if not title:
        return None
    result = _MOCK_TMDB.get(title.lower())
    if result is None:
        return None
    fields, confidence = result
    fields = dict(fields)  # copy to avoid mutation
    # Merge episode-specific data
    if episode is not None and title.lower() == "breaking bad":
        ep_data = _BB_EPISODES.get(episode, {})
        fields.update(ep_data)
    return fields, confidence
