"""Metadata extraction from filenames using guessit."""

from __future__ import annotations

import guessit

from tapes.models import FileMetadata

# guessit key -> normalized key
_RENAME_KEYS: dict[str, str] = {
    "video_codec": "codec",
    "source": "media_source",
    "audio_codec": "audio",
}


def _normalize_raw(data: dict) -> dict:
    """Rename guessit keys to our normalized names and drop internal fields."""
    result: dict = {}
    for key, value in data.items():
        normalized = _RENAME_KEYS.get(key, key)
        result[normalized] = value
    return result


def extract_metadata(
    filename: str, folder_name: str | None = None
) -> FileMetadata:
    """Extract metadata from a filename (and optionally a folder name).

    Runs guessit on the filename, normalizes field names, and returns
    a FileMetadata dataclass. Falls back to folder_name for title/year
    if guessit can't determine them from the filename alone.
    """
    guess = dict(guessit.guessit(filename))

    # Extract primary fields from filename guess
    media_type = guess.pop("type", None)
    title = guess.pop("title", None)
    year = guess.pop("year", None)
    season = guess.pop("season", None)
    episode = guess.pop("episode", None)
    part = guess.pop("part", None) or guess.pop("cd", None)

    # Remove non-useful internal fields
    guess.pop("container", None)
    guess.pop("mimetype", None)

    # Folder fallback for title and year
    if folder_name is not None and (title is None or year is None):
        folder_guess = dict(guessit.guessit(folder_name))
        if title is None:
            title = folder_guess.get("title")
        if year is None:
            year = folder_guess.get("year")

    # Build normalized raw dict from remaining fields
    raw = _normalize_raw(guess)

    return FileMetadata(
        media_type=media_type,
        title=title,
        year=year,
        season=season,
        episode=episode,
        part=part,
        raw=raw,
    )
