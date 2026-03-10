"""Metadata extraction from filenames using guessit."""

from __future__ import annotations

from dataclasses import dataclass, field

import guessit


@dataclass
class FileMetadata:
    """Parsed metadata about a media file."""

    media_type: str | None = None
    title: str | None = None
    year: int | None = None
    season: int | None = None
    episode: int | None = None
    part: int | None = None
    raw: dict = field(default_factory=dict)


# guessit key -> normalized key
_RENAME_KEYS: dict[str, str] = {
    "video_codec": "codec",
    "source": "media_source",
    "audio_codec": "audio",
    "screen_size": "resolution",
    "audio_channels": "audio_channels",
    "audio_profile": "audio_profile",
    "video_profile": "video_profile",
}

# Values in guessit's "other" field that map to semantic HDR categories
_HDR_VALUES: frozenset[str] = frozenset(
    {
        "HDR10",
        "HDR10+",
        "Dolby Vision",
        "Standard Dynamic Range",
    }
)


def _normalize_raw(data: dict) -> dict:
    """Rename guessit keys to our normalized names and split ``other``.

    The guessit ``other`` field is a grab-bag (str or list).  We split it
    into semantic fields: ``hdr`` (HDR10, Dolby Vision, etc.), ``three_d``
    (3D), ``remux`` (bool), and leave the rest in ``other``.
    """
    result: dict = {}
    for key, value in data.items():
        if key == "other":
            _split_other(value, result)
            continue
        normalized = _RENAME_KEYS.get(key, key)
        result[normalized] = value
    return result


def _split_other(value: str | list[str], out: dict) -> None:
    """Split guessit's ``other`` into semantic fields."""
    items = value if isinstance(value, list) else [value]
    hdr_parts: list[str] = []
    rest: list[str] = []
    for item in items:
        if item in _HDR_VALUES:
            hdr_parts.append(item)
        elif item == "3D":
            out["three_d"] = "3D"
        elif item == "Remux":
            out["remux"] = "Remux"
        else:
            rest.append(item)
    if hdr_parts:
        out["hdr"] = ".".join(hdr_parts)
    if rest:
        out["other"] = ".".join(rest)


def extract_metadata(filename: str, folder_name: str | None = None) -> FileMetadata:
    """Extract metadata from a filename (and optionally a folder name).

    Runs guessit on the filename, normalizes field names, and returns
    a FileMetadata dataclass. Falls back to folder_name for title,
    year, and season if guessit can't determine them from the filename
    alone.
    """
    guess = dict(guessit.guessit(filename))

    media_type = guess.pop("type", None)
    title = guess.pop("title", None)
    year = guess.pop("year", None)
    season = guess.pop("season", None)
    episode = guess.pop("episode", None)
    # guessit returns a list for multi-episode files (e.g. S01E03E04).
    # Normalize to the first episode for scoring and template formatting.
    if isinstance(episode, list):
        episode = episode[0] if episode else None
    part = guess.pop("part", None) or guess.pop("cd", None)

    guess.pop("container", None)
    guess.pop("mimetype", None)

    if folder_name is not None and (title is None or year is None or season is None):
        folder_guess = dict(guessit.guessit(folder_name))
        if title is None:
            title = folder_guess.get("title")
        if year is None:
            year = folder_guess.get("year")
        if season is None:
            season = folder_guess.get("season")

    raw = _normalize_raw(guess)
    if part is not None:
        raw["part"] = part

    return FileMetadata(
        media_type=media_type,
        title=title,
        year=year,
        season=season,
        episode=episode,
        part=part,
        raw=raw,
    )
