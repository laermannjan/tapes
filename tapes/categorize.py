"""Categorize staged files by media type and extension."""

from __future__ import annotations

from typing import Any

from tapes.fields import MEDIA_TYPE, MEDIA_TYPE_EPISODE, MEDIA_TYPE_MOVIE, SEASON, TITLE
from tapes.tree_model import FileNode

SUBTITLE_EXTS = frozenset({".srt", ".sub", ".ass", ".ssa", ".idx"})
SIDECAR_EXTS = frozenset({".nfo", ".xml", ".jpg", ".png"})


def categorize_staged(files: list[FileNode]) -> dict[str, int]:
    """Categorize staged files and return counts."""
    movies = 0
    episodes = 0
    subtitles = 0
    sidecars = 0
    other = 0
    shows: set[str] = set()
    seasons: set[tuple[str, Any]] = set()

    for f in files:
        ext = f.path.suffix.lower()
        media_type = f.metadata.get(MEDIA_TYPE)

        if media_type == MEDIA_TYPE_MOVIE:
            movies += 1
        elif media_type == MEDIA_TYPE_EPISODE:
            episodes += 1
            title = f.metadata.get(TITLE, "")
            season = f.metadata.get(SEASON)
            if title:
                shows.add(title)
            if title and season is not None:
                seasons.add((title, season))
        elif ext in SUBTITLE_EXTS:
            subtitles += 1
        elif ext in SIDECAR_EXTS:
            sidecars += 1
        else:
            other += 1

    return {
        "movies": movies,
        "episodes": episodes,
        "shows": len(shows),
        "seasons": len(seasons),
        "subtitles": subtitles,
        "sidecars": sidecars,
        "other": other,
        "total": len(files),
    }
