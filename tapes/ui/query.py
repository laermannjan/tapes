"""Mock TMDB lookup for grid TUI."""
from __future__ import annotations

from typing import Any

# Mock database mapping lowercase title to result fields.
_MOCK_TMDB: dict[str, dict[str, Any]] = {
    "dune": {"title": "Dune", "year": 2021},
    "arrival": {"title": "Arrival", "year": 2016},
    "breaking bad": {"title": "Breaking Bad"},
    "interstellar": {"title": "Interstellar", "year": 2014},
}


def mock_tmdb_lookup(title: str) -> dict[str, Any] | None:
    """Look up a title in the mock TMDB database.

    Returns a dict of fields if found, or None if no match.
    """
    if not title:
        return None
    return _MOCK_TMDB.get(title.lower())
